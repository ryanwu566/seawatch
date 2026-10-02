"""Load and validate the curated civilian scenario dataset (design §5–§6).

Pure, offline, dependency-free. Maps the JSON dataset into the frozen Slice A
dataclasses, enforcing the provenance truth boundary at load time:

- ``official``/``derived`` fields must carry adequate ``SourceMetadata``;
- capacity/cost/risk/demand figures must never be ``official``;
- coordinates must fall inside the Taiwan bbox;
- a malformed dataset raises :class:`DatasetError` so the API router can degrade
  to an empty scenario list without affecting other SeaWatch endpoints.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import (
    Commodity,
    Demand,
    DisruptionScenario,
    Port,
    Route,
    SourceMetadata,
    SourceType,
    Supply,
)
from .provenance import validate_official

DEFAULT_DATASET_PATH = Path(__file__).parent / "data" / "scenarios.json"

# Taiwan bounding box (matches apps/web taiwanMap TAIWAN_BBOX).
_TAIWAN_BBOX = {"min_lat": 21.5, "min_lon": 118.0, "max_lat": 26.5, "max_lon": 123.5}


class DatasetError(ValueError):
    """Raised when the curated dataset is missing or structurally invalid."""


@dataclass(frozen=True)
class Dataset:
    ports: tuple[Port, ...]
    demands: tuple[Demand, ...]
    supplies: tuple[Supply, ...]
    routes: tuple[Route, ...]
    scenarios: tuple[DisruptionScenario, ...]

    def _ports_by_id(self) -> dict[str, Port]:
        return {p.id: p for p in self.ports}

    def port(self, port_id: str) -> Port | None:
        return self._ports_by_id().get(port_id)

    def scenario(self, scenario_id: str) -> DisruptionScenario | None:
        for scenario in self.scenarios:
            if scenario.id == scenario_id:
                return scenario
        return None

    def demands_for(self, scenario: DisruptionScenario) -> tuple[Demand, ...]:
        """Demands whose normal port is disrupted by this scenario."""

        disrupted = set(scenario.disrupted_ports)
        return tuple(d for d in self.demands if d.normally_served_by in disrupted)

    def candidate_routes(self, scenario: DisruptionScenario) -> tuple[Route, ...]:
        """Routes whose port is NOT disrupted (eligible alternatives)."""

        disrupted = set(scenario.disrupted_ports)
        return tuple(r for r in self.routes if r.from_port not in disrupted)

    def supplies_for(self, commodity: Commodity) -> tuple[Supply, ...]:
        return tuple(s for s in self.supplies if s.commodity is commodity)

    def effective_capacity(self, scenario: DisruptionScenario, port_id: str) -> float:
        """Port capacity under the scenario (0 if disrupted; overrides applied)."""

        if port_id in scenario.disrupted_ports:
            return 0.0
        port = self.port(port_id)
        base = port.capacity_units if port else 0.0
        return float(scenario.capacity_overrides.get(port_id, base))


def _source_type(raw: str) -> SourceType:
    try:
        return SourceType(raw)
    except ValueError as exc:  # noqa: PERF203 - explicit error path
        raise DatasetError(f"invalid source_type: {raw!r}") from exc


def _metadata(raw: dict | None) -> SourceMetadata | None:
    if raw is None:
        return None
    return SourceMetadata(
        source_name=raw.get("source_name"),
        source_reference=raw.get("source_reference"),
        as_of=raw.get("as_of"),
        derivation_method=raw.get("derivation_method"),
    )


def _commodity(raw: str) -> Commodity:
    try:
        return Commodity(raw)
    except ValueError as exc:
        raise DatasetError(f"invalid commodity: {raw!r}") from exc


def _require_in_bbox(lon: float, lat: float, where: str) -> None:
    if not (_TAIWAN_BBOX["min_lon"] <= lon <= _TAIWAN_BBOX["max_lon"]):
        raise DatasetError(f"{where}: lon {lon} outside Taiwan bbox")
    if not (_TAIWAN_BBOX["min_lat"] <= lat <= _TAIWAN_BBOX["max_lat"]):
        raise DatasetError(f"{where}: lat {lat} outside Taiwan bbox")


def load(path: Path | str = DEFAULT_DATASET_PATH) -> Dataset:
    """Load + validate the dataset. Raises :class:`DatasetError` on any problem."""

    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetError(f"dataset file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetError(f"dataset file is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise DatasetError("dataset root must be a JSON object")

    try:
        ports = _parse_ports(raw.get("ports", []))
        demands = _parse_demands(raw.get("demands", []))
        supplies = _parse_supplies(raw.get("supplies", []))
        routes = _parse_routes(raw.get("routes", []))
        scenarios = _parse_scenarios(raw.get("scenarios", []))
    except (KeyError, TypeError) as exc:
        raise DatasetError(f"malformed dataset record: {exc}") from exc

    dataset = Dataset(
        ports=ports,
        demands=demands,
        supplies=supplies,
        routes=routes,
        scenarios=scenarios,
    )
    _validate_cross_references(dataset)
    return dataset


def _parse_ports(items: list) -> tuple[Port, ...]:
    ports: list[Port] = []
    for item in items:
        source_type = _source_type(item["source_type"])
        port = Port(
            id=item["id"],
            name_zh=item["name_zh"],
            name_en=item["name_en"],
            lon=float(item["lon"]),
            lat=float(item["lat"]),
            capacity_units=float(item["capacity_units"]),
            base_handling_cost=float(item["base_handling_cost"]),
            source_type=source_type,
            source_metadata=_metadata(item.get("source_metadata")),
        )
        _require_in_bbox(port.lon, port.lat, f"port {port.id}")
        # Only the port name/coordinate may be official (with evidence). Capacity
        # and cost are planning values and must never masquerade as official.
        try:
            validate_official(port)
        except ValueError as exc:
            raise DatasetError(f"port {port.id}: {exc}") from exc
        ports.append(port)
    return tuple(ports)


def _parse_demands(items: list) -> tuple[Demand, ...]:
    demands: list[Demand] = []
    for item in items:
        source_type = _source_type(item["source_type"])
        if source_type in (SourceType.OFFICIAL, SourceType.DERIVED):
            raise DatasetError(
                f"demand {item.get('id')!r} must be scenario/synthetic, not {source_type.value}"
            )
        demands.append(
            Demand(
                id=item["id"],
                commodity=_commodity(item["commodity"]),
                priority=int(item["priority"]),
                quantity_units=float(item["quantity_units"]),
                origin_demand_node=item["origin_demand_node"],
                normally_served_by=item["normally_served_by"],
                source_type=source_type,
                source_metadata=_metadata(item.get("source_metadata")),
            )
        )
    return tuple(demands)


def _parse_supplies(items: list) -> tuple[Supply, ...]:
    supplies: list[Supply] = []
    for item in items:
        source_type = _source_type(item["source_type"])
        if source_type in (SourceType.OFFICIAL, SourceType.DERIVED):
            raise DatasetError(
                f"supply {item.get('id')!r} must be scenario/synthetic, not {source_type.value}"
            )
        supplies.append(
            Supply(
                id=item["id"],
                commodity=_commodity(item["commodity"]),
                available_units=float(item["available_units"]),
                entry_port_options=tuple(item["entry_port_options"]),
                source_type=source_type,
                source_metadata=_metadata(item.get("source_metadata")),
            )
        )
    return tuple(supplies)


def _parse_routes(items: list) -> tuple[Route, ...]:
    routes: list[Route] = []
    for item in items:
        source_type = _source_type(item["source_type"])
        geometry = item.get("path_geometry")
        schematic = bool(item.get("schematic", geometry is None))
        route = Route(
            id=item["id"],
            from_port=item["from_port"],
            to_demand_node=item["to_demand_node"],
            distance_km=float(item["distance_km"]),
            baseline_eta_hours=float(item["baseline_eta_hours"]),
            per_unit_cost=float(item["per_unit_cost"]),
            route_risk=float(item["route_risk"]),
            source_type=source_type,
            path_geometry=geometry,
            schematic=schematic,
            source_metadata=_metadata(item.get("source_metadata")),
        )
        if not (0.0 <= route.route_risk <= 1.0):
            raise DatasetError(f"route {route.id}: route_risk must be in [0,1]")
        # A derived distance must name its method; routes are never official.
        if route.source_type is SourceType.OFFICIAL:
            raise DatasetError(f"route {route.id}: routes may not be classified official")
        try:
            validate_official(route)
        except ValueError as exc:
            raise DatasetError(f"route {route.id}: {exc}") from exc
        if geometry is None and not route.schematic:
            raise DatasetError(f"route {route.id}: routes without geometry must be schematic")
        routes.append(route)
    return tuple(routes)


def _parse_scenarios(items: list) -> tuple[DisruptionScenario, ...]:
    scenarios: list[DisruptionScenario] = []
    for item in items:
        source_type = _source_type(item["source_type"])
        if source_type is not SourceType.SCENARIO:
            raise DatasetError(
                f"scenario {item.get('id')!r} must have source_type 'scenario'"
            )
        overrides = {k: float(v) for k, v in item.get("capacity_overrides", {}).items()}
        scenarios.append(
            DisruptionScenario(
                id=item["id"],
                name_zh=item["name_zh"],
                name_en=item["name_en"],
                disrupted_ports=tuple(item["disrupted_ports"]),
                description_zh=item["description_zh"],
                description_en=item["description_en"],
                source_type=source_type,
                capacity_overrides=overrides,
            )
        )
    return tuple(scenarios)


def _validate_cross_references(dataset: Dataset) -> None:
    port_ids = {p.id for p in dataset.ports}
    for route in dataset.routes:
        if route.from_port not in port_ids:
            raise DatasetError(f"route {route.id}: unknown from_port {route.from_port!r}")
    for scenario in dataset.scenarios:
        for disrupted in scenario.disrupted_ports:
            if disrupted not in port_ids:
                raise DatasetError(
                    f"scenario {scenario.id}: unknown disrupted port {disrupted!r}"
                )
