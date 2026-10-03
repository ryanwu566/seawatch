# SeaWatch rules walkthrough: how a track becomes an alert

Plain-language companion to `docs/rulebook.md` (generated from live thresholds) and the README. Alerts are **candidates for human review**,
never findings of intent or illegality.

## 0. The pipeline in one picture

```text
tracks  ->  clean identities  ->  learn "normal" from history  ->  behaviour rules  ->  events
        ->  fuse into alerts (risk, level)  ->  ML second opinion  ->  [research vessels only] path agent  ->  analyst
```

Three layers with different jobs:

| layer | job | can it raise an alert? | trust |
|---|---|---|---|
| Deterministic rules | spot specific, explainable behaviours | yes, the only layer that does | high: every number is shown |
| ML second opinion | "does the statistics also find this unusual?" | no, only agrees or disagrees | medium: per-region, weak on unseen behaviour |
| Path agent | "what does this slow research-vessel path look like?" | no, advisory | medium: written from five examples |

## 1. Before any rule runs

1. **Identity hygiene** (`identity.py`): drop drift-net / trap beacons and placeholder identities (names with battery percentages such as
   `MJY06010-15-57%`, repeated characters, MMSIs outside 201-775). About 27% of the tracks in the supplied full day were not ships.
2. **Normal behaviour is learned, not drawn** (`context.py`, `learned.py`): where traffic normally flows, which places are ports/anchorages
   (many vessels stopping slowly), how often a vessel normally reports, where *this* vessel habitually dwells, how long its own silences are,
   which vessels routinely visit a zone. Rules ask "unusual for here and for this vessel", not "slow".
3. **Three presets** pick thresholds by data density: default (sparse coast, minute-level), `dense()` (busy fishing waters, minute-level),
   `hourly()` (11 km hourly cells).

## 2. The behaviour rules (what, why suspicious, thresholds, what it ignores)

Thresholds are `default / dense / hourly`. All are adjustable in the Tuning lab.

| rule | what it sees | why it matters | thresholds | ignored as normal | innocent explanations |
|---|---|---|---|---|---|
| **AIS gap** | silence inside covered area | hiding a meeting, transfer or survey | silence 40 / 120 / 360 min | left the area, in port/anchored, sparse reception, vessel's own usual silence, normal for its type | bad reception, equipment fault |
| **Loitering** | slow in a small circle away from port | transfers, retrievals, equipment work | 2 nm radius, 90 min, <= 4 kn / 1.5 nm, 180 min / 5 nm, 480 min | moored all along, waiting at port/anchorage, fishing on a fishing ground, habitual dwell cell | fishing, waiting, weather, drifting |
| **Rendezvous** | two vessels slow and close | ship-to-ship transfer | 0.6 nm, 45 min, <= 3.5 kn / 0.4 nm, 90 min / 6.5 nm, 240 min | both in port/anchorage; fishing pairs discounted | pair trawling, bunkering |
| **Cluster** | many vessels gathered | coordinated gathering | 4 vessels within 3 nm for 40 min / 6, 3 nm, 90 min / 6, 9 nm, 240 min | learned stop areas; alerts over 6 vessels split | fishing grounds, weather shelter |
| **Zone entry** | entry to a protected zone (cable corridor, restricted waters) | anchoring/dragging near cables | any entry (dwell optional) | routine visitors to that zone; pure transit loses 18 risk | licensed local traffic |
| **Position jump / identity conflict** | impossible speed, or one MMSI alternating between places | spoofing or a cloned identity | > 60 kn and > 4 nm / 70 kn and 40 nm (hourly); 3+ alternations | placeholder IDs | GPS glitch, shared MMSI |
| **Status mismatch** | status "anchored/moored" while moving >= 3 kn | stale or falsified status | message-level only | | crew forgot to update |
| **Route deviation** | time in water normal traffic does not use | avoiding observation | 60 / 120 / 720 min at >= 5 kn, < 1.5 vessels per cell historically | busy cells | weather routing, new routes |
| **Dark rendezvous** | one vessel goes dark while another stops where it could have reached | the classic dark transfer | combination of gap + loiter/rendezvous/cluster, reach = half the silence x 15 kn | fishing-majority fleets lose 22 | coincidence |
| **Survey pattern** | >= 4 long legs, each turned back, similar length, stepped sideways, slow | mapping seabed or cable route needs systematic lines | legs >= 3 nm (14 nm hourly), within 24 h (96 h hourly), <= 9 kn | fishing, ferry, tug, pilot, SAR, service, dredger types (and fishing boats recognised by name) | licensed survey, trawling |

## 3. Taiwan survey-threat model (the mentor's factors, as numbers)

Every vessel gets seven yes/no factors with their numbers shown (the factor cards):

| factor | rule of thumb | evidence in our data |
|---|---|---|
| **T** Territory | inside 12 nm (territorial sea), 12-24 nm (contiguous zone), or EEZ approximation | modelled from public coastlines, not legal baselines |
| **V** Velocity | >= 50% of fixes at 2-6 kn (message-level; 5-10 kn kept for hourly) | real survey runs median 4 kn; transit also sits at 5-10 kn, so 5-10 alone cannot tell them apart |
| **A** AIS declaration | name (RESEARCH, SURVEY, KEXUE, XIANG YANG HONG...), registry class Research / Seismic Surveyor, destination | cheap to fake: a hit is strong, a miss proves nothing |
| **D** Destination text | `TOWING ... CPA`, `TOWING 5NM CABLE`, `KEEP 2CPA PASSING` | seen on TAN SUO ER HAO and HAIYANGDIZHI BAHAO |
| **N** Nav status | `RESTRICTED_MANEUVERABILITY` at low speed; brief status switches while under way | cable ships and dredgers also use it; status switching is rare (0.6% of non-fishing vessels) |
| **C** Cable proximity | share of the stretch within 10 nm of a charted cable | public, approximate map |
| **P** Pattern | lawnmower / zig-zag legs | |

How the factors become a name (the first/highest rule for a stretch of track wins):

| rule | meaning | severity | when it becomes HIGH |
|---|---|---|---|
| **R7** towing / slow manoeuvring survey work | destination says towing, or restricted status at low speed on a declared research vessel | 92 inside 24 nm, 80 in EEZ, 60 elsewhere (-8 status only, +10 with a pattern) | towing in the EEZ or inside 24 nm: forced HIGH |
| **R2** pattern inside 24 nm | survey lines in Taiwan's closest waters | 85 (+5 declared, +5 speed) | forced HIGH |
| **R1** declared survey vessel inside 24 nm | the ship says it is research and is inside | 78 TS / 70 CZ (+8 speed); steaming through at transit speed drops to 58 | forced HIGH unless transit |
| **R3** pattern in EEZ | consent may exist | 72 | by score |
| **R4** declared at survey speed in EEZ | | 62 | by score |
| **R5** pattern outside Taiwan's waters | behaviour only | 55 | by score |
| **R6** foreign state vessel inside 12 nm | coast guard etc., a sovereignty matter | 70 | by score |
| **R0** Taiwan-registered survey vessel | expected | 30 | never raised |

Cable proximity adds +4. Detections are never a judgement of consent: AIS cannot show it.

## 4. From events to an alert

1. **Grouping:** events on the same vessels within 12 h (default) / 24 h (hourly) join one alert; alerts of more than 6 vessels split.
2. **Risk (0-99):** for each kind take the best event, `p = kind_weight x severity x (0.6 + 0.4 x confidence) / 100`, then
   `risk = 100 x (1 - product(1 - 0.9 p))`. Several independent kinds add up (noisy-OR); one weak kind stays low; 3+ kinds add 6.
   Kind weights are 0.6 (status mismatch) to 1.0 (rendezvous, zone entry, identity conflict, survey, dark rendezvous).
3. **Discounts and floors:** fishing-majority groups of routine behaviours x0.65 (x0.7 more within 6 nm of a coast); watch-list vessel +8;
   survey R1/R2/R7 floors to HIGH as above; operator feedback multiplies the risk of similar alerts down.
4. **Level:** LOW below, MEDIUM from, HIGH from: default 30 / 45 / 70; `dense` and `hourly` 55 / 70 / 82. Each level has a recommended action
   (HIGH: task an asset or request SAR/RF confirmation; MEDIUM: queue for review in the shift; LOW: keep watching).

## 5. ML second opinion

Per region, trained on the region's own history: **Isolation Forest** (unsupervised "this window looks unlike normal") and
**HistGradientBoosting** (supervised on injected behaviours as weak positives), over 15 portable window features (reporting ratio, speed,
radius, turning, implied speed, familiarity of the water, share in stop areas...). For each alert: `agree` (the models also find it unusual,
with the deviating features) or `rules_only` (lower trust). Measured on the Taiwan hourly data: rules alone flag 329 vessels (17 on injected
events), rules confirmed by ML flag 99 (still 17): about 74% fewer unverified alerts at no recall loss. It cannot create alerts, and a model
from one region does not transfer to another. No model exists yet for the April message-level regions.

## 6. The path agent (research vessels only, advisory)

```text
all vessels -> RESEARCH GATE -> SPEED GATE -> SHAPE FEATURES -> REVIEW -> analyst accepts / rejects
   7,548          32-39            261-279 windows                 87 flagged windows = 41 episodes
```

1. **Research gate:** declares research/survey (name, registry class, towing destination). Restricted status alone does not pass (wind-farm vessels hold it).
2. **Speed gate:** 6-hour windows with median speed <= 7 kn (parked included: holding position can be the work).
3. **Shape features:** speed and its steadiness, straightness, turning, legs, re-traversal, parallel-line share, dwell, extent.
4. **Review** into: survey lines under tow, lawnmower, station-keeping work, tow then transit, fishing, port, drift, transit, unclear; with reasons,
   caveats and a picture. Reviewer = deterministic rules (default) or a language model given the picture, features and AIS context.

Measured only on five analyst-marked examples: 3/5 vessels flagged within +-12 h, 5/5 within +-36 h. It is fitted to those five, so treat it as
a first draft, not a validated detector.

## 7. What each layer can and cannot claim

- Rules: what happened and the numbers. Not why, not whether consent exists.
- ML: whether the pattern is statistically unusual for this region. Not whether it is a threat.
- Agent: what the path looks like. Not intent.
- Known weak spots: hourly recall for dark gaps / loitering / rendezvous; `taiwan-day` noise with one day of history; modelled (not legal)
  12/24/EEZ lines; learned path model unusable until confirmed tracks exist.
