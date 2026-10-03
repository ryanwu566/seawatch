# What counts as a "potential threat" (national-scan definition, v1)

The system reports whatever COULD be a threat to Taiwan's maritime security and lets the analyst decide. This page says exactly what that means, so that
rules, the path agent and the precision measurements all use the same definition. It is a working definition for the team to correct.

## 1. The five signal families

A track is reported when it shows at least one of these. Hull type never clears a vessel: a fishing-type hull is judged on the same signals.

| family | observable signal | rule(s) | status |
|---|---|---|---|
| **S1 Survey / seabed mapping** | research-declared vessel towing, working a line, or holding in restricted-manoeuvre status; survey-shaped legs; inside or near Taiwan's zones | R0-R7, `survey_pattern`, path agent | built |
| **S2 Infrastructure interference** | any vessel slow or stopped on a charted submarine cable, away from harbours, alone (no crowd of slow boats around it) | `cable_activity` | built v1 |
| **S3 Sovereignty presence** | foreign state vessel inside 12 nm (R6); entry to a protected zone (cable corridor, Kinmen restricted waters) | R6, `zone_entry` | built |
| **S4 Identity deception** | impossible jumps, one MMSI in two places, cloned or changing identities | `position_jump`, `identity_conflict` | built |
| **S5 Dark in a sensitive place** | AIS silence only where it matters: inside 24 nm of Taiwan-administered land or within 3 nm of a cable | gap rule restricted to sensitive areas | proposed |
| **S6 Coordinated presence** | a fishing-type group moving together (same speed and heading, convoy / swarm) near Taiwan or a cable, unusually large for the area | convoy feature on clusters | proposed |

## 2. Fishing-type vessels in dense traffic: how precision improves

Fishing vessels are a large part of the traffic (3,467 of 7,480 tracks in the supplied day) and most of what they do is routine, but they also appear in
publicly reported cable-damage, militia and illegal-transfer cases. So the system does not discount them; it makes the signals sharper:

1. **Judge by place and behaviour, not hull.** S2 ignores ship type. A fishing boat that fishes on a fishing ground is invisible to S2; one that is the only
   slow vessel on a cable for five hours is reported.
2. **Crowd vs lone.** Many slow vessels in one area is a fishing ground or anchorage (skipped, with the count logged); a lone vessel is the signal.
   On the supplied day this took cable-area candidates from 166 to 53 events (37 vessels) with no change in the rule.
3. **Sensitive-area gating (S5, proposed).** Do not look for dark gaps / loitering everywhere in the Strait; look only inside 24 nm and near cables.
   This keeps the rule's value and drops most of the dense-fishing-ground noise.
4. **Fixed objects are not vessels.** Fish farms, buoys and moorings broadcast like ships. A track that never reaches ship speed, or sits fixed on one spot
   for hours, is excluded (302 tracks on the supplied day).
5. **History makes "unusual" meaningful.** A boat that stops every day at the same spot is a habit (VesselHabits); the first time it does so on a cable is not.
   One day of history is too little; several days fix most of the remaining noise.
6. **Area picture.** Routine fishing behaviours are shown as one summary per area and day, with an "unusually large fleet" flag, not as dozens of alerts.

## 3. Precision of the path agent

The agent only sees research-declared vessels (the research gate removes ~99.5% of traffic before any model is involved). Ways to raise its precision,
in order of value:

1. **Confirmed examples.** Today five analyst-marked paths; every accept / reject in the UI becomes a labelled path (`/path-reviews-export`).
2. **Two reviewers must agree.** The deterministic rules and a language model both read the same window; a window is flagged by default when the rules flag
   it, and the model can only add "agree" or "disagree" (disagreement is shown, not hidden). Later, auto-escalate only on agreement.
3. **Cheaper model for volume, stronger model for disputes.** Run a small model on every surviving window and a larger one only when the rules and the small
   model disagree.
4. **Category-specific checks** (towing text must be present for "survey lines under tow" to reach high confidence; station-keeping needs restricted status).

## 4. How precision will be measured

- **Analyst precision per rule:** confirmed / (confirmed + false alarm) from the status buttons already in the UI, reported per kind in the Assessment view.
- **Replay of known incidents:** the labelled cases (Yi Peng 3; Hong Tai 58 and Shunxin-39 once positions are added to `data/labels/incidents.csv`) must
  be raised by S2 / S4 when their tracks are replayed.
- **Injected tests** in `sf-bay` and the simulated region for rules switched off in the Taiwan regions (gaps, loitering, rendezvous), until labelled Taiwan data exists.
- A rule is promoted to the live Taiwan demo only when its analyst precision on at least a few days of review is acceptable to the team.
