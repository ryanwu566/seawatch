# Measuring against real outcomes

Everything in `detection-stack.md` is scored against behaviours *we* defined. This page is about the other kind of
evidence: labels that exist in the world independent of us. Neither kind of label is proof of intent.

## Label sources actually wired in

| Source | What it labels | Access | Status |
|---|---|---|---|
| OFAC SDN list (US Treasury) | **Vessel** is sanctioned (1,539 vessels, 1,524 with IMO) | public, `scripts/fetch_watchlists.py` | in use, matched on IMO/MMSI (never on name) |
| Documented incidents (`data/labels/incidents.csv`) | **Vessel + time window** suspected of an act | public reporting, each row cites its source | 1 row: Yi Peng 3 (Baltic cable damage, 17-18 Nov 2024) |
| UK / EU consolidated lists | vessel designations | public | downloaded; too few vessel rows with IMO (EU file 17, UK 34 ships) to matter |
| Global Fishing Watch API | AIS-gap / encounter / loitering events, IUU flags | needs a free token + terms | scaffold only (`adapters/gfw.py`), not run |

Labels are stored with source and confidence. A watch-list entry is a legal designation of a hull, not a statement
about what it did on a given day. An incident is *suspected* and may be an accident (for Yi Peng 3 the cause is still
officially "under investigation").

## Data

* NOAA (US waters, 1-3 Jan 2024): only **4** OFAC-listed vessels appear in all of US waters over three days, with no
  information on what they did.
* Danish Maritime Authority open AIS (`aisdata.ais.dk`, Danish straits / south-west Baltic, with IMO, status, ship type):
  `scripts/evaluate_real_outcomes.py`, `scripts/fetch_dma_partial.py`. The archive link is slow (~0.3 MB/s), so full
  days take ~30 min each.

## Findings so far (18 Nov 2024, one full Danish day: 1,818 vessels)

1. **The documented incident is not observable in this feed.** Yi Peng 3 appears in the Danish data from 08:18 UTC on 18 Nov,
   with AIS on. The cable damage and the reported ~7.5 h AIS-off period were around Gotland/Oland on 17 Nov. The feed
   contains no reports east of ~16.4 degrees E, so zero reports fall inside the incident window. No detector could have
   caught the incident from this data; this is a coverage limit, not a detector result.
2. **Sanctioned vessels are not distinguishable by behaviour rules.** 4 listed tankers crossed the area; none raised an alert
   (base rate: 17% of all vessels did). Transiting a strait looks ordinary. With n=4 this is an observation, not a statistic.
3. **Busy real traffic is much noisier than the SF day:** 204 alerts, 24 rated HIGH, on 1,818 vessels (11 alerts / 100
   vessel-days). The HIGH alerts are dominated by fishing fleets, pilot boats, ferries and pleasure-craft GPS glitches, and
   several chain dozens of vessels into one alert. Tuning for this is the next piece of work.

## What this implies

* Behaviour rules answer *"is this movement unusual and why"*. They cannot answer *"is this vessel on a list"* - that needs
  an identity screen. `profile.py` / `scripts/evaluate_profile.py` train one on AIS-visible static traits (MMSI country prefix,
  type, size, data completeness, destination conventions, reporting quality) with IMO/name excluded. It needs tens of listed
  vessels to say anything; one day gives 4. Fetch more days (`fetch_dma_partial.py`) before reading anything into it.
* To test against the Taiwan cable cases (Shunxin-39, 3 Jan 2025 near Keelung; Hong Tai 58, Feb 2025, Penghu cable) we need AIS
  covering those dates and places. Identifiers and times must be verified from primary reporting before being added as
  incident rows.
