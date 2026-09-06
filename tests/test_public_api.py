"""Host-facing API: get_capabilities() and analyze()."""

from __future__ import annotations

import pytest

from ariadne_geoloadst import analyze, get_capabilities
from ariadne_geoloadst.adapter import GeoLoadSTPlugin, _copy_statistics, _to_host_payload
from ariadne_geoloadst.capabilities import UnknownCapabilityError
from ariadne_geoloadst.engine import GeoLoadSTEngine
from ariadne_geoloadst.schemas import ExecutionRequest
from tests.conftest import AvailablePlugin, FakeAnalyzer

NETWORK_CODE = "1-complete_data-mixed-all-1-sw"


def test_get_capabilities_lists_moran_lisa_first() -> None:
    entries = get_capabilities()
    ids = [item["capability_id"] for item in entries]
    assert "moran_lisa" in ids
    assert ids[0] == "moran_lisa"
    moran = next(item for item in entries if item["capability_id"] == "moran_lisa")
    assert moran["domain"] == "energy_grid"
    assert moran["engine"] == "GeoLoadST"
    assert moran["status"] == "bound"
    assert "available" in moran


def test_analyze_rejects_unknown_capability() -> None:
    with pytest.raises(UnknownCapabilityError, match="invented_method"):
        analyze(NETWORK_CODE, "invented_method", {"network_id": NETWORK_CODE})


def test_analyze_rejects_empty_ids() -> None:
    with pytest.raises(ValueError, match="network_id"):
        analyze("  ", "moran_lisa", {})
    with pytest.raises(ValueError, match="capability_id"):
        analyze(NETWORK_CODE, "", {})


def test_analyze_without_engine_returns_structured_empty_result() -> None:
    plugin = GeoLoadSTPlugin()
    if plugin.is_available().status == "available":
        pytest.skip("GeoLoadST is installed in this environment")
    payload = analyze(
        NETWORK_CODE,
        "moran_lisa",
        {"network_id": NETWORK_CODE, "bus_count": 0},
    )
    assert payload["status"] == "unavailable"
    assert payload["capability"] == "moran_lisa"
    assert payload["statistics"] == {}
    assert payload["features"] == []
    assert "detail" in payload


def test_analyze_maps_completed_execute_to_ariadne_shape() -> None:
    plugin = AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=FakeAnalyzer))
    result = plugin.execute(
        ExecutionRequest(
            capability_id="moran_lisa",
            simbench_network_code=NETWORK_CODE,
        )
    )
    assert result.status == "completed"
    payload = _to_host_payload(result, "moran_lisa")
    assert set(payload) >= {"status", "capability", "statistics", "features"}
    assert payload["status"] == "success"
    assert payload["capability"] == "moran_lisa"
    statistics = payload["statistics"]
    assert isinstance(statistics, dict)
    assert statistics["moran_i"] == 0.42
    assert statistics["p_value"] == 0.001
    features = payload["features"]
    assert isinstance(features, list)
    assert features, "LISA cluster points must be forwarded to the host"
    assert all(item["geometry"]["type"] == "Point" for item in features)
    assert {item["properties"]["cluster_type"] for item in features} == {
        "HIGH_HIGH",
        "LOW_LOW",
    }
    assert all(item["properties"]["indicator"] == "LISA" for item in features)
    assert all(
        "value" in item["properties"] and "p_value" in item["properties"] for item in features
    )
    assert all(item["properties"]["layer_name"] == "GeoLoadST LISA Clusters" for item in features)


def test_analyze_forwards_topology_centrality_points() -> None:
    plugin = AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=FakeAnalyzer))
    result = plugin.execute(
        ExecutionRequest(
            capability_id="topology_centrality",
            simbench_network_code=NETWORK_CODE,
        )
    )
    payload = _to_host_payload(result, "topology_centrality")
    features = payload["features"]
    assert isinstance(features, list)
    assert features
    assert all(item["geometry"]["type"] == "Point" for item in features)
    props = features[0]["properties"]
    assert props["analysis"] == "topology_centrality"
    assert props["layer_name"] == "GeoLoadST Topology Centrality"
    assert "degree_centrality" in props
    assert "betweenness_centrality" in props
    assert "closeness_centrality" in props


def test_copy_statistics_reads_normalized_moran_objects() -> None:
    assert _copy_statistics(
        {
            "moran_instability": {
                "kind": "spatial_statistic",
                "statistics": {"I": 0.34, "p_sim": 0.02},
            }
        }
    ) == {"moran_i": 0.34, "p_value": 0.02}
    assert _copy_statistics({"clusters": [1, 0, 4]}) == {}
