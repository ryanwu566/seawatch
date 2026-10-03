# The three supplied Taiwan AIS files: what they contain and what we learned

| file | content |
|---|---|
| `16992c33-...csv` | one full 2 days (2 to 3 April 2026) of message-level AIS, 21.5-26.5 N / 118-123.5 E: 954,670 reports, 17,258 vessel IDs, median 6 min between reports, with speed, course, navigation status, destination, type, flag |
| `research_vessel_AIS_01.csv` | 1 to 7 April 2026, 73 research / survey-type vessels (registry subtype: Research, Fishery Research, Seismic Surveyor, Subsea Maintenance, Dredger...) over a wide area (18-32 N, 115-127 E) |
| `Research_vessel_AIS_02.csv` | 8 to 16 April 2026, 85 such vessels |

Loaded with `scripts/ingest_mentor_ais.py` (column names are guessed; the reporting interval selects hourly or message-level
handling). `scripts/analyse_research_vessels.py` and `scripts/analyse_day.py` reproduce everything below.

## What the data shows

* **Most "research" vessels are not near Taiwan.** Of 80 usable research-file vessels, only about 8 spend time inside Taiwan's 24 nm or
  EEZ. Several are Taiwan-registered (SUNNY BRIGHT, LEGEND: long stationary work off the east coast; expected domestic activity, rule R0).
* **Real survey runs exist in the data**: HAIYANGDIZHI 9 and 8, HAI YANG SHI YOU 707 and others sail tight lawnmower / racetrack
  patterns, found by the pattern detector (rule R5, outside Taiwan's claimed waters, around 125 E 29 N).
* **Declared research vessels transiting Taiwan's waters**: DONG FANG HONG 3 steamed through the Strait inside Matsu/Kinmen
  limits at 10-12 kn with no pattern; JIA GENG and XIANG YANG HONG 03 clipped Kinmen's 12 nm. These now classify as
  "passing through at transit speed" (risk below the alert line), not as survey.
* **The mentor's speed band does not separate survey from transit.** Inside detected survey runs the median speed was 4 kn
  (69% under 5 kn); 55% of the same vessels' other moving fixes were at 5-10 kn. For message-level data the velocity factor
  now uses 2-6 kn (`DetectionConfig.dense()`); the original 5-10 stays for hourly data.
* **The full-day file is dominated by non-ships**: about 2,700 of 10,200 tracks were drift-net / trap beacons and placeholder
  identities (names such as `MJY06010-15-57%`, battery percentages, repeated characters, MMSIs outside the valid 201-775 range).
  Unfiltered they produced 2,347 rendezvous and 286 clusters; `identity.py` removes them (rendezvous fell to 918 before any other tuning).

## Noise on the dense day (learned from 2 April, monitored 3 April)

| stage | count |
|---|---|
| tracks after identity hygiene | 7,528 |
| rule events | 2,700 |
| alerts, first run with settings tuned on sparse data | 2,724 (725 high) |
| alerts with the dense preset + fishing-fleet / harbour discounts | 251 (40 high) |

Still too many for a human to review: a one-day history is too short to learn each vessel's routine, and fishing-fleet and offshore-
construction activity (wind farm vessels off Changhua) still ranks high. More history will help. Survey threat events on this
day: 10; factor combinations show T 1,534, V 560, A 19, P 8 of 4,170 foreign vessels, and only 3 vessels meet three factors.

## Limits

The research files carry no event labels. "Research vessel" is a registry class, not proof of survey activity or of intent. Only
about 5 vessels show real survey runs, which is too few to train a shape classifier honestly; they are used to check the rules
and measure speed, not to fit a model.

## Reading the AIS the way an analyst does (added after review in kepler.gl)

Four more signals are now part of the model, all from the supplied data:

* **Destination text.** `TOWING KEEP 3NM CPA` (TAN SUO ER HAO), `TOWING 5NM CABLE(S)` (HAIYANGDIZHI BAHAO), `KEEP 2CPA PASSING`:
  the vessel announces a towed sensor array or cable work. Declaration score 0.95; rule R7.
* **Navigation status.** `RESTRICTED_MANEUVERABILITY` held for much of a slow track (HAIYANGDIZHI BAHAO 32%, TAN SUO ER HAO 42%,
  LIAO YUE 94%, HAIYANG DIZHI SI HAO 98%) marks slow manoeuvring work; straight, fast `UNDER_WAY_USING_ENGINE` tracks are transit
  and stay below the alert line. Brief switches away from a steady status while under way (e.g. to `NOT_DEFINED_DEFAULT` and back)
  are counted: 23 of 4,019 non-fishing vessels in the full day, so they are informative.
* **Registry subtype** (`Research`, `Seismic Surveyor`): counted as a declaration (0.7), labelled as a registry class.
* **Cable proximity.** Submarine cable routes (TeleGeography public map, CC BY-NC-SA 4.0, approximate) are on the map, and the
  share of a stretch within 10 nm of a cable is part of the evidence. TAN SUO ER HAO's towing in the EEZ lay on the Asia Direct Cable.

Result on the research fortnight (`taiwan-research` region, nothing injected): 4 alerts. TAN SUO ER HAO towing in Taiwan's EEZ
(HIGH), KE XUE slow manoeuvring in the EEZ, HAIYANGDIZHI BAHAO towing outside Taiwan's waters, and JIA GENG at transit speed
near Kinmen. Chinese research ships working far from Taiwan (seismic and cable-route work near Japan and the Ryukyus) are
classified but stay below the alert line, because they are not in Taiwan's waters.

Regions: `taiwan-research` (default) and `taiwan-day`, built by `scripts/build_taiwan_ais.py`. Map layers: cables, landing points and
Taiwan's modelled 12 nm / 24 nm / EEZ limits (`scripts/build_cables.py`, `scripts/build_zone_lines.py`).
