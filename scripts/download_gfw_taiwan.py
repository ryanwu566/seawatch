import os
import time
from datetime import date, timedelta
from pathlib import Path

import requests


# ============================================================
# SeaWatch - Global Fishing Watch Taiwan Historical Downloader
# ============================================================


# ------------------------------------------------------------
# 1. Find SeaWatch data root
#
# Priority:
#   1. SEAWATCH_DATA_ROOT environment variable
#   2. Automatically search D: ~ Z: for <drive>:\SeaWatch
# ------------------------------------------------------------

def find_data_root() -> Path:
    env_root = os.getenv("SEAWATCH_DATA_ROOT")

    if env_root:
        path = Path(env_root)

        if path.exists():
            print(f"Using SEAWATCH_DATA_ROOT: {path}")
            return path

        raise RuntimeError(
            f"SEAWATCH_DATA_ROOT exists in environment but path was not found: {path}"
        )

    # Automatically detect external SSD
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = Path(f"{letter}:\\SeaWatch")

        if candidate.exists():
            print(f"Auto-detected SeaWatch SSD: {candidate}")
            return candidate

    raise RuntimeError(
        "Cannot find SeaWatch data folder.\n"
        "\n"
        "Set it manually in PowerShell, for example:\n"
        '$env:SEAWATCH_DATA_ROOT="<external-drive>:\\SeaWatch"'
    )


DATA_ROOT = find_data_root()


# ------------------------------------------------------------
# 2. Global Fishing Watch token
# ------------------------------------------------------------

TOKEN = os.getenv("GFW_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "GFW_TOKEN NOT FOUND.\n"
        "\n"
        "Set it in PowerShell first:\n"
        '$env:GFW_TOKEN="YOUR_TOKEN"'
    )


# ------------------------------------------------------------
# 3. GFW API endpoint
# ------------------------------------------------------------

URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"


# ------------------------------------------------------------
# 4. Taiwan Area of Interest
#
# Longitude:
#   118.0E ~ 123.5E
#
# Latitude:
#   21.5N ~ 26.5N
# ------------------------------------------------------------

GEOJSON = {
    "type": "Polygon",
    "coordinates": [[
        [118.0, 21.5],
        [123.5, 21.5],
        [123.5, 26.5],
        [118.0, 26.5],
        [118.0, 21.5]
    ]]
}


# ------------------------------------------------------------
# 5. Download date range
#
# END_DATE is exclusive.
#
# Current setting:
#   Download 2026-09-01 through 2026-09-29
# ------------------------------------------------------------

START_DATE = date(2026, 9, 1)
END_DATE = date(2026, 9, 30)


# ------------------------------------------------------------
# 6. Output directory
# ------------------------------------------------------------

OUTPUT_DIR = (
    DATA_ROOT
    / "ais"
    / "historical"
    / "raw"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ------------------------------------------------------------
# 7. HTTP headers
# ------------------------------------------------------------

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}


# ------------------------------------------------------------
# 8. Helper: download one day
# ------------------------------------------------------------

def download_day(current_date: date) -> bool:
    next_day = current_date + timedelta(days=1)

    output_file = (
        OUTPUT_DIR
        / f"gfw_taiwan_{current_date.isoformat()}_hourly.json"
    )

    print()
    print("=" * 70)
    print(f"SeaWatch GFW Download - {current_date}")
    print("=" * 70)

    # --------------------------------------------------------
    # Skip files that already exist
    # --------------------------------------------------------

    if output_file.exists() and output_file.stat().st_size > 1000:
        size_mb = output_file.stat().st_size / 1024 / 1024

        print("Already downloaded.")
        print(f"File: {output_file}")
        print(f"Size: {size_mb:.2f} MB")

        return True


    # --------------------------------------------------------
    # API parameters
    # --------------------------------------------------------

    params = {
        "datasets[0]": "public-global-presence:latest",

        "date-range": (
            f"{current_date.isoformat()},"
            f"{next_day.isoformat()}"
        ),

        "temporal-resolution": "HOURLY",

        "spatial-resolution": "LOW",

        "group-by": "VESSEL_ID",

        "format": "JSON"
    }


    # --------------------------------------------------------
    # Retry up to 3 times
    # --------------------------------------------------------

    for attempt in range(1, 4):

        print()
        print(f"Attempt {attempt}/3")
        print("Connecting to Global Fishing Watch...")

        try:

            response = requests.post(
                URL,
                params=params,
                headers=HEADERS,
                json={"geojson": GEOJSON},
                timeout=300
            )


            print(
                f"HTTP status: {response.status_code}"
            )


            # ------------------------------------------------
            # Success
            # ------------------------------------------------

            if response.status_code == 200:

                temp_file = output_file.with_suffix(".json.part")

                with open(temp_file, "wb") as f:
                    f.write(response.content)

                # Rename only after the download is complete
                temp_file.replace(output_file)

                size_mb = (
                    output_file.stat().st_size
                    / 1024
                    / 1024
                )

                print()
                print("DOWNLOAD COMPLETE")
                print(f"Saved to: {output_file}")
                print(f"File size: {size_mb:.2f} MB")

                return True


            # ------------------------------------------------
            # Rate limit
            # ------------------------------------------------

            if response.status_code == 429:

                print(
                    "GFW rate limit reached."
                )

                print(
                    "Waiting 60 seconds before retry..."
                )

                time.sleep(60)

                continue


            # ------------------------------------------------
            # Authentication errors
            # ------------------------------------------------

            if response.status_code in (401, 403):

                print()
                print("Authentication failed.")

                print(
                    "Check whether GFW_TOKEN is valid."
                )

                print(
                    response.text[:2000]
                )

                return False


            # ------------------------------------------------
            # Other API errors
            # ------------------------------------------------

            print()
            print("GFW API ERROR")

            print(
                response.text[:2000]
            )

            print()
            print(
                "Waiting 20 seconds before retry..."
            )

            time.sleep(20)


        except requests.Timeout:

            print()
            print("Request timed out.")

            print(
                "Waiting 20 seconds before retry..."
            )

            time.sleep(20)


        except requests.RequestException as exc:

            print()
            print("Network error:")

            print(exc)

            print()
            print(
                "Waiting 20 seconds before retry..."
            )

            time.sleep(20)


    # --------------------------------------------------------
    # Failed all retries
    # --------------------------------------------------------

    print()
    print(
        f"FAILED TO DOWNLOAD: {current_date}"
    )

    return False


# ------------------------------------------------------------
# 9. Main
# ------------------------------------------------------------

def main():

    print()
    print("=" * 70)
    print("SeaWatch Taiwan Historical AIS Downloader")
    print("=" * 70)

    print()
    print("Data root:")
    print(DATA_ROOT)

    print()
    print("Output:")
    print(OUTPUT_DIR)

    print()
    print("Taiwan AOI:")
    print("Longitude: 118.0E ~ 123.5E")
    print("Latitude : 21.5N ~ 26.5N")

    print()
    print("Dataset:")
    print("public-global-presence:latest")

    print()
    print("Resolution:")
    print("Temporal: HOURLY")
    print("Spatial : LOW")

    print()
    print("Date range:")
    print(f"{START_DATE} ~ {END_DATE - timedelta(days=1)}")

    print()


    current_date = START_DATE

    successful_days = 0
    failed_days = []


    while current_date < END_DATE:

        success = download_day(current_date)

        if success:
            successful_days += 1

        else:
            failed_days.append(current_date.isoformat())

            # Stop so we don't blindly continue after a major error
            print()
            print(
                "Stopping download because a day failed."
            )

            break


        current_date += timedelta(days=1)


        # Give GFW a short break between reports
        if current_date < END_DATE:
            print()
            print(
                "Waiting 3 seconds..."
            )

            time.sleep(3)


    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SeaWatch GFW Download Summary")
    print("=" * 70)

    print(
        f"Successful days: {successful_days}"
    )

    if failed_days:

        print(
            "Failed days:"
        )

        for failed in failed_days:
            print(
                f"  - {failed}"
            )

    else:

        print(
            "Failed days: 0"
        )


    print()
    print(
        f"Data location: {OUTPUT_DIR}"
    )

    print()
    print("DONE")


# ------------------------------------------------------------
# 10. Run
# ------------------------------------------------------------

if __name__ == "__main__":
    main()
