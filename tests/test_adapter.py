"""Adapter validation and provenance without scientific execution."""

from __future__ import annotations

from ariadne_geoloadst import GeoLoadSTPlugin
from ariadne_geoloadst.schemas import ExecutionRequest
from ariadne_geoloadst.simbench import SimBenchProvider


def test_execute_unknown_capability_fails_before_engine() -> None:
    plugin = GeoLoadSTPlugin()
    try:
        plugin.execute(ExecutionRequest(capability_id="made_up_method"))
    except Exception as exc:
        assert "made_up_method" in str(exc)
    else:
        raise AssertionError("invented capability must be rejected")


def test_execute_records_provenance_and_does_not_invent_values() -> None:
    plugin = GeoLoadSTPlugin()
    result = plugin.execute(
        ExecutionRequest(
            capability_id="spatial_clustering_of_instability",
            simbench_network_code="1-complete_data-mixed-all-1-sw",
            selection_reason="User asked if high-instability nodes are clustered.",
        )
    )
    assert result.status in {"unavailable", "not_bound"}
    assert result.capability_id == "spatial_clustering_of_instability"
    assert "payload" not in result.provenance
    assert result.provenance["plugin_id"] == "ariadne_geoloadst"
    assert result.provenance["simbench_network_code"] == "1-complete_data-mixed-all-1-sw"
    assert result.provenance["capability_id"] == "spatial_clustering_of_instability"
    assert "chain_of_thought" not in result.provenance
    assert "think" not in str(result.provenance).lower()


def test_simbench_is_not_overpass() -> None:
    provider = SimBenchProvider()
    assert "1-complete_data-mixed-all-1-sw" in provider.available_example_codes()
    assert "Overpass" in provider.describe_limitation()
    assert "city query" in provider.describe_limitation()
