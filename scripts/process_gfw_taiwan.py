import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


# ============================================================
# SeaWatch - GFW Historical Data Processor
#
# Convert:
#   GFW daily JSON
#       ->
#   compressed daily Parquet
#
# Input:
#   <SeaWatch>\ais\historical\raw\
#
# Output:
#   <SeaWatch>\ais\historical\processed\
#
# Portable:
#   Works even if the external SSD changes from D: to E:/F:/...
# ============================================================


# ============================================================
# 1. Locate SeaWatch data root
# ============================================================

def find_data_root() -> Path:
    # First use environment variable if available
    env_root = os.getenv("SEAWATCH_DATA_ROOT")

    if env_root:
        root = Path(env_root)

        if root.exists():
            print(f"Using SEAWATCH_DATA_ROOT: {root}")
            return root

        raise RuntimeError(
            f"SEAWATCH_DATA_ROOT points to a missing folder: {root}"
        )

    # Otherwise automatically look for the external SSD
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = Path(f"{letter}:\\SeaWatch")

        if candidate.exists():
            print(f"Auto-detected SeaWatch SSD: {candidate}")
            return candidate

    raise RuntimeError(
        "SeaWatch data folder was not found.\n"
        "\n"
        "Set it in PowerShell, for example:\n"
        '$env:SEAWATCH_DATA_ROOT="<external-drive>:\\SeaWatch"'
    )


DATA_ROOT = find_data_root()


# ============================================================
# 2. Paths
# ============================================================

RAW_DIR = (
    DATA_ROOT
    / "ais"
    / "historical"
    / "raw"
)

PROCESSED_DIR = (
    DATA_ROOT
    / "ais"
    / "historical"
    / "processed"
)

DAILY_DIR = (
    PROCESSED_DIR
    / "daily"
)

PROCESSED_DIR.mkdir(
    parents=True,
    exist_ok=True
)

DAILY_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# 3. Output schema
# ============================================================

SCHEMA = pa.schema([
    ("date", pa.string()),
    ("entryTimestamp", pa.string()),
    ("exitTimestamp", pa.string()),

    ("lat", pa.float64()),
    ("lon", pa.float64()),
    ("hours", pa.float64()),

    ("vesselId", pa.string()),
    ("mmsi", pa.string()),
    ("shipName", pa.string()),
    ("flag", pa.string()),
    ("vesselType", pa.string()),
    ("geartype", pa.string()),
    ("imo", pa.string()),
    ("callsign", pa.string()),

    ("firstTransmissionDate", pa.string()),
    ("lastTransmissionDate", pa.string()),

    ("dataset", pa.string()),
    ("sourceDataset", pa.string()),
    ("sourceFile", pa.string()),
])


# ============================================================
# 4. Normalization helpers
# ============================================================

def clean_string(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def clean_float(value):
    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


# ============================================================
# 5. Read one GFW JSON file
# ============================================================

def extract_records(json_path: Path):
    print("Reading JSON...")

    with json_path.open(
        "r",
        encoding="utf-8"
    ) as file:
        payload = json.load(file)

    entries = payload.get(
        "entries",
        []
    )

    records = []

    # GFW structure:
    #
    # "entries": [
    #   {
    #     "public-global-presence:v4.0": [
    #        {...},
    #        {...}
    #     ]
    #   }
    # ]
    #
    # We deliberately do not hard-code v4.0.

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        for source_dataset, items in entry.items():

            if not isinstance(items, list):
                continue

            for item in items:

                if not isinstance(item, dict):
                    continue

                record = {
                    "date":
                        clean_string(
                            item.get("date")
                        ),

                    "entryTimestamp":
                        clean_string(
                            item.get("entryTimestamp")
                        ),

                    "exitTimestamp":
                        clean_string(
                            item.get("exitTimestamp")
                        ),

                    "lat":
                        clean_float(
                            item.get("lat")
                        ),

                    "lon":
                        clean_float(
                            item.get("lon")
                        ),

                    "hours":
                        clean_float(
                            item.get("hours")
                        ),

                    "vesselId":
                        clean_string(
                            item.get("vesselId")
                        ),

                    # Keep MMSI as STRING.
                    # It is an identifier, not something we calculate.
                    "mmsi":
                        clean_string(
                            item.get("mmsi")
                        ),

                    "shipName":
                        clean_string(
                            item.get("shipName")
                        ),

                    "flag":
                        clean_string(
                            item.get("flag")
                        ),

                    "vesselType":
                        clean_string(
                            item.get("vesselType")
                        ),

                    "geartype":
                        clean_string(
                            item.get("geartype")
                        ),

                    "imo":
                        clean_string(
                            item.get("imo")
                        ),

                    "callsign":
                        clean_string(
                            item.get("callsign")
                        ),

                    "firstTransmissionDate":
                        clean_string(
                            item.get(
                                "firstTransmissionDate"
                            )
                        ),

                    "lastTransmissionDate":
                        clean_string(
                            item.get(
                                "lastTransmissionDate"
                            )
                        ),

                    "dataset":
                        clean_string(
                            item.get("dataset")
                        ),

                    "sourceDataset":
                        clean_string(
                            source_dataset
                        ),

                    "sourceFile":
                        json_path.name,
                }

                records.append(
                    record
                )

    return records


# ============================================================
# 6. Process one day
# ============================================================

def process_one_file(json_path: Path):
    output_name = (
        json_path.name
        .replace(
            "_hourly.json",
            ".parquet"
        )
    )

    output_path = (
        DAILY_DIR
        / output_name
    )

    print()
    print("=" * 70)
    print(f"Processing: {json_path.name}")
    print("=" * 70)

    # --------------------------------------------------------
    # Skip already processed files
    # --------------------------------------------------------

    if (
        output_path.exists()
        and output_path.stat().st_size > 1000
    ):
        metadata = pq.read_metadata(
            output_path
        )

        size_mb = (
            output_path.stat().st_size
            / 1024
            / 1024
        )

        print("Already processed.")
        print(
            f"Rows: {metadata.num_rows:,}"
        )
        print(
            f"Size: {size_mb:.2f} MB"
        )

        return {
            "inputFile": json_path.name,
            "outputFile": output_path.name,
            "rows": metadata.num_rows,
            "rawBytes": json_path.stat().st_size,
            "parquetBytes": output_path.stat().st_size,
        }


    # --------------------------------------------------------
    # Read JSON
    # --------------------------------------------------------

    records = extract_records(
        json_path
    )

    print(
        f"Records found: {len(records):,}"
    )


    if not records:
        print(
            "WARNING: No records found."
        )

        return {
            "inputFile": json_path.name,
            "outputFile": None,
            "rows": 0,
            "rawBytes": json_path.stat().st_size,
            "parquetBytes": 0,
        }


    # --------------------------------------------------------
    # Build Arrow table
    # --------------------------------------------------------

    print(
        "Creating Arrow table..."
    )

    table = pa.Table.from_pylist(
        records,
        schema=SCHEMA
    )


    # --------------------------------------------------------
    # Write Parquet safely using .part temporary file
    # --------------------------------------------------------

    temp_path = Path(
        str(output_path) + ".part"
    )

    if temp_path.exists():
        temp_path.unlink()


    print(
        "Writing ZSTD compressed Parquet..."
    )

    pq.write_table(
        table,
        temp_path,
        compression="zstd",
        write_statistics=True,
        row_group_size=100_000,
    )


    # Only replace final file after successful write
    temp_path.replace(
        output_path
    )


    raw_size = (
        json_path.stat().st_size
    )

    parquet_size = (
        output_path.stat().st_size
    )

    raw_mb = (
        raw_size
        / 1024
        / 1024
    )

    parquet_mb = (
        parquet_size
        / 1024
        / 1024
    )

    if raw_size > 0:
        reduction = (
            100
            * (
                1
                - parquet_size
                / raw_size
            )
        )
    else:
        reduction = 0


    print()
    print("PARQUET COMPLETE")

    print(
        f"Rows: {len(records):,}"
    )

    print(
        f"JSON: {raw_mb:.2f} MB"
    )

    print(
        f"Parquet: {parquet_mb:.2f} MB"
    )

    print(
        f"Storage reduction: {reduction:.1f}%"
    )


    return {
        "inputFile": json_path.name,
        "outputFile": output_path.name,
        "rows": len(records),
        "rawBytes": raw_size,
        "parquetBytes": parquet_size,
    }


# ============================================================
# 7. Build lightweight vessel index
# ============================================================

def build_vessel_index(parquet_files):
    print()
    print("=" * 70)
    print("Building vessel index")
    print("=" * 70)


    vessels = {}


    columns = [
        "vesselId",
        "mmsi",
        "shipName",
        "flag",
        "vesselType",
        "geartype",
        "imo",
        "callsign",
        "date",
    ]


    for parquet_path in parquet_files:

        print(
            f"Reading: {parquet_path.name}"
        )

        table = pq.read_table(
            parquet_path,
            columns=columns
        )


        for row in table.to_pylist():

            vessel_id = row.get(
                "vesselId"
            )

            if not vessel_id:
                continue


            if vessel_id not in vessels:

                vessels[vessel_id] = {
                    "vesselId": vessel_id,
                    "mmsi": None,
                    "shipName": None,
                    "flag": None,
                    "vesselType": None,
                    "geartype": None,
                    "imo": None,
                    "callsign": None,
                    "firstDate": None,
                    "lastDate": None,
                    "observationCount": 0,
                }


            vessel = vessels[
                vessel_id
            ]


            # Fill useful identity fields whenever available
            identity_fields = [
                "mmsi",
                "shipName",
                "flag",
                "vesselType",
                "geartype",
                "imo",
                "callsign",
            ]


            for field in identity_fields:

                value = row.get(
                    field
                )

                if value:
                    vessel[field] = value


            record_date = row.get(
                "date"
            )


            if record_date:

                if (
                    vessel["firstDate"] is None
                    or record_date
                    < vessel["firstDate"]
                ):
                    vessel[
                        "firstDate"
                    ] = record_date


                if (
                    vessel["lastDate"] is None
                    or record_date
                    > vessel["lastDate"]
                ):
                    vessel[
                        "lastDate"
                    ] = record_date


            vessel[
                "observationCount"
            ] += 1


    records = list(
        vessels.values()
    )


    records.sort(
        key=lambda item: (
            item.get("mmsi") or "",
            item.get("vesselId") or "",
        )
    )


    index_schema = pa.schema([
        ("vesselId", pa.string()),
        ("mmsi", pa.string()),
        ("shipName", pa.string()),
        ("flag", pa.string()),
        ("vesselType", pa.string()),
        ("geartype", pa.string()),
        ("imo", pa.string()),
        ("callsign", pa.string()),
        ("firstDate", pa.string()),
        ("lastDate", pa.string()),
        ("observationCount", pa.int64()),
    ])


    table = pa.Table.from_pylist(
        records,
        schema=index_schema
    )


    output_path = (
        PROCESSED_DIR
        / "vessel_index.parquet"
    )


    temp_path = Path(
        str(output_path) + ".part"
    )

    if temp_path.exists():
        temp_path.unlink()


    pq.write_table(
        table,
        temp_path,
        compression="zstd",
        write_statistics=True,
    )


    temp_path.replace(
        output_path
    )


    print()
    print(
        f"Unique vessels: {len(records):,}"
    )

    print(
        f"Saved: {output_path}"
    )


    return len(records)


# ============================================================
# 8. Main
# ============================================================

def main():
    print()
    print("=" * 70)
    print("SeaWatch GFW JSON -> Parquet Processor")
    print("=" * 70)

    print()
    print("Data root:")
    print(DATA_ROOT)

    print()
    print("Raw directory:")
    print(RAW_DIR)

    print()
    print("Processed directory:")
    print(PROCESSED_DIR)


    # --------------------------------------------------------
    # Verify raw folder
    # --------------------------------------------------------

    if not RAW_DIR.exists():
        raise RuntimeError(
            f"Raw folder does not exist: {RAW_DIR}"
        )


    json_files = sorted(
        RAW_DIR.glob(
            "gfw_taiwan_2026-09-*_hourly.json"
        )
    )


    print()
    print(
        f"Raw JSON files found: {len(json_files)}"
    )


    if not json_files:
        raise RuntimeError(
            "No GFW JSON files were found."
        )


    if len(json_files) != 29:
        print()
        print(
            "WARNING:"
        )

        print(
            "Expected 29 September files, "
            f"but found {len(json_files)}."
        )


    # --------------------------------------------------------
    # Process all daily files
    # --------------------------------------------------------

    results = []


    for json_path in json_files:

        result = process_one_file(
            json_path
        )

        results.append(
            result
        )


    # --------------------------------------------------------
    # Collect generated Parquet files
    # --------------------------------------------------------

    parquet_files = sorted(
        DAILY_DIR.glob(
            "gfw_taiwan_2026-09-*.parquet"
        )
    )


    print()
    print(
        f"Daily Parquet files: {len(parquet_files)}"
    )


    # --------------------------------------------------------
    # Vessel index
    # --------------------------------------------------------

    unique_vessels = build_vessel_index(
        parquet_files
    )


    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    total_rows = sum(
        item["rows"]
        for item in results
    )

    raw_bytes = sum(
        item["rawBytes"]
        for item in results
    )

    parquet_bytes = sum(
        item["parquetBytes"]
        for item in results
    )


    if raw_bytes > 0:

        storage_reduction = (
            100
            * (
                1
                - parquet_bytes
                / raw_bytes
            )
        )

    else:
        storage_reduction = 0


    # --------------------------------------------------------
    # Summary JSON
    # --------------------------------------------------------

    summary = {
        "name":
            "SeaWatch Taiwan GFW Historical Dataset",

        "source":
            "Global Fishing Watch Global AIS Vessel Presence",

        "purpose":
            "Historical maritime traffic context and vessel baseline",

        "areaOfInterest": {
            "west": 118.0,
            "east": 123.5,
            "south": 21.5,
            "north": 26.5,
        },

        "dateRange": {
            "start": "2026-09-01",
            "end": "2026-09-29",
        },

        "temporalResolution":
            "HOURLY",

        "spatialResolution":
            "LOW",

        "groupBy":
            "VESSEL_ID",

        "rawJsonFiles":
            len(json_files),

        "dailyParquetFiles":
            len(parquet_files),

        "totalRecords":
            total_rows,

        "uniqueVessels":
            unique_vessels,

        "rawBytes":
            raw_bytes,

        "parquetBytes":
            parquet_bytes,

        "storageReductionPercent":
            round(
                storage_reduction,
                2
            ),

        "generatedAtUtc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "importantNote":
            (
                "This is Global Fishing Watch "
                "AIS Vessel Presence data. "
                "It is not raw AIS message-level data."
            ),
    }


    summary_path = (
        PROCESSED_DIR
        / "dataset_summary.json"
    )


    with summary_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            summary,
            file,
            ensure_ascii=False,
            indent=2
        )


    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SeaWatch Processing Complete")
    print("=" * 70)

    print()
    print(
        f"Raw JSON files: {len(json_files)}"
    )

    print(
        f"Daily Parquet files: {len(parquet_files)}"
    )

    print(
        f"Total records: {total_rows:,}"
    )

    print(
        f"Unique vessels: {unique_vessels:,}"
    )

    print()

    print(
        f"Raw size: "
        f"{raw_bytes / 1024 / 1024 / 1024:.2f} GB"
    )

    print(
        f"Parquet size: "
        f"{parquet_bytes / 1024 / 1024:.2f} MB"
    )

    print(
        f"Storage reduction: "
        f"{storage_reduction:.1f}%"
    )

    print()
    print("Daily Parquet:")
    print(DAILY_DIR)

    print()
    print("Vessel index:")
    print(
        PROCESSED_DIR
        / "vessel_index.parquet"
    )

    print()
    print("Dataset summary:")
    print(summary_path)

    print()
    print("DONE")


# ============================================================
# 9. Entry point
# ============================================================

if __name__ == "__main__":
    main()
