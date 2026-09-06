"""Geometry abstraction: do not invent coordinates."""

from __future__ import annotations

from ariadne_geoloadst.engine import DatasetSpec
from ariadne_geoloadst.geometry import extract_spatial_network, is_geographic
from ariadne_geoloadst.schemas import SpatialNetwork
from tests.conftest import FakeAnalyzer, FakeElectricalModel


def test_analyzer_coords_and_lines_are_mapped() -> None:
    analyzer = FakeAnalyzer(DatasetSpec(simbench_network_code="example"))
    analyzer.prepare_data()
    network = extract_spatial_network(analyzer)

    assert network.crs == "EPSG:4326"
    assert [node.bus_id for node in network.nodes] == [1, 2, 3]
    assert all(node.has_geometry for node in network.nodes)
    assert len(network.edges) == 2
    assert all(edge.has_geometry for edge in network.edges)


def test_missing_bus_coordinates_are_flagged_not_invented() -> None:
    network = extract_spatial_network(
        {
            "nodes": [
                {"bus_id": 1, "x": 10.9, "y": 53.3},
                {"bus_id": 2},
            ],
            "edges": [{"from_bus": 1, "to_bus": 2, "kind": "line"}],
        }
    )
    by_id = {node.bus_id: node for node in network.nodes}
    assert by_id[1].has_geometry is True
    assert by_id[2].has_geometry is False
    assert by_id[2].x is None
    assert network.edges[0].has_geometry is False
    assert network.missing_node_count == 1


def test_projected_coordinates_are_not_published_as_wgs84() -> None:
    network = extract_spatial_network(
        {
            "nodes": [
                {"bus_id": 1, "x": 500000.0, "y": 5800000.0},
                {"bus_id": 2, "x": 500100.0, "y": 5800100.0},
            ],
            "edges": [{"from_bus": 1, "to_bus": 2}],
        }
    )
    assert network.crs == "local"
    assert all(not node.has_geometry for node in network.nodes)


def test_existing_spatial_network_is_returned_unchanged() -> None:
    original = SpatialNetwork(source="explicit")
    assert extract_spatial_network(original) is original


def test_electrical_model_without_geodata_has_unknown_crs() -> None:
    network = extract_spatial_network(FakeElectricalModel())
    assert network.crs == "unknown"
    assert network.nodes == ()


def test_geographic_predicate() -> None:
    assert is_geographic(11.0, 53.3) is True
    assert is_geographic(500000.0, 53.3) is False
