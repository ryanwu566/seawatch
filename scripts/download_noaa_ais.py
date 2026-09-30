"""Download the approved NOAA AIS daily source file."""

from __future__ import annotations

import argparse
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.adapters.noaa_ais import (
    DownloadError,
    download_file,
    write_download_record,
)
from apps.api.seawatch.datasets.source_catalog import load_phase3a_catalog


DEFAULT_SOURCE_URL = (
    "https://ocmgeodatastor1.blob.core.windows.net/"
    "marinecadastre/ais2024/ais-2024-01-01.parquet"
)
DEFAULT_DESTINATION = Path("data/raw/ais-2024-01-01.parquet")
DEFAULT_CATALOG = Path("config/noaa_ais_phase3a_dates.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2024-01-01")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--url")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        source_date = date.fromisoformat(args.date)
        entry = load_phase3a_catalog(args.catalog).for_date(source_date)
        if args.url is not None and args.url != entry.source_url:
            raise ValueError(
                f"URL is not the approved NOAA {source_date.isoformat()} source"
            )
        destination = args.destination or Path("data/raw") / entry.raw_filename
        sidecar = destination.with_name(destination.name + ".download.json")
        if sidecar.exists() and not args.force:
            raise FileExistsError(f"download record already exists: {sidecar}")
        record = download_file(
            entry.source_url, destination, overwrite=args.force
        )
        write_download_record(record, sidecar, overwrite=args.force)
    except (DownloadError, FileExistsError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")

    print(f"destination: {record.destination}")
    print(f"content_length: {record.content_length}")
    print(f"sha256: {record.sha256}")
    print(f"download_utc: {record.download_utc.isoformat().replace('+00:00', 'Z')}")
    print(f"record: {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
