from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.api.seawatch.live.edge_ais import EdgeAisDecoder


FIXTURE = Path("tests/fixtures/ais/edge_nmea.txt")
RECEIVED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _lines() -> dict[str, bytes]:
    records: dict[str, bytes] = {}
    for line in FIXTURE.read_bytes().splitlines():
        if not line or line.startswith(b"#"):
            continue
        label, sentence = line.split(b"|", 1)
        records[label.decode("ascii")] = sentence
    return records


def test_decodes_class_a_and_class_b_positions_to_normalized_observations() -> None:
    lines = _lines()
    decoder = EdgeAisDecoder()

    class_a = decoder.feed_line(lines["class_a"], received_at=RECEIVED_AT)
    class_b = decoder.feed_line(lines["class_b"], received_at=RECEIVED_AT)

    assert class_a.accepted_frames == 1
    assert class_a.rejected_frames == 0
    assert len(class_a.observations) == 1
    assert class_a.observations[0].mmsi == 416000001
    assert class_a.observations[0].latitude == 22.5
    assert class_a.observations[0].longitude == 120.25
    assert class_a.observations[0].sog_knots == 12.3
    assert class_a.observations[0].cog_deg == 182.3
    assert class_a.observations[0].heading_deg == 181.0
    assert class_a.observations[0].observed_at == RECEIVED_AT
    assert class_a.observations[0].received_at == RECEIVED_AT
    assert class_a.observations[0].source == "edge_ais"
    assert class_a.observations[0].synthesized is False

    assert len(class_b.observations) == 1
    assert class_b.observations[0].mmsi == 416000002
    assert class_b.observations[0].latitude == 23.0
    assert class_b.observations[0].longitude == 121.0


def test_assembles_valid_two_part_position_and_keeps_channels_isolated() -> None:
    lines = _lines()
    decoder = EdgeAisDecoder()

    first_b = decoder.feed_line(lines["multipart_b_1"], received_at=RECEIVED_AT)
    first_a = decoder.feed_line(lines["multipart_a_1"], received_at=RECEIVED_AT)
    complete_b = decoder.feed_line(lines["multipart_b_2"], received_at=RECEIVED_AT)
    complete_a = decoder.feed_line(lines["multipart_a_2"], received_at=RECEIVED_AT)

    assert first_b.pending_fragments == 1
    assert first_a.pending_fragments == 2
    assert len(complete_b.observations) == 1
    assert len(complete_a.observations) == 1
    assert complete_b.observations[0].mmsi == 367059850
    assert complete_b.observations[0].latitude == 29.543695
    assert complete_b.observations[0].longitude == pytest.approx(-88.810392)
    assert complete_a.pending_fragments == 0


def test_rejects_bad_checksum_oversized_out_of_order_and_duplicate_fragments() -> None:
    lines = _lines()
    decoder = EdgeAisDecoder()

    bad_checksum = lines["class_a"][:-2] + b"00"
    assert decoder.feed_line(bad_checksum, received_at=RECEIVED_AT).rejected_frames == 1
    assert decoder.feed_line(b"!" + b"X" * 1024, received_at=RECEIVED_AT).rejected_frames == 1
    assert (
        decoder.feed_line(lines["multipart_b_2"], received_at=RECEIVED_AT).rejected_frames
        == 1
    )

    assert decoder.feed_line(lines["multipart_b_1"], received_at=RECEIVED_AT).pending_fragments == 1
    duplicate = decoder.feed_line(lines["multipart_b_1"], received_at=RECEIVED_AT)
    assert duplicate.rejected_frames == 1
    assert duplicate.pending_fragments == 0


def test_unsupported_static_message_is_valid_but_emits_no_position() -> None:
    lines = _lines()
    decoder = EdgeAisDecoder()

    decoder.feed_line(lines["static_1"], received_at=RECEIVED_AT)
    result = decoder.feed_line(lines["static_2"], received_at=RECEIVED_AT)

    assert result.accepted_frames == 1
    assert result.rejected_frames == 0
    assert result.observations == ()


def test_normalizes_navigation_sentinels_to_none() -> None:
    result = EdgeAisDecoder().feed_line(
        _lines()["navigation_sentinels"], received_at=RECEIVED_AT
    )
    observation = result.observations[0]

    assert observation.sog_knots is None
    assert observation.cog_deg is None
    assert observation.heading_deg is None


def test_coordinate_sentinels_are_accepted_but_not_emitted_as_positions() -> None:
    result = EdgeAisDecoder().feed_line(
        _lines()["coordinate_sentinels"], received_at=RECEIVED_AT
    )

    assert result.accepted_frames == 1
    assert result.rejected_frames == 0
    assert result.observations == ()


def test_tag_block_epoch_overrides_receive_time_for_observed_at() -> None:
    result = EdgeAisDecoder().feed_line(_lines()["tagged"], received_at=RECEIVED_AT)

    assert result.observations[0].observed_at == datetime.fromtimestamp(
        1671620143, tz=timezone.utc
    )
    assert result.observations[0].received_at == RECEIVED_AT


def test_fragment_expiry_and_bounded_assembly_count() -> None:
    lines = _lines()
    clock = [10.0]
    decoder = EdgeAisDecoder(
        fragment_ttl_seconds=5.0,
        monotonic=lambda: clock[0],
        max_assemblies=1,
    )

    decoder.feed_line(lines["multipart_b_1"], received_at=RECEIVED_AT)
    second_key = lines["multipart_a_1"].replace(b",7,A,", b",8,A,")
    body = second_key.rsplit(b"*", 1)[0]
    checksum = 0
    for byte in body[1:]:
        checksum ^= byte
    second_key = body + f"*{checksum:02X}".encode("ascii")

    bounded = decoder.feed_line(second_key, received_at=RECEIVED_AT)
    assert bounded.rejected_frames == 1
    assert bounded.pending_fragments == 1

    clock[0] = 16.0
    assert decoder.expire_fragments() == 1
    assert decoder.feed_line(lines["class_a"], received_at=RECEIVED_AT).pending_fragments == 0
