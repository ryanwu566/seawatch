"""Historical AIS adapter interface and concrete implementations.

The adapter is the ONLY layer that changes when a new historical data source
arrives.

Every downstream pipeline module receives:

    Iterable[HistoricalAisRecord]

The source-specific file format is fully encapsulated here.

Supported / planned sources
---------------------------
* Synthetic fixture
* NOAA MarineCadastre
* Global Fishing Watch AIS Vessel Presence
* NODASS / Taiwan AIS

Important
---------
Global Fishing Watch AIS Vessel Presence is NOT raw AIS message-level data.

GFW records used by this adapter represent standardized historical presence
observations. Their provenance is explicitly labeled ``gfw_presence``.
"""

from __future__ import annotations

import abc

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .schema import (
    DATA_SOURCE_GFW_PRESENCE,
    DATA_SOURCE_NOAA,
    DATA_SOURCE_SYNTHETIC,
    HistoricalAisRecord,
)


# --------------------------------------------------------------------------- #
# Abstract base — contract every adapter must satisfy
# --------------------------------------------------------------------------- #


class HistoricalAisAdapter(abc.ABC):
    """Produce ``HistoricalAisRecord`` objects from a concrete data source.

    Implementations must:

    - Yield records in any order; the pipeline sorts by timestamp.
    - Set ``data_source`` to the appropriate ``DATA_SOURCE_*`` constant.
    - Keep source-specific schemas inside the adapter.
    - Use ``vessel_id`` as the pipeline-internal vessel identifier.
    - Be deterministic for identical input data.
    """

    @abc.abstractmethod
    def load_tracks(self) -> Iterable[HistoricalAisRecord]:
        """Yield all historical vessel observations from this source.

        Raises
        ------
        NotImplementedError
            When a concrete source has not been implemented yet.

        ValueError
            When the source data fails basic validation.
        """

    @property
    @abc.abstractmethod
    def data_source_label(self) -> str:
        """The ``DATA_SOURCE_*`` constant this adapter produces."""

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable description for logs and manifest entries."""


# --------------------------------------------------------------------------- #
# NOAA stub — preserved until NOAA integration is implemented
# --------------------------------------------------------------------------- #


class NoaaParquetAdapter(HistoricalAisAdapter):
    """Adapter for official NOAA MarineCadastre AIS GeoParquet files.

    Status
    ------
    Stub — not yet implemented.

    This class is intentionally preserved so existing tests and future NOAA
    work remain isolated from the GFW integration.
    """

    def __init__(self, parquet_path: Path | str) -> None:
        self._path = Path(parquet_path)

    @property
    def data_source_label(self) -> str:
        return DATA_SOURCE_NOAA

    @property
    def description(self) -> str:
        return (
            f"NOAA MarineCadastre AIS GeoParquet "
            f"[{self._path.name}] (stub)"
        )

    def load_tracks(self) -> Iterable[HistoricalAisRecord]:  # pragma: no cover
        raise NotImplementedError(
            "NoaaParquetAdapter is not yet implemented. "
            "NOAA data has not been acquired. "
            "See the PLUG_IN_HERE comment in adapter.py for instructions."
        )


# --------------------------------------------------------------------------- #
# Synthetic fixture adapter
# --------------------------------------------------------------------------- #


class SyntheticFixtureAdapter(HistoricalAisAdapter):
    """Adapter that loads deterministic Taiwan-corridor synthetic fixtures.

    This adapter is for testing and hackathon demo fallback only.

    Every record it produces carries:

        data_source='synthetic_fixture'

    Synthetic records must never be confused with real historical vessel data.
    """

    def __init__(self, fixture_module_path: str = "default") -> None:
        """Reserve a fixture selector for future multi-fixture support."""

        self._fixture = fixture_module_path

    @property
    def data_source_label(self) -> str:
        return DATA_SOURCE_SYNTHETIC

    @property
    def description(self) -> str:
        return (
            "Synthetic fixture adapter — "
            "Taiwan-corridor deterministic test data. "
            "NOT real AIS. "
            "For pipeline testing and hackathon demos only."
        )

    def load_tracks(self) -> Iterable[HistoricalAisRecord]:
        """Yield deterministic synthetic fixture records."""

        from tests.fixtures.historical.synthetic_corridor import (
            SYNTHETIC_CORRIDOR_TRACKS,
        )

        return iter(SYNTHETIC_CORRIDOR_TRACKS)


# --------------------------------------------------------------------------- #
# Global Fishing Watch timestamp normalization
# --------------------------------------------------------------------------- #


def _normalize_gfw_timestamp(value: object) -> str:
    """Convert a GFW presence timestamp into ISO-8601 UTC.

    Examples
    --------
    Input:

        2026-09-29 13:00

    Output:

        2026-09-29T13:00:00Z

    Notes
    -----
    The GFW timestamp represents a standardized vessel-presence observation
    bucket. It must not be interpreted as the exact timestamp of a raw AIS
    message.
    """

    if value is None:
        raise ValueError(
            "GFW observation is missing date"
        )

    text = str(value).strip()

    if not text:
        raise ValueError(
            "GFW observation contains an empty date"
        )

    normalized = text.replace(
        " ",
        "T",
    )

    try:
        if normalized.endswith("Z"):
            parsed = datetime.fromisoformat(
                normalized.replace(
                    "Z",
                    "+00:00",
                )
            )

        else:
            parsed = datetime.fromisoformat(
                normalized
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

    except ValueError as exc:
        raise ValueError(
            f"Invalid GFW timestamp: {value!r}"
        ) from exc

    return (
        parsed
        .astimezone(timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


# --------------------------------------------------------------------------- #
# Global Fishing Watch AIS Vessel Presence adapter
# --------------------------------------------------------------------------- #


class GfwPresenceParquetAdapter(HistoricalAisAdapter):
    """Read GFW AIS Vessel Presence daily Parquet files.

    Expected files
    --------------
    A directory containing files such as:

        gfw_taiwan_2026-09-01.parquet
        gfw_taiwan_2026-09-02.parquet
        ...
        gfw_taiwan_2026-09-29.parquet

    Required columns
    ----------------
    - date
    - lat
    - lon
    - vesselId

    Identity handling
    -----------------
    GFW ``vesselId`` is used only as the internal
    ``HistoricalAisRecord.vessel_id``.

    A valid MMSI may be copied into the record's private identity field solely
    so the pipeline can derive the live layer's opaque identity. It is excluded
    from repr/equality and must never be serialized. IMO, callsign, ship name,
    and other source-specific identity fields are never copied.

    Movement fields
    ---------------
    This GFW Vessel Presence dataset does not provide raw AIS SOG, COG, or
    heading for the canonical observations used here.

    Therefore:

        sog_knots=None
        cog_deg=None
        heading_deg=None

    GFW ``vesselType`` is textual, while the canonical schema expects an AIS
    numeric ship-type code. No fabricated mapping is performed.

    Therefore:

        vessel_type=None

    Memory behavior
    ---------------
    Parquet files are streamed in batches rather than loading the entire
    multi-million-row dataset into memory.
    """

    REQUIRED_COLUMNS = (
        "date",
        "lat",
        "lon",
        "vesselId",
    )

    def __init__(
        self,
        parquet_dir: Path | str,
        *,
        batch_size: int = 100_000,
    ) -> None:
        self._parquet_dir = Path(
            parquet_dir
        )

        if batch_size <= 0:
            raise ValueError(
                "batch_size must be greater than zero"
            )

        self._batch_size = batch_size

    @property
    def data_source_label(self) -> str:
        return DATA_SOURCE_GFW_PRESENCE

    @property
    def description(self) -> str:
        return (
            "Global Fishing Watch AIS Vessel Presence "
            "daily Parquet adapter "
            "(historical presence observations; not raw AIS)"
        )

    def _discover_files(self) -> list[Path]:
        """Return GFW daily Parquet files in deterministic filename order."""

        if not self._parquet_dir.exists():
            raise FileNotFoundError(
                "GFW parquet directory does not exist: "
                f"{self._parquet_dir}"
            )

        if not self._parquet_dir.is_dir():
            raise NotADirectoryError(
                "GFW parquet path is not a directory: "
                f"{self._parquet_dir}"
            )

        files = sorted(
            self._parquet_dir.glob(
                "gfw_taiwan_*.parquet"
            )
        )

        if not files:
            raise FileNotFoundError(
                "No GFW Taiwan Parquet files found in: "
                f"{self._parquet_dir}"
            )

        return files

    def discover_files(self) -> tuple[Path, ...]:
        """Return the validated input files without reading or modifying them."""

        return tuple(self._discover_files())

    @staticmethod
    def _validate_coordinates(
        *,
        latitude: object,
        longitude: object,
        source_file: Path,
    ) -> tuple[float, float]:
        """Validate and normalize WGS84 coordinates."""

        try:
            lat = float(latitude)
            lon = float(longitude)

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Invalid GFW coordinates in "
                f"{source_file.name}: "
                f"lat={latitude!r}, "
                f"lon={longitude!r}"
            ) from exc

        if not (
            -90.0 <= lat <= 90.0
        ):
            raise ValueError(
                "Invalid GFW latitude in "
                f"{source_file.name}: "
                f"{lat}"
            )

        if not (
            -180.0 <= lon <= 180.0
        ):
            raise ValueError(
                "Invalid GFW longitude in "
                f"{source_file.name}: "
                f"{lon}"
            )

        return lat, lon

    @staticmethod
    def _normalize_mmsi(value: object) -> int | None:
        """Return a valid nine-digit MMSI or ``None`` for an unsafe join."""

        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, float):
            if not value.is_integer():
                return None
            candidate = int(value)
        else:
            text = str(value).strip()
            if not text:
                return None
            try:
                candidate = int(text)
            except ValueError:
                return None

        if not 100_000_000 <= candidate <= 999_999_999:
            return None
        return candidate

    def load_tracks(self) -> Iterable[HistoricalAisRecord]:
        """Yield canonical historical observations from GFW Parquet files."""

        try:
            import pyarrow.parquet as pq

        except ImportError as exc:
            raise RuntimeError(
                "GfwPresenceParquetAdapter requires pyarrow. "
                "Install the project dependency before loading GFW data."
            ) from exc

        parquet_files = self.discover_files()

        for parquet_path in parquet_files:
            parquet_file = pq.ParquetFile(
                parquet_path
            )

            available_columns = set(
                parquet_file.schema_arrow.names
            )

            missing_columns = (
                set(self.REQUIRED_COLUMNS)
                - available_columns
            )

            if missing_columns:
                missing = ", ".join(
                    sorted(missing_columns)
                )

                raise ValueError(
                    "GFW Parquet file is missing required "
                    f"columns ({missing}): "
                    f"{parquet_path.name}"
                )

            selected_columns = list(self.REQUIRED_COLUMNS)
            if "mmsi" in available_columns:
                selected_columns.append("mmsi")

            batches = parquet_file.iter_batches(
                columns=selected_columns,
                batch_size=self._batch_size,
            )

            for batch in batches:
                for row in batch.to_pylist():
                    vessel_id_value = row.get(
                        "vesselId"
                    )

                    observed_at_value = row.get(
                        "date"
                    )

                    latitude_value = row.get(
                        "lat"
                    )

                    longitude_value = row.get(
                        "lon"
                    )

                    # Skip rows that cannot form a canonical observation.
                    if (
                        vessel_id_value is None
                        or observed_at_value is None
                        or latitude_value is None
                        or longitude_value is None
                    ):
                        continue

                    vessel_id = str(
                        vessel_id_value
                    ).strip()

                    if not vessel_id:
                        continue

                    latitude, longitude = (
                        self._validate_coordinates(
                            latitude=latitude_value,
                            longitude=longitude_value,
                            source_file=parquet_path,
                        )
                    )

                    observed_at = (
                        _normalize_gfw_timestamp(
                            observed_at_value
                        )
                    )

                    yield HistoricalAisRecord(
                        vessel_id=vessel_id,

                        observed_at=observed_at,

                        longitude=longitude,

                        latitude=latitude,

                        data_source=(
                            DATA_SOURCE_GFW_PRESENCE
                        ),

                        sog_knots=None,

                        cog_deg=None,

                        heading_deg=None,

                        vessel_type=None,

                        mmsi=self._normalize_mmsi(
                            row.get("mmsi")
                        ),
                    )
