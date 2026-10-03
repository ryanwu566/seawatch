"""Slice B — curated scenario dataset + loader tests."""

from __future__ import annotations

import json

import pytest

from apps.api.seawatch.logistics.dataset import (
    DEFAULT_DATASET_PATH,
    DatasetError,
    load,
)
from apps.api.seawatch.logistics.models import Commodity, SourceType

TAIWAN_BBOX = {"min_lat": 21.5, "min_lon": 118.0, "max_lat": 26.5, "max_lon": 123.5}


@pytest.fixture(scope="module")
def dataset():
    return load()


def test_default_dataset_loads(dataset) -> None:
    assert dataset.ports
    assert dataset.demands
    assert dataset.routes
    assert dataset.scenarios


def test_all_coordinates_within_taiwan_bbox(dataset) -> None:
    for port in dataset.ports:
        assert TAIWAN_BBOX["min_lon"] <= port.lon <= TAIWAN_BBOX["max_lon"]
        assert TAIWAN_BBOX["min_lat"] <= port.lat <= TAIWAN_BBOX["max_lat"]


def test_covers_three_ports_and_three_commodities(dataset) -> None:
    port_ids = {p.id for p in dataset.ports}
    assert {"kaohsiung", "taichung", "keelung"} <= port_ids
    commodities = {d.commodity for d in dataset.demands}
    assert commodities == {Commodity.MEDICAL, Commodity.FOOD, Commodity.FUEL}


def test_kaohsiung_scenario_marks_kaohsiung_disrupted(dataset) -> None:
    scenario = dataset.scenario("kaohsiung-disruption")
    assert scenario is not None
    assert "kaohsiung" in scenario.disrupted_ports
    assert scenario.source_type is SourceType.SCENARIO


def test_capacity_cost_risk_never_official(dataset) -> None:
    # Capacity/cost live on the Port record; the port *name/coordinate* may be
    # official, but the design forbids presenting capacity/cost as official. We
    # assert routes (carrying cost/risk) are never official and the dataset's
    # declared capacity provenance is synthetic.
    for route in dataset.routes:
        assert route.source_type is not SourceType.OFFICIAL
    raw = json.loads(DEFAULT_DATASET_PATH.read_text(encoding="utf-8"))
    assert raw["capacity_provenance"]["source_type"] == "synthetic"
    assert raw["route_planning_provenance"]["source_type"] == "scenario"


def test_official_ports_have_complete_metadata(dataset) -> None:
    for port in dataset.ports:
        if port.source_type is SourceType.OFFICIAL:
            assert port.source_metadata is not None
            assert port.source_metadata.source_name
            assert port.source_metadata.source_reference


def test_derived_routes_name_their_method(dataset) -> None:
    for route in dataset.routes:
        if route.source_type is SourceType.DERIVED:
            assert route.source_metadata is not None
            assert route.source_metadata.derivation_method
            assert "great-circle" in route.source_metadata.derivation_method


def test_routes_without_geometry_are_schematic(dataset) -> None:
    for route in dataset.routes:
        if route.path_geometry is None:
            assert route.schematic is True


def test_demands_for_scenario_are_kaohsiung_served(dataset) -> None:
    scenario = dataset.scenario("kaohsiung-disruption")
    affected = dataset.demands_for(scenario)
    assert affected
    assert all(d.normally_served_by == "kaohsiung" for d in affected)


def test_candidate_routes_exclude_disrupted_port(dataset) -> None:
    scenario = dataset.scenario("kaohsiung-disruption")
    routes = dataset.candidate_routes(scenario)
    assert routes
    assert all(r.from_port != "kaohsiung" for r in routes)


def test_effective_capacity_zero_for_disrupted(dataset) -> None:
    scenario = dataset.scenario("kaohsiung-disruption")
    assert dataset.effective_capacity(scenario, "kaohsiung") == 0.0
    assert dataset.effective_capacity(scenario, "taichung") > 0.0


def test_loader_rejects_official_without_metadata(tmp_path) -> None:
    bad = {
        "ports": [
            {
                "id": "x",
                "name_zh": "x",
                "name_en": "x",
                "lon": 120.5,
                "lat": 24.0,
                "capacity_units": 10.0,
                "base_handling_cost": 1.0,
                "source_type": "official",
            }
        ],
        "demands": [],
        "supplies": [],
        "routes": [],
        "scenarios": [],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DatasetError):
        load(path)


def test_loader_rejects_derived_without_method(tmp_path) -> None:
    bad = {
        "ports": [],
        "demands": [],
        "supplies": [],
        "routes": [
            {
                "id": "r",
                "from_port": "a",
                "to_demand_node": "b",
                "distance_km": 10.0,
                "baseline_eta_hours": 1.0,
                "per_unit_cost": 1.0,
                "route_risk": 0.1,
                "schematic": True,
                "source_type": "derived",
            }
        ],
        "scenarios": [],
    }
    path = tmp_path / "bad2.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DatasetError):
        load(path)


def test_loader_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(DatasetError):
        load(tmp_path / "does_not_exist.json")


def test_loader_rejects_invalid_json(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(DatasetError):
        load(path)


def test_loader_rejects_route_risk_out_of_range(tmp_path) -> None:
    bad = {
        "ports": [],
        "demands": [],
        "supplies": [],
        "routes": [
            {
                "id": "r",
                "from_port": "a",
                "to_demand_node": "b",
                "distance_km": 10.0,
                "baseline_eta_hours": 1.0,
                "per_unit_cost": 1.0,
                "route_risk": 1.4,
                "schematic": True,
                "source_type": "scenario",
            }
        ],
        "scenarios": [],
    }
    path = tmp_path / "bad3.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(DatasetError):
        load(path)
