# Real Taiwan data: what is in it, what we learned, what it can and cannot show

## The dataset (`D:\SeaWatch`, set `SEAWATCH_DATA_ROOT` if the drive letter differs)

Global Fishing Watch **"AIS vessel presence"**, 1-29 Sept 2026, area 118-123.5 E / 21.5-26.5 N.
This is **not message-level AIS**: one row per vessel per hour, positioned at the centre of a ~0.1 degree (~11 km) cell, with
no speed, course or navigation status.

| | |
|---|---|
| records | 3.34 M (2.6 M after dropping fishing-gear beacons) |
| vessel IDs | 70,883 (about 25,000 are real ships with >= 6 observed hours) |
| median vessel | only 13 observed hours in 29 days (most are transient or intermittent reporters) |
| identity | MMSI on 99.5% of rows, IMO on only ~10% of vessels |
| mix | fishing/trawlers/gear dominate; cargo ~12% of rows; flags CHN 1.33 M rows, TWN 0.83 M |
| hidden by construction | vessels with AIS off (dark) are absent; positions are +/- 5 km |

Consequences: detectors had to be re-expressed for hourly cell data (`DetectionConfig.hourly()`), speed is estimated from cell
steps, and "gaps" mean "not seen for hours", which for small boats is often just poor reception. Each vessel is therefore
judged against **its own** history and against **peers of its type** before a silence is called unusual.

## What the system learns from this history (Sept 1-25) and applies to the monitored days (26-29)

* traffic baseline per cell; habitual stopping areas (ports, anchorages); each vessel's habitual dwell cells and its own
  normal silence length; the peer distribution of silences per ship type; each zone's routine visitors;
* a supervised and an unsupervised model on window features (`scripts/train_tw_ml.py`).

The monitored scenario is real traffic plus **labelled** added behaviours (injected dark gaps, loitering, spoofed jumps, survey
patterns; scripted rendezvous, dark transfer, cluster, zone entries), always placed where the behaviour would be unusual.
Zones are **illustrative**, not official boundaries. `scripts/tune_tw.py` reports recall and the number of alerts on untouched
real vessels at each alert threshold.

## Held-out benchmark (`data/models/ml_taiwan-gfw_benchmark.json`)

Trained on the two history days before the live window, tested on the four live days:

| method | vessels flagged | on added behaviours | unverified (real, unlabelled) | ROC-AUC |
|---|---|---|---|---|
| Rules | 329 | 17 | 312 | 0.85 |
| Isolation Forest | 536 | 18 | 518 | 0.95 |
| Gradient boosting | 713 | 32 | 681 | 0.99 |
| **Rules confirmed by ML** | **99** | **17** | **82** | - |

Reading it honestly: the supervised model was trained on the same generator of added events as it is tested on for three of the
eight behaviours, and it flags 7% of all vessels, so its recall is flattering. The useful, robust finding is the last row: using the
model to confirm rule alerts removes ~74% of unverified alerts without losing any added behaviour the rules found.

## Real labels in this dataset

* **Sanctions list (OFAC SDN):** 84 listed vessel IDs present, 80 with >= 6 observed hours (31 belong to one Chinese distant-water
  fishing fleet listed under Global Magnitsky; 28 Iran-programme, 9 Russia, 8 terrorism, 5 Ukraine-related, 3 DPRK).
  * Behaviour rules do **not** separate them: in two untouched windows ROC-AUC was 0.49 and 0.49; none of the 36 listed vessel-windows
    (21 + 15) was flagged. A designation is about the hull, not about what it did that week.
  * Identity screen (flag, type, activity; IMO and name excluded; compared only against vessels that broadcast an IMO, since the
    labels were matched on IMO): random folds ROC-AUC 0.95 but **no better than flag + type alone (0.94)**; leave-one-programme-out
    0.75, again equal to the flag + type prior. Flag state and ship type carry the signal; AIS behaviour adds nothing measurable.
* **PRC research vessels (OSINT):** Heritage Foundation Backgrounder 3977 (18 Aug 2026), Table 2, lists seven vessels with IMO
  numbers and June-August survey areas (`data/labels/osint_vessels.csv`). Three are present in September (Jia Geng, Shen Hai Yi Hao,
  Xiang Yang Hong 22); none ran a survey pattern in this month inside the area (Jia Geng and Shen Hai Yi Hao spend days at Xiamen; Xiang Yang
  Hong 22 operates in the northern Taiwan Strait). The reported east/south-of-Taiwan surveys predate this data. The report is a think-tank
  analysis of commercial AIS history, so these are "reported", not proven.

## Survey / zig-zag patterns (`survey.py`, `scripts/find_survey_tracks.py`)

Rule: >= 4 consecutive long legs, each turned back on the previous (U-turn or sharp zig-zag), similar length, stepped sideways,
at towing speed, away from ports; fishing, ferries, tugs etc. are exempt. Searched over all ~25,000 vessels for the whole month:

* **18 patterns on 9 vessels.** Taiwan's research/seismic vessel NEW OCEANRESEARCHER3 (a genuine survey, 5 legs of ~47 nm south of Taiwan).
* **Six China Coast Guard hulls, 15 of the 18 patterns** (CHINACOASTGUARD 1301, 1303, 1304, 1307 near 25.9 N 123.3 E; 1401, 2503 near 22.2-22.8 N
  122.8-123.1 E, the Gagua Ridge area that the Heritage report lists as a survey area) run repeated parallel/zig-zag legs of 30-80 nm for days. The
  pattern is observed; its purpose (patrol, survey, enforcement) cannot be read from AIS. The remaining two are a fishing-named boat
  typed 'other' and an unnamed identity. Device-range and placeholder MMSIs are filtered out.
* Rule recall on synthetic survey shapes sampled at real reporting gaps: lawnmower 69%, zig-zag 67%, race-track 82%.
* A learned shape classifier (`surveyml.py`) is **experimental and not used**: with no confirmed real positives it learned
  "synthetic vs real" shortcuts (it flagged vessels with no long legs). Do not treat it as validated.

## Limits to remember

Hourly presence cannot show identity cloning, short loitering, or anything below ~10 km; absent vessels may be dark or merely out of
reception; the alert volume on real traffic (about 75 a day at the default threshold of 55, about 63 a day at 60) is a policy choice
that the Tuning lab exposes, not a result.

## New data from the mentor

```
python scripts/ingest_mentor_ais.py PATH_TO_CSV_OR_FOLDER [--live-frac 0.2] [--save data/processed/mentor_tracks.parquet]
```

Column names are guessed (MMSI, timestamp, lat/lon, speed, course, name, type, IMO, status, destination). The reporting interval
decides the preset: median >= 30 min is treated as hourly presence, otherwise message-level AIS. The script learns normal traffic
from the first 80% of the time range and runs every rule, including the territory / velocity / declaration / pattern threat model,
on the last 20%, then prints events, what was discarded as normal, the factor combination table and the top alerts. Message-level
data also unlocks declared destination, navigational status and measured speed, which strengthen the A and V factors.
See `docs/rulebook.md` for what every rule means.
