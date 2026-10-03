# Path analysis: how a track is judged, what the data can and cannot teach

## The pipeline (what the "path agent" does)

1. **Filter.** Only vessels moving slowly enough to be working a line are examined in detail: median speed between 1.5 and 7 kn over a
   6 h window (faster is transit, slower is parked or drifting), at least 8 nm of path.
2. **Describe the shape.** Per window: speed and its steadiness, straightness, turning per nm, number and length of legs, re-traversal of
   the same ground, share of headings along one axis (parallel lines), dwell, extent (`pathml.py`).
3. **Judge.** Today the judgement is the hand-written rule set (`survey.py` pattern rule, plus the towing / restricted-status / zone / cable
   evidence in `threat.py`). The learned model (`pathml.py`, `scripts/train_path_model.py`) is built and evaluated, but not yet used,
   for the reason below.

## What the supplied data taught us

Weak labels came from what vessels announced (towing text in the destination, or sustained "restricted in ability to manoeuvre"):
21 windows on 9 vessels. Scored on vessels the model had not seen:

| method | ROC-AUC | notes |
|---|---|---|
| gradient boosting + logistic regression on 17 shape features | 0.45 | chance: too few positives |
| hand-written lawnmower rule | 0.56 | finds 24% of announced-survey windows |
| speed steadiness alone | 0.68 | the best single feature |

* The announced surveys in this data are mostly **steady, slow tows** (median 4 kn, speed variability 0.15 against 0.57 for other slow
  vessels, about half the turning per nm). They are not all zig-zags: towing a streamer means long, nearly straight runs at constant speed.
* Slow windows are common and mostly innocent: fishing boats trawling (the biggest false-candidate group), tugs, vessels waiting off ports.
* **Conclusion: nine vessels cannot train a path classifier.** A model trained on them would memorise those vessels. We keep it
  experimental and measure it honestly instead of shipping its scores.

## What would make the model real

Confirmed tracks. `data/labels/confirmed_paths.csv` (mmsi, time range, label 1/0, source) overrides the weak labels when present, so
the day a confirmed set exists (mentor, OSINT such as the vessels in the Heritage report, incident records) the same script retrains
and reports vessel-grouped accuracy. Useful sets: confirmed illegal-survey tracks (positives) and, equally, ordinary slow tracks of
cable ships, fishing boats and tugs (negatives); the negatives are what keeps a model from flagging every trawler.

## Next step for an AI agent on paths

A language-model agent is a better fit than a classifier at this data size: render the slow windows that survive the filter as a
picture plus the feature table and the vessel's AIS context, and have the agent say what it sees (tow, lawnmower, trawl, drift,
port approach) with its reasoning, for the analyst to accept or reject. Accepted and rejected cases then become the confirmed set above.


## Update: the agent, and the analyst's confirmed examples

Five tracks the analyst marked after reviewing the research files in kepler.gl are in `data/labels/confirmed_paths.csv` (HAIYANGDIZHI BAHAO
11 Apr, DONG FANG HONG 3 6 Apr, XIANG YANG HONG 01 3 Apr, LIAO YUE 16 Apr, TAN SUO ER HAO 4 Apr). Plotting them showed three kinds of activity:
survey lines under tow (BAHAO: restricted-manoeuvre status, 'TOWING 5NM CABLE(S)', steady 4 kn, five parallel legs; XIANG YANG HONG 01: a hooked
slow line), station-keeping in restricted status (LIAO YUE and DONG FANG HONG 3: under 2 kn inside a few nm), and a tow joined to a fast run
(TAN SUO ER HAO). Hence the agent categories and the rule that a research-declared vessel holding restricted status at low speed in a small area is
reported as station-keeping work.

`pathagent.py` implements the pipeline: research gate (declared name / registry class / towing text; restricted status alone is not enough
because wind-farm and offshore-construction vessels hold it for weeks) -> speed gate (median <= 7 kn, parked included) -> shape features -> reviewer.
Result on the April data: 7,548 vessels -> 32-39 pass the research gate -> 261-279 slow windows -> 87 flagged (41 episodes). The five confirmed
vessels: 3/5 flagged inside the marked +-12 h, 5/5 within +-36 h. The two that miss the narrow range (DONG FANG HONG 3, TAN SUO ER HAO) were marked at
the fast leg between two working stretches; the agent flags the working stretches either side.
Retraining the learned path model with these labels is not worth reporting: they add 4 windows to the 21 weak positives.

Use: `python scripts/evaluate_path_agent.py [--images DIR] [--claude]`; API `/detection/path-reviews`; UI "Path review (advisory)" in the alert panel.
