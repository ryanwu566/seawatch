# SeaWatch rulebook: what makes activity 'suspicious'

_Generated from the live thresholds (hourly ~11 km cells (thresholds scaled up accordingly))._

An alert is a CANDIDATE FOR HUMAN REVIEW, never a finding of intent. Each rule states what was observed, why that is unusual, and the innocent explanations. Several independent weak signals raise risk together (noisy-OR); one weak signal alone stays low.

## 1. Suspected unauthorised survey (the mentor's three factors, plus pattern)

Foreign research or survey ships operating in Taiwan's waters are treated as a potential threat to subsea cables. Three factors identify them; the destination text, navigation status, cable proximity and the zig-zag pattern confirm.

**Legal background.** Reference only: UNCLOS Art. 19(2)(j) makes research or survey in the territorial sea non-innocent passage; Arts. 245-246 require coastal-state consent for research in the territorial sea and EEZ. Taiwan is not a UNCLOS party and its legal status is for lawyers. AIS cannot show whether consent exists, so every result is a candidate for review.

### Factors

* **T - Territory.** Positions inside Taiwan's territorial sea (<= 12 nm), contiguous zone (12-24 nm) or EEZ (<= 200 nm, nearer to Taiwan than to the mainland, Japan or the Philippines). _Reference geometry from Natural Earth coastlines, not legal baselines. A fix within 3 nm of a limit counts as 'on the line' (position error)._
* **V - Velocity.** Typical speed within 5-10 kn for at least half of the track's fixes. _The mentor said '5 to 10 miles per hour or so'; we read it as knots. Measured on 80 real research-type vessels (Apr 2026): inside survey runs the median was 4 kn (69% below 5 kn) while 55% of their transit fixes were at 5-10 kn, so the 5-10 band cannot tell survey from transit. Message-level data therefore uses 2-6 kn; hourly data keeps 5-10 (speed is estimated from cell steps). Adjustable in the Tuning lab._
* **A - AIS declaration.** The vessel itself signals survey or research: name containing a survey/research designation (RESEARCH, SURVEY, KEXUE, XIANG YANG HONG, HAIYANG DIZHI ...), a survey destination, or a feed class of seismic vessel (weak). _Strong evidence when present (score >= 0.6) but proves little when absent; names are cheap to change._
* **D - Destination text.** The destination field announces towing or cable work: e.g. 'TOWING KEEP 3NM CPA', 'TOWING 5NM CABLE', 'KEEP 2CPA PASSING'. A vessel towing a sensor array asks others to keep clear. _Seen in the supplied data on TAN SUO ER HAO and HAIYANGDIZHI BAHAO. Strongest single AIS signal (declaration score 0.95)._
* **N - Navigation status.** 'Restricted in ability to manoeuvre' held for a large share of the track at low speed (slow manoeuvring over a cable), or the status briefly switching away from the steady value and back while under way (e.g. UNDER_WAY_USING_ENGINE -> NOT_DEFINED_DEFAULT -> back). _Cable-layers and dredgers use the same status, so it is evidence, not proof. Status switching is rare: about 0.6% of non-fishing vessels in a full day._
* **C - Cable proximity.** Share of the stretch within 10 nm of a charted submarine cable (TeleGeography public map, approximate). _Adds +4 severity when at least 20% of the stretch is near a cable._
* **P - Pattern.** Survey-shaped zig-zag / lawnmower track (see the survey detector above). _Independent of what the vessel claims; a ship that hides its role still has to sail the lines._

### Rules

| rule | name | severity | needs | meaning |
|---|---|---|---|---|
| R2 | Pattern in territorial sea / contiguous zone | 85 (+5 if declared, +5 if survey speed) | T + P | Foreign vessel sailing survey lines inside Taiwan's 24 nm: highest-confidence rule. |
| R3 | Pattern in the EEZ | 72 | EEZ + P | Survey lines in the EEZ. Consent may exist; review. |
| R5 | Pattern outside Taiwan's claimed waters | 55 | P | Survey lines near Taiwan but outside claimed waters; informational context. |
| R1 | Declared survey vessel in territorial sea / contiguous zone | 78 in TS, 70 in CZ (+8 survey speed) | T + A | The ship says it is a research vessel and is inside Taiwan's 24 nm; easy case. |
| R4 | Declared survey vessel working at survey speed in the EEZ | 62 | A + V (>= 60% of fixes) + 6 EEZ fixes | Declared and slow for a long time in the EEZ, without a clear pattern. |
| R7 | Towing a survey array / slow manoeuvring survey work | 92 in 24 nm, 80 in EEZ, 60 elsewhere (-8 if only restricted-manoeuvre status, +10 with a pattern) | D (towing text) or N (restricted manoeuvre >= 20%) with A | The vessel announces towing / cable work, or manoeuvres slowly in restricted status. Towing in the EEZ is raised to at least MEDIUM; inside 24 nm to HIGH. |
| R6 | Foreign state vessel in the territorial sea | 70 (+6 survey speed) | >= 2 clear TS fixes + state-vessel name | Coast guard, maritime safety or fisheries enforcement ship of another state inside the 12 nm. Not survey, but a sovereignty matter. |
| R0 | Taiwan-registered survey vessel | 30 (not raised) | MMSI 416xxxxxx | Domestic research is expected; recorded, never alerted. |

Single factors are common (many foreign ships cross these waters; many move at 5-10 kn). The combination is rare. The Assessment view shows how many vessels meet each combination.

## 2. Behaviour detectors

### Reporting gap (going dark)

* **What it sees:** A vessel stops being heard for at least 360 min inside the covered area and reappears (or never does).
* **Why it matters:** Switching AIS off is how vessels hide meetings, transfers and survey work.
* **Thresholds:** minimum silence (min) = 360; max implied speed across gap (kn) = 40; 'stayed put' radius (nm) = 12; area-edge margin (nm) = 12
* **Discarded as noise:** left or re-entered the monitored area; in port or at anchor; short silence in sparse reception; this vessel's own routine (its p95 silence); ordinary for its ship type (peer percentile)
* **Innocent explanations:** poor satellite or shore reception; equipment fault; vessel left the covered area; port or anchorage shadowing
* **Data needs / limits:** Needs reception coverage; hourly feeds can only say 'not seen'.

### Loitering / unusual stopping

* **What it sees:** Slow (<= 4 kn) inside a 5 nm circle for 480+ min, away from port.
* **Why it matters:** Stopping in open water is where transfers, retrievals and equipment work happen.
* **Thresholds:** minimum dwell (min) = 480; radius (nm) = 5; max speed (kn) = 4
* **Discarded as noise:** moored for the whole observation; waiting at port or anchorage; fishing on a fishing ground; this vessel's habitual dwell cell
* **Innocent explanations:** fishing; waiting for a berth or weather; drifting engine trouble; legitimate survey or cable work
* **Data needs / limits:** Learns stop areas from history so ports and anchorages are not alarms.

### Rendezvous / dark transfer

* **What it sees:** Two vessels slow and within 6.5 nm for 240+ min; stronger when one or both went dark around it.
* **Why it matters:** Ship-to-ship transfer of cargo, fuel or people; sanctions evasion and smuggling.
* **Thresholds:** meeting distance (nm) = 6.5; minimum meeting time (min) = 240; max speed (kn) = 3.5
* **Discarded as noise:** both in port or anchorage; fishing-fleet gatherings (risk reduced)
* **Innocent explanations:** fishing pairs; bunkering at an anchorage; tow or escort; crew transfer
* **Data needs / limits:** Position accuracy matters: at hourly ~11 km cells the distance test is loosened.

### Clustering

* **What it sees:** 6+ vessels within 9 nm for 240+ min away from ports.
* **Why it matters:** Coordinated gatherings (maritime militia, blockade rehearsal, fleet at a cable site).
* **Thresholds:** vessels = 6; distance (nm) = 9; minutes = 240
* **Discarded as noise:** inside a learned stop area; alerts larger than 6 vessels are split by lead vessel to stay reviewable
* **Innocent explanations:** fishing grounds; weather shelter; regatta or exercise
* **Data needs / limits:** Needs traffic density context.

### Restricted-zone entry

* **What it sees:** A vessel enters a protected zone (cable corridor, restricted waters, port area).
* **Why it matters:** Anchoring or dragging near cables and sensitive areas is the classic sabotage and survey pre-condition.
* **Thresholds:** minimum dwell (min) = 0
* **Discarded as noise:** routine visitor to this zone (learned from history); transit discount (-18 risk) when only crossing
* **Innocent explanations:** licensed local traffic; fishing boats on a normal route; operator allow-listed vessels
* **Data needs / limits:** Zones are illustrative; replace with official polygons.

### Position jump / identity conflict

* **What it sees:** A position change implying > 70 kn and > 40 nm, or the same identity alternating between places 3+ times.
* **Why it matters:** Spoofed or cloned AIS identities.
* **Thresholds:** implied speed (kn) = 70; distance (nm) = 40; alternations = 3
* **Discarded as noise:** device-range and placeholder MMSIs
* **Innocent explanations:** GPS glitch; two ships sharing a mis-set MMSI; receiver timing error
* **Data needs / limits:** Weak on hourly data (cell positions are +/- 5 km).

### Status / behaviour mismatch

* **What it sees:** Declared navigational status contradicts movement (e.g. 'at anchor' while making 12 kn).
* **Why it matters:** Inconsistent self-reports suggest manipulated or careless AIS.
* **Innocent explanations:** crew forgot to update status
* **Data needs / limits:** Message-level AIS only.

### Route deviation

* **What it sees:** 720+ min at >= 5 kn through water that historic traffic rarely uses (< 1.5 vessels per cell).
* **Why it matters:** Off-lane transit can mean avoiding observation or surveying new ground.
* **Thresholds:** minutes = 720; familiar-water cut-off = 1.5
* **Discarded as noise:** cells busy in the learned baseline
* **Innocent explanations:** weather routing; fishing; new routes
* **Data needs / limits:** Needs a baseline of normal traffic.

### Survey-shaped track (zig-zag / lawnmower)

* **What it sees:** 4+ long legs (>= 14 nm), each turned back on the last, similar length, stepped sideways, slow, within 96 h.
* **Why it matters:** Scanning the seabed (cables, resources) requires systematic parallel passes; ordinary transit never looks like this.
* **Thresholds:** legs = 4; leg length (nm) = 14; window (h) = 96
* **Discarded as noise:** fishing, ferry, tug, pilot, SAR, service and dredger types are exempt; turn points mostly in benign (port) areas
* **Innocent explanations:** genuine research and cable-route surveys by licensed parties; search-and-rescue patterns; trawling runs
* **Data needs / limits:** Measured recall on synthetic shapes: lawnmower 69%, zig-zag 67%, race-track 82%.

## 3. From events to alerts

* **risk:** Event severity x detector weight x confidence, combined across independent events with noisy-OR so extra evidence adds but never exceeds 100.
* **levels:** {'alert shown from': 55.0, 'medium': 70.0, 'high': 82.0}
* **grouping:** Events on the same vessel(s) within the link window are merged into one alert so a story reads as one item.
* **ml:** A second, statistical opinion (Isolation Forest + gradient boosting) scores the same time window. 'Agree' means both consider it unusual; 'rules only' lowers trust.
* **watch:** Vessels on a cited research-vessel or sanctions list get +8 risk and a caveat. They are matched on IMO / MMSI only; a listing is about the hull, not about this week's behaviour.
* **feedback:** Operators mark false alarms, add notes, allow-list vessels and tune thresholds; those decisions suppress or reshape later alerts.
