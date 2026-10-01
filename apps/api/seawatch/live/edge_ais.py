"""Bounded NMEA framing and pure local AIS position normalization."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from pyais import decode

from .schema import LiveVesselObservation


_POSITION_TYPES = {1, 2, 3, 18, 19, 27}


@dataclass(frozen=True)
class EdgeDecodeResult:
    observations: tuple[LiveVesselObservation, ...]
    accepted_frames: int
    rejected_frames: int
    pending_fragments: int


@dataclass
class _Assembly:
    lines: list[bytes]
    next_fragment: int
    expires_at: float
    observed_at: datetime | None


class EdgeAisDecoder:
    """Validate NMEA envelopes, assemble fragments, and delegate AIS bits to pyais."""

    def __init__(
        self,
        max_line_bytes: int = 1024,
        fragment_ttl_seconds: float = 15.0,
        monotonic: Callable[[], float] = time.monotonic,
        *,
        max_assemblies: int = 128,
    ) -> None:
        self._max_line_bytes = max_line_bytes
        self._fragment_ttl_seconds = fragment_ttl_seconds
        self._monotonic = monotonic
        self._max_assemblies = max_assemblies
        self._assemblies: dict[tuple[bytes, int, bytes, bytes], _Assembly] = {}

    def _result(
        self,
        *,
        observations: tuple[LiveVesselObservation, ...] = (),
        accepted: int = 0,
        rejected: int = 0,
    ) -> EdgeDecodeResult:
        return EdgeDecodeResult(
            observations=observations,
            accepted_frames=accepted,
            rejected_frames=rejected,
            pending_fragments=len(self._assemblies),
        )

    @staticmethod
    def _checksum_ok(body: bytes, checksum_text: bytes) -> bool:
        if len(checksum_text) != 2:
            return False
        try:
            expected = int(checksum_text, 16)
        except ValueError:
            return False
        actual = 0
        for byte in body[1:]:
            actual ^= byte
        return actual == expected

    def _unwrap_tag(self, line: bytes) -> tuple[bytes, datetime | None]:
        if not line.startswith(b"\\"):
            return line, None
        closing = line.find(b"\\", 1)
        if closing < 0:
            raise ValueError("unterminated NMEA tag block")
        tag = line[1:closing]
        try:
            body, checksum = tag.rsplit(b"*", 1)
        except ValueError as exc:
            raise ValueError("tag block has no checksum") from exc
        if not self._checksum_ok(b"!" + body, checksum):
            raise ValueError("invalid tag block checksum")
        timestamp = None
        for item in body.split(b","):
            if item.startswith(b"c:"):
                timestamp = datetime.fromtimestamp(float(item[2:]), tz=timezone.utc)
                break
        return line[closing + 1 :], timestamp

    def _parse_envelope(
        self, line: bytes
    ) -> tuple[tuple[bytes, int, bytes, bytes], int, int, datetime | None, bytes]:
        sentence, tag_time = self._unwrap_tag(line)
        try:
            body, checksum = sentence.rsplit(b"*", 1)
        except ValueError as exc:
            raise ValueError("NMEA sentence has no checksum") from exc
        if not self._checksum_ok(body, checksum):
            raise ValueError("invalid NMEA checksum")
        fields = body.split(b",")
        if len(fields) != 7 or fields[0] not in {b"!AIVDM", b"!AIVDO"}:
            raise ValueError("unsupported NMEA sentence")
        try:
            total = int(fields[1])
            fragment = int(fields[2])
            fill_bits = int(fields[6])
        except ValueError as exc:
            raise ValueError("invalid NMEA numeric field") from exc
        if not (1 <= total <= 9 and 1 <= fragment <= total and 0 <= fill_bits <= 5):
            raise ValueError("invalid NMEA fragment bounds")
        sequence = fields[3]
        channel = fields[4]
        if total > 1 and not sequence:
            raise ValueError("multipart NMEA sentence requires a sequence ID")
        key = (fields[0], total, sequence, channel)
        return key, total, fragment, tag_time, sentence

    def feed_line(
        self,
        line: bytes,
        *,
        received_at: datetime,
    ) -> EdgeDecodeResult:
        self.expire_fragments()
        candidate = line.strip()
        if not candidate or len(candidate) > self._max_line_bytes:
            return self._result(rejected=1)
        try:
            key, total, fragment, tag_time, sentence = self._parse_envelope(candidate)
        except (ValueError, OverflowError, OSError):
            return self._result(rejected=1)

        lines: list[bytes]
        observed_at = tag_time
        if total == 1:
            lines = [sentence]
        elif fragment == 1:
            if key in self._assemblies:
                del self._assemblies[key]
                return self._result(rejected=1)
            if len(self._assemblies) >= self._max_assemblies:
                return self._result(rejected=1)
            self._assemblies[key] = _Assembly(
                lines=[sentence],
                next_fragment=2,
                expires_at=self._monotonic() + self._fragment_ttl_seconds,
                observed_at=tag_time,
            )
            return self._result()
        else:
            assembly = self._assemblies.get(key)
            if assembly is None or fragment != assembly.next_fragment:
                if assembly is not None:
                    del self._assemblies[key]
                return self._result(rejected=1)
            assembly.lines.append(sentence)
            assembly.next_fragment += 1
            if fragment < total:
                return self._result()
            lines = assembly.lines
            observed_at = assembly.observed_at or tag_time
            del self._assemblies[key]

        try:
            message = decode(*lines)
            data = message.asdict()
            observation = self._normalize(
                data,
                observed_at=observed_at or received_at,
                received_at=received_at,
            )
        except (ValueError, TypeError, KeyError, OverflowError):
            return self._result(rejected=1)
        observations = (observation,) if observation is not None else ()
        return self._result(observations=observations, accepted=1)

    def expire_fragments(self) -> int:
        now = self._monotonic()
        expired = [key for key, value in self._assemblies.items() if value.expires_at <= now]
        for key in expired:
            del self._assemblies[key]
        return len(expired)

    @staticmethod
    def _optional_number(value: object, unavailable_at: float) -> float | None:
        if value is None:
            return None
        number = float(value)
        if not math.isfinite(number) or number >= unavailable_at:
            return None
        return number

    def _normalize(
        self,
        data: dict,
        *,
        observed_at: datetime,
        received_at: datetime,
    ) -> LiveVesselObservation | None:
        message_type = int(data["msg_type"])
        if message_type not in _POSITION_TYPES:
            return None
        latitude = float(data["lat"])
        longitude = float(data["lon"])
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90.0 <= latitude <= 90.0
            or not -180.0 <= longitude <= 180.0
        ):
            return None
        mmsi = int(data["mmsi"])
        speed_limit = 63.0 if message_type == 27 else 102.3
        course_limit = 511.0 if message_type == 27 else 360.0
        status = data.get("status")
        return LiveVesselObservation(
            provider_id=f"edge:{mmsi}",
            latitude=latitude,
            longitude=longitude,
            observed_at=observed_at,
            received_at=received_at,
            source="edge_ais",
            sog_knots=self._optional_number(data.get("speed"), speed_limit),
            cog_deg=self._optional_number(data.get("course"), course_limit),
            heading_deg=self._optional_number(data.get("heading"), 511.0),
            nav_status=int(status) if status is not None else None,
            vessel_type=int(data["ship_type"])
            if data.get("ship_type") is not None
            else None,
            name=data.get("shipname"),
            synthesized=False,
            mmsi=mmsi,
        )
