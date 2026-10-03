# SeaWatch detection stack

Behaviour detection over AIS tracks: **rules** (explainable, one detector per behaviour) plus a
**statistical/ML second opinion**, fused into risk-ranked alerts that an operator reviews.
Alerts are candidates for human review - never findings of intent.

## Run it

```powershell
python scripts/setup_sfbay_data.py      # once: NOAA public AIS (3 days) cropped to San Francisco Bay (~700 MB download)
python scripts/train_region_ml.py       # optional, ~2 min: ML second opinion for SF Bay
.\scripts\run_demo.ps1                  # API :8000 + web :5173
```

Without the SF data the app falls back to the fully simulated Taiwan world. Set `SEAWATCH_REGION=taiwan|sf-bay`
to choose the start-up region; the header drop-down switches it live.

## Regions

| Region | Background traffic | Added behaviours |
|---|---|---|
| `sf-bay` | **Real** recorded AIS, 3 Jan 2024 (NOAA, CC0). Models learn from 1-2 Jan. | Injected into real vessels: dark gap, loitering, spoofed jump, MMSI clone. Scripted vessels in real water lanes: rendezvous, dark ship-to-ship transfer, cluster, restricted/cable zone entries. |
| `taiwan` | Simulated (receiver coverage, benign look-alikes, satellite-only gaps). | Same set plus route deviation. |

Ground truth exists only for added behaviours; alerts on untouched real vessels are **unverified**, not "false".

## Detectors (`apps/api/seawatch/detection/detectors.py`)

AIS gap (coverage-aware, ignores berth power-downs and area-edge exits) - loitering (stay-point; ignores berthed,
anchored-by-status, service vessels) - rendezvous and cluster - zone entry (learns each zone's routine visitors) -
position jump and MMSI clone (kinematic plausibility) - navigational-status mismatch - pattern-of-life route deviation.
Every event carries evidence, benign explanations and what AIS cannot tell you.

## Region context is learned, not drawn (`learned.py`, `context.py`)

Habitual stopping areas, normal reporting rate/coverage and normal traffic are fitted from a region's history, so
the same code runs on a new coast with no hand-built zones.

## Measured results

* `scripts/evaluate_rules_on_real.py` - rules on real SF AIS: ~5-6 alerts / 100 vessel-days (none HIGH) on untouched traffic; recall of
  injected behaviours ~89% (dark gap 24/24, jump 23/23, clone 16/17, loitering 18/24).
* `scripts/train_region_ml.py` - trained on 1-2 Jan, tested on held-out 3 Jan (includes behaviours the models never saw):
  rules recall 0.89; gradient boosting ROC-AUC 0.96 but finds none of the unseen behaviour types; Isolation Forest ROC-AUC 0.94.
  Rules and ML are complementary.
* A model trained on SF does **not** transfer to Taiwan (`scripts/train_transfer.py`): normal traffic differs too much.
  Train per region.

## Operator workflow

Mark false alarm (with reason - similar alerts are down-weighted), confirm, escalate, add notes, allow-list vessels, adjust
thresholds live (Tuning lab). Everything is under `/detection/*` (see `/docs`).

## What "detected" means - and what it does not

Every recall/precision figure here is measured against **behaviours we defined and added ourselves** (see *Regions*).
It shows the detectors find the *patterns* we describe (dark gap, loiter, rendezvous, ...), not that they find vessels
that were *actually* illegal, sanctioned or hostile. The NOAA archive carries no such labels, and neither will most raw
AIS archives from Taiwan.

To measure against real outcomes we need labelled sources, for example enforcement or detention records, sanctions/IUU
vessel lists (match on MMSI/IMO), Global Fishing Watch events (adapter scaffold in `adapters/gfw.py`, token required),
or publicly reported incidents with a known vessel and time. Each must be checked for licence and for selection bias:
enforcement labels only record what authorities already chose to examine. Until then the system's job is *prioritising
unusual behaviour for a human to review*, with the evidence and the benign alternatives shown.

## Tuning harness

`python scripts/tune_sf.py --seeds 11 12 13 14 15 16 [--set loiter_min_minutes=60]` rebuilds the SF world for several
seeds and reports per-behaviour recall, alerts on the benign regatta look-alike, and unverified alerts on real traffic.
Current (6 seeds): cluster 6/6, rendezvous 6/6, dark transfer 6/6, dark gap 24/24, jump 24/24, zone entry 12/12,
MMSI clone 18/24, loitering 14/24; ~12 unverified alerts per scenario on real traffic (mostly tugs/ferries/ships waiting).
Loitering misses are mostly pleasure craft near marinas and vessels whose own history shows they dwell there routinely.

See also `docs/real-outcomes.md` for the real-label evaluation (sanctions list, documented incidents) and what it showed.
