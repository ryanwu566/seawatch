"""Inspect Parquet and GeoParquet metadata without reading all rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.seawatch.adapters.noaa_ais import (
    MetadataInspectionError,
    inspect_parquet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        payload = json.dumps(
            inspect_parquet(args.path).to_dict(), indent=2, sort_keys=True
        )
    except MetadataInspectionError as error:
        parser.exit(1, f"error: {error}\n")

    if args.output is None:
        print(payload)
        return 0
    if args.output.exists() and not args.force:
        parser.exit(1, f"error: destination already exists: {args.output}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload + "\n", encoding="utf-8")
    print(f"inspection: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
