"""Spatial normalization produces Ariadne-compatible GeoJSON, not a new viewer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from ariadne_geoloadst.capabilities import load_default_registry
from ariadne_geoloadst.engine import DatasetSpec, GeoLoadSTEngine
from ariadne_geoloadst.geometry import extract_spatial_network
from ariadne_geoloadst.schemas import ExecutionRequest, SpatialNetwork
from ariadne_geoloadst.visualization import (
    COLOR_HIGH,
    COLOR_LOW,
    build_spatial_result,
    export_geojson,
    to_ariadne_map_payload,
)
from tests.conftest import AvailablePlugin, FakeAnalyzer

NETWORK_CODE = "1-complete_data-mixed-all-1-sw"


def _network() -> SpatialNetwork:
    analyzer = FakeAnalyzer(DatasetSpec(simbench_network_code=NETWORK_CODE))
    analyzer.prepare_data()
    return extract_spatial_network(analyzer)


def _feature_list(geojson: dict[str, object]) -> list[dict[str, Any]]:
    raw = geojson["features"]
    assert isinstance(raw, list | tuple)
    return [cast(dict[str, Any], item) for item in raw]


def test_instability_points_carry_value_severity_and_ariadne_fields() -> None:
    spec = load_default_registry().get("load_instability_rms")
    spatial = build_spatial_result(
        spec=spec,
        outputs={
            "instability_index": {"kind": "array", "values": [0.1, 0.9, 0.5]},
            "bus_ids_used": {"kind": "array", "values": [1, 2, 3]},
            "threshold": 0.8,
        },
        network=_network(),
        request=ExecutionRequest(
            capability_id="load_instability_rms",
            simbench_network_code=NETWORK_CODE,
            roi_bbox=(10.8, 11.2, 53.2, 53.5),
        ),
    )

    assert spatial.geojson["type"] == "FeatureCollection"
    assert spatial.layer_type == "network_hotspot"
    assert spatial.geometry_status == "ready"
    features = _feature_list(spatial.geojson)
    points = [item for item in features if item["geometry"]["type"] == "Point"]
    lines = [item for item in features if item["geometry"]["type"] == "LineString"]
    polygons = [item for item in features if item["geometry"]["type"] == "Polygon"]
    assert len(points) == 3
    assert len(lines) == 2
    assert len(polygons) == 1

    by_bus = {item["properties"]["bus_id"]: item["properties"] for item in points}
    assert by_bus[1]["value"] == 0.1
    assert by_bus[1]["severity"] == "low"
    assert by_bus[1]["color"] == COLOR_LOW
    assert by_bus[2]["severity"] == "high"
    assert by_bus[2]["color"] == COLOR_HIGH
    assert by_bus[1]["target_id"] == "t1"
    assert by_bus[1]["name"] == "Bus 1"
    assert by_bus[1]["tags"]["kind"] == "grid_bus"
    assert by_bus[1]["ariadne"]["capability_id"] == "load_instability_rms"
    assert points[0]["geometry"]["coordinates"] == [10.90, 53.30]


def test_local_coordinates_are_not_forced_onto_the_ariadne_map() -> None:
    spec = load_default_registry().get("load_instability_rms")
    spatial = build_spatial_result(
        spec=spec,
        outputs={"instability_index": {"kind": "array", "values": [0.4, 0.7]}},
        network=extract_spatial_network(
            {
                "nodes": [
                    {"bus_id": 1, "x": 500000.0, "y": 5800000.0},
                    {"bus_id": 2, "x": 500100.0, "y": 5800100.0},
                ]
            }
        ),
    )
    assert spatial.geometry_status == "non_geographic"
    assert spatial.feature_count == 0
    assert _feature_list(spatial.geojson) == []
    assert any("WGS84" in warning for warning in spatial.warnings)


def test_missing_geometry_does_not_invent_points() -> None:
    spec = load_default_registry().get("topology_centrality")
    spatial = build_spatial_result(spec=spec, outputs={}, network=None)
    assert spatial.geometry_status == "missing"
    assert spatial.feature_count == 0


def test_adapter_attaches_spatial_result_and_host_payload(plugin: AvailablePlugin) -> None:
    result = plugin.execute(
        ExecutionRequest(
            capability_id="load_instability_rms",
            simbench_network_code=NETWORK_CODE,
            roi_bbox=(10.8, 11.2, 53.2, 53.5),
        )
    )
    assert result.status == "completed"
    assert result.spatial is not None
    assert result.spatial.feature_count >= 3
    output = result.provenance["output"]
    assert isinstance(output, dict)
    assert output["format"] == "GeoJSON"
    assert output["layer_type"] == "network_hotspot"
    assert output["visualization_type"] == "point_choropleth"

    payload = plugin.to_map_payload(result)
    assert payload is not None
    geojson = payload["geojson"]
    assert isinstance(geojson, dict)
    assert geojson["type"] == "FeatureCollection"
    assert payload["feature_count"] == result.spatial.feature_count
    attribution = str(payload["attribution"])
    assert "Not OpenStreetMap" in attribution


def test_export_geojson_is_json_serializable(tmp_path: Path, plugin: AvailablePlugin) -> None:
    result = plugin.execute(
        ExecutionRequest(capability_id="load_instability_rms", simbench_network_code=NETWORK_CODE)
    )
    path = export_geojson(result, tmp_path / "instability.geojson")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["type"] == "FeatureCollection"
    assert loaded["features"]


def test_lisa_uses_engine_cluster_codes_as_classes() -> None:
    spec = load_default_registry().get("lisa_instability")
    spatial = build_spatial_result(
        spec=spec,
        outputs={
            "clusters_instability": {"kind": "array", "values": [0, 1, 2]},
            "cluster_labels_map": {0: "Not Significant", 1: "High-High", 2: "Low-Low"},
            "lisa_instability": {
                "kind": "local_spatial_statistic",
                "Is": {"kind": "array", "values": [0.11, 0.82, -0.21]},
                "p_sim": {"kind": "array", "values": [0.20, 0.01, 0.03]},
            },
            "bus_ids_used": {"kind": "array", "values": [1, 2, 3]},
        },
        network=_network(),
    )
    features = _feature_list(spatial.geojson)
    points = [item for item in features if item["geometry"]["type"] == "Point"]
    lines = [item for item in features if item["geometry"]["type"] == "LineString"]
    assert lines == []
    assert {item["properties"]["cluster_type"] for item in points} == {"HIGH_HIGH", "LOW_LOW"}
    by_type = {item["properties"]["cluster_type"]: item["properties"] for item in points}
    assert by_type["HIGH_HIGH"]["indicator"] == "LISA"
    assert by_type["HIGH_HIGH"]["value"] == 0.82
    assert by_type["HIGH_HIGH"]["p_value"] == 0.01
    assert by_type["HIGH_HIGH"]["color"] == "#dc2626"
    assert by_type["HIGH_HIGH"]["layer_name"] == "GeoLoadST LISA Clusters"
    assert by_type["LOW_LOW"]["color"] == "#2563eb"


def test_topology_centrality_emits_points_with_copied_metrics() -> None:
    spec = load_default_registry().get("topology_centrality")
    spatial = build_spatial_result(
        spec=spec,
        outputs={
            "metrics": {
                "degree": {"kind": "array", "values": [2.0, 3.0, 1.0]},
                "betweenness": {"kind": "array", "values": [0.10, 0.80, 0.00]},
                "closeness": {"kind": "array", "values": [0.40, 0.90, 0.20]},
                "bus_ids": {"kind": "array", "values": [1, 2, 3]},
            }
        },
        network=_network(),
    )
    features = _feature_list(spatial.geojson)
    assert all(item["geometry"]["type"] == "Point" for item in features)
    assert not any(item["geometry"]["type"] == "LineString" for item in features)
    by_bus = {item["properties"]["bus_id"]: item["properties"] for item in features}
    assert set(by_bus) == {1, 2, 3}
    assert by_bus[2]["degree_centrality"] == 3.0
    assert by_bus[2]["betweenness_centrality"] == 0.80
    assert by_bus[2]["closeness_centrality"] == 0.90
    assert by_bus[2]["analysis"] == "topology_centrality"
    assert by_bus[2]["layer_name"] == "GeoLoadST Topology Centrality"
    assert by_bus[2]["visualization_metric"] == "betweenness_centrality"
    assert by_bus[2]["value"] == 0.80
    assert spatial.visualization.layer_name == "GeoLoadST Topology Centrality"


def test_topology_omits_missing_centrality_vectors() -> None:
    spec = load_default_registry().get("topology_centrality")
    spatial = build_spatial_result(
        spec=spec,
        outputs={"metrics": {"degree": {"kind": "array", "values": [0.2, 0.5, 0.1]}}},
        network=_network(),
    )
    features = _feature_list(spatial.geojson)
    props = features[0]["properties"]
    assert "degree_centrality" in props
    assert "betweenness_centrality" not in props
    assert "closeness_centrality" not in props
    assert props["visualization_metric"] == "degree_centrality"


def test_host_payload_is_none_when_there_is_no_geometry() -> None:
    plugin = AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=FakeAnalyzer))
    result = plugin.execute(ExecutionRequest(capability_id="vulnerability_index"))
    assert result.status == "not_bound"
    assert result.spatial is None
    assert to_ariadne_map_payload(result) is None
