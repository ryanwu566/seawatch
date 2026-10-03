"""Slice D — capacity-aware allocation tests."""

from __future__ import annotations

from apps.api.seawatch.logistics.dataset import Dataset, load
from apps.api.seawatch.logistics.models import (
    Commodity,
    Demand,
    DisruptionScenario,
    Port,
    Route,
    SourceMetadata,
    SourceType,
    Supply,
)
from apps.api.seawatch.logistics.optimizer import (
    GreedyPriorityOptimizer,
    allocate,
)
from apps.api.seawatch.logistics.scoring import normalize_weights


def _port(pid: str, cap: float, cost: float = 1.0) -> Port:
    return Port(
        id=pid,
        name_zh=pid,
        name_en=pid,
        lon=120.5,
        lat=24.0,
        capacity_units=cap,
        base_handling_cost=cost,
        source_type=SourceType.SCENARIO,
    )


def _route(port: str, eta: float, cost: float, risk: float) -> Route:
    return Route(
        id=f"{port}->south-node",
        from_port=port,
        to_demand_node="south-node",
        distance_km=100.0,
        baseline_eta_hours=eta,
        per_unit_cost=cost,
        route_risk=risk,
        source_type=SourceType.DERIVED,
        schematic=True,
        source_metadata=SourceMetadata(derivation_method="great-circle"),
    )


def _demand(did: str, commodity: Commodity, priority: int, qty: float) -> Demand:
    return Demand(
        id=did,
        commodity=commodity,
        priority=priority,
        quantity_units=qty,
        origin_demand_node="south-node",
        normally_served_by="kaohsiung",
        source_type=SourceType.SCENARIO,
    )


def _supply(commodity: Commodity, units: float, ports: tuple[str, ...]) -> Supply:
    return Supply(
        id=f"{commodity.value}-supply",
        commodity=commodity,
        available_units=units,
        entry_port_options=ports,
        source_type=SourceType.SCENARIO,
    )


def _scenario() -> DisruptionScenario:
    return DisruptionScenario(
        id="kaohsiung-disruption",
        name_zh="高雄港中斷情境",
        name_en="Kaohsiung Port Disruption",
        disrupted_ports=("kaohsiung",),
        description_zh="x",
        description_en="x",
        source_type=SourceType.SCENARIO,
    )


def _dataset(ports, demands, supplies, routes) -> Dataset:
    return Dataset(
        ports=tuple(ports),
        demands=tuple(demands),
        supplies=tuple(supplies),
        routes=tuple(routes),
        scenarios=(_scenario(),),
    )


WEIGHTS = normalize_weights(None)


def test_priority_order_medical_before_food_before_fuel() -> None:
    ds = _dataset(
        ports=[_port("kaohsiung", 0.0), _port("taichung", 100.0)],
        demands=[
            _demand("fuel-south", Commodity.FUEL, 3, 10.0),
            _demand("medical-south", Commodity.MEDICAL, 1, 10.0),
            _demand("food-south", Commodity.FOOD, 2, 10.0),
        ],
        supplies=[
            _supply(Commodity.MEDICAL, 100.0, ("taichung",)),
            _supply(Commodity.FOOD, 100.0, ("taichung",)),
            _supply(Commodity.FUEL, 100.0, ("taichung",)),
        ],
        routes=[_route("taichung", 9.0, 1.0, 0.2)],
    )
    allocs = allocate(_scenario(), ds, WEIGHTS)
    assert [a.demand_id for a in allocs] == [
        "medical-south",
        "food-south",
        "fuel-south",
    ]


def test_disrupted_port_excluded() -> None:
    ds = _dataset(
        ports=[_port("kaohsiung", 100.0), _port("taichung", 100.0)],
        demands=[_demand("medical-south", Commodity.MEDICAL, 1, 10.0)],
        supplies=[_supply(Commodity.MEDICAL, 100.0, ("kaohsiung", "taichung"))],
        routes=[_route("kaohsiung", 1.0, 1.0, 0.1), _route("taichung", 9.0, 1.0, 0.2)],
    )
    allocs = allocate(_scenario(), ds, WEIGHTS)
    ports_used = {a.port_id for alloc in allocs for a in alloc.assignments}
    assert "kaohsiung" not in ports_used
    assert ports_used == {"taichung"}


def test_capacity_decrements_across_demands() -> None:
    # Taichung cap 15; medical 10 then food 10 -> food can only get 5, 5 unmet
    ds = _dataset(
        ports=[_port("kaohsiung", 0.0), _port("taichung", 15.0)],
        demands=[
            _demand("medical-south", Commodity.MEDICAL, 1, 10.0),
            _demand("food-south", Commodity.FOOD, 2, 10.0),
        ],
        supplies=[
            _supply(Commodity.MEDICAL, 100.0, ("taichung",)),
            _supply(Commodity.FOOD, 100.0, ("taichung",)),
        ],
        routes=[_route("taichung", 9.0, 1.0, 0.2)],
    )
    allocs = {a.demand_id: a for a in allocate(_scenario(), ds, WEIGHTS)}
    assert allocs["medical-south"].satisfied_units == 10.0
    assert allocs["medical-south"].unmet_units == 0.0
    assert allocs["food-south"].satisfied_units == 5.0
    assert allocs["food-south"].unmet_units == 5.0


def test_split_allocation_across_two_ports() -> None:
    # Taichung cap 30, Keelung cap 70. Demand 50 -> split 30 + 20.
    ds = _dataset(
        ports=[_port("kaohsiung", 0.0), _port("taichung", 30.0), _port("keelung", 70.0, 1.15)],
        demands=[_demand("medical-south", Commodity.MEDICAL, 1, 50.0)],
        supplies=[_supply(Commodity.MEDICAL, 100.0, ("taichung", "keelung"))],
        routes=[
            _route("taichung", 9.5, 1.2, 0.21),
            _route("keelung", 15.0, 1.45, 0.28),
        ],
    )
    alloc = allocate(_scenario(), ds, WEIGHTS)[0]
    assert alloc.satisfied_units == 50.0
    assert alloc.unmet_units == 0.0
    # Two assignments; Taichung first (better score), filled to its 30 cap.
    by_port = {a.port_id: a.units for a in alloc.assignments}
    assert by_port["taichung"] == 30.0
    assert by_port["keelung"] == 20.0


def test_unmet_when_capacity_short() -> None:
    ds = _dataset(
        ports=[_port("kaohsiung", 0.0), _port("taichung", 20.0)],
        demands=[_demand("medical-south", Commodity.MEDICAL, 1, 50.0)],
        supplies=[_supply(Commodity.MEDICAL, 100.0, ("taichung",))],
        routes=[_route("taichung", 9.0, 1.0, 0.2)],
    )
    alloc = allocate(_scenario(), ds, WEIGHTS)[0]
    assert alloc.satisfied_units == 20.0
    assert alloc.unmet_units == 30.0


def test_supply_cap_enforced() -> None:
    # Ample port capacity but only 12 units of supply.
    ds = _dataset(
        ports=[_port("kaohsiung", 0.0), _port("taichung", 100.0)],
        demands=[_demand("medical-south", Commodity.MEDICAL, 1, 50.0)],
        supplies=[_supply(Commodity.MEDICAL, 12.0, ("taichung",))],
        routes=[_route("taichung", 9.0, 1.0, 0.2)],
    )
    alloc = allocate(_scenario(), ds, WEIGHTS)[0]
    assert alloc.satisfied_units == 12.0
    assert alloc.unmet_units == 38.0


def test_missing_route_excludes_port() -> None:
    # Keelung has capacity+supply but NO route to the demand node.
    ds = _dataset(
        ports=[_port("kaohsiung", 0.0), _port("taichung", 10.0), _port("keelung", 100.0, 1.15)],
        demands=[_demand("medical-south", Commodity.MEDICAL, 1, 50.0)],
        supplies=[_supply(Commodity.MEDICAL, 100.0, ("taichung", "keelung"))],
        routes=[_route("taichung", 9.0, 1.0, 0.2)],  # no keelung route
    )
    alloc = allocate(_scenario(), ds, WEIGHTS)[0]
    assert alloc.satisfied_units == 10.0
    assert alloc.unmet_units == 40.0
    assert {a.port_id for a in alloc.assignments} == {"taichung"}


def test_all_ports_disrupted_all_unmet() -> None:
    scenario = DisruptionScenario(
        id="kaohsiung-disruption",
        name_zh="x",
        name_en="x",
        disrupted_ports=("kaohsiung", "taichung"),
        description_zh="x",
        description_en="x",
        source_type=SourceType.SCENARIO,
    )
    ds = Dataset(
        ports=(_port("kaohsiung", 0.0), _port("taichung", 100.0)),
        demands=(_demand("medical-south", Commodity.MEDICAL, 1, 50.0),),
        supplies=(_supply(Commodity.MEDICAL, 100.0, ("taichung",)),),
        routes=(_route("taichung", 9.0, 1.0, 0.2),),
        scenarios=(scenario,),
    )
    alloc = allocate(scenario, ds, WEIGHTS)[0]
    assert alloc.satisfied_units == 0.0
    assert alloc.unmet_units == 50.0
    assert alloc.assignments == ()


def test_determinism_identical_runs() -> None:
    ds = load()
    scenario = ds.scenario("kaohsiung-disruption")
    opt = GreedyPriorityOptimizer()
    a = opt.allocate(scenario, ds, WEIGHTS)
    b = opt.allocate(scenario, ds, WEIGHTS)
    assert a == b


def test_no_over_allocation_on_real_dataset() -> None:
    ds = load()
    scenario = ds.scenario("kaohsiung-disruption")
    allocs = allocate(scenario, ds, WEIGHTS)
    used: dict[str, float] = {}
    for alloc in allocs:
        for assignment in alloc.assignments:
            used[assignment.port_id] = used.get(assignment.port_id, 0.0) + assignment.units
    for port_id, total in used.items():
        assert total <= ds.effective_capacity(scenario, port_id) + 1e-6
