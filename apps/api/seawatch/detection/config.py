"""Operator-adjustable detection thresholds.

``PARAM_SPECS`` is what the UI renders as sliders; ``DetectionConfig`` is what the
detectors read. Every threshold has a unit, range and plain-language meaning so an
operator can trade sensitivity against false alarms without reading code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class DetectionConfig:
    # --- AIS reporting gaps ------------------------------------------------
    gap_min_minutes: float = 40.0
    gap_max_implied_knots: float = 35.0
    # --- Loitering / unusual stopping -------------------------------------
    loiter_radius_nm: float = 2.0
    loiter_min_minutes: float = 90.0
    loiter_max_speed_kn: float = 4.0
    # --- Rendezvous / clustering ------------------------------------------
    proximity_distance_nm: float = 0.6
    rendezvous_min_minutes: float = 45.0
    rendezvous_max_speed_kn: float = 3.5
    cluster_distance_nm: float = 3.0
    cluster_min_vessels: int = 4
    cluster_min_minutes: float = 40.0
    zone_min_dwell_minutes: float = 0.0
    # --- Kinematic plausibility / spoofing --------------------------------
    jump_min_implied_knots: float = 60.0
    jump_min_distance_nm: float = 4.0
    identity_min_alternations: int = 3
    # --- Pattern of life (route deviation) --------------------------------
    deviation_min_minutes: float = 60.0
    deviation_min_speed_kn: float = 5.0
    deviation_familiarity: float = 1.5
    # --- Alerting ----------------------------------------------------------
    alert_link_hours: float = 12.0
    alert_min_risk: float = 30.0
    high_risk: float = 70.0
    medium_risk: float = 45.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectionConfig":
        base = cls()
        for f in fields(cls):
            if f.name in data and data[f.name] is not None:
                setattr(base, f.name, type(getattr(base, f.name))(data[f.name]))
        return base


PARAM_SPECS: list[dict[str, Any]] = [
    dict(name="gap_min_minutes", group="AIS gap", label="Minimum silence", unit="min", min=10, max=240, step=5,
         help="A vessel that stops transmitting for longer than this is flagged. Lower = more alerts."),
    dict(name="loiter_min_minutes", group="Loitering", label="Minimum dwell", unit="min", min=20, max=360, step=10,
         help="How long a vessel must stay in a small area, away from port, before it counts as loitering."),
    dict(name="loiter_radius_nm", group="Loitering", label="Loiter radius", unit="nm", min=0.5, max=8, step=0.5,
         help="The vessel must remain inside a circle of this radius."),
    dict(name="rendezvous_min_minutes", group="Rendezvous", label="Minimum meeting time", unit="min", min=15, max=180, step=5,
         help="Two vessels moving slowly together for at least this long."),
    dict(name="proximity_distance_nm", group="Rendezvous", label="Meeting distance", unit="nm", min=0.1, max=2, step=0.1,
         help="Maximum separation for two vessels to count as meeting."),
    dict(name="cluster_min_vessels", group="Clustering", label="Cluster size", unit="vessels", min=3, max=12, step=1,
         help="Number of vessels gathered together to raise a cluster."),
    dict(name="jump_min_implied_knots", group="Spoofing", label="Impossible speed", unit="kn", min=30, max=150, step=5,
         help="A position change implying a speed above this is treated as physically implausible."),
    dict(name="deviation_min_minutes", group="Route deviation", label="Time off normal routes", unit="min", min=20, max=240, step=10,
         help="How long a vessel must travel through water that normal traffic does not use."),
    dict(name="deviation_familiarity", group="Route deviation", label="Familiar-water cut-off", unit="vessels", min=0.5, max=5, step=0.1,
         help="Water cells with less historic traffic than this count as unfamiliar."),
    dict(name="alert_min_risk", group="Alerting", label="Minimum risk to alert", unit="score", min=10, max=80, step=1,
         help="Alerts below this risk score are hidden. Raise it to cut noise."),
    dict(name="high_risk", group="Alerting", label="High-risk level", unit="score", min=50, max=95, step=1,
         help="Risk score at which an alert is rated HIGH."),
]
