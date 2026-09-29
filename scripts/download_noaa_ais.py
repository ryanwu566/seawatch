"""Download the approved NOAA AIS daily source file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.adapters.noaa_ais import (
    DownloadError,
    download_file,
    write_download_record,
)


DEFAULT_SOURCE_URL = (
    "https://ocmgeodatastor1.blob.core.windows.net/"
    "marinecadastre/ais2024/ais-2024-01-01.parquet"
)
DEFAULT_DESTINATION = Path("data/raw/ais-2024-01-01.parquet")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_SOURCE_URL)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.url != DEFAULT_SOURCE_URL:
        parser.exit(1, "error: URL is not the approved NOAA 2024-01-01 source\n")

    try:
        sidecar = args.destination.with_name(args.destination.name + ".download.json")
        if sidecar.exists() and not args.force:
            raise FileExistsError(f"download record already exists: {sidecar}")
        record = download_file(args.url, args.destination, overwrite=args.force)
        write_download_record(record, sidecar, overwrite=args.force)
    except (DownloadError, FileExistsError) as error:
        parser.exit(1, f"error: {error}\n")

    print(f"destination: {record.destination}")
    print(f"content_length: {record.content_length}")
    print(f"sha256: {record.sha256}")
    print(f"download_utc: {record.download_utc.isoformat().replace('+00:00', 'Z')}")
    print(f"record: {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
