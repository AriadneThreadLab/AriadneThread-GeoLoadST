"""Adapter contract: validate, dispatch, normalize, record provenance."""

from __future__ import annotations

from typing import Any

import pytest

from ariadne_geoloadst import GeoLoadSTPlugin
from ariadne_geoloadst.capabilities import (
    CapabilityRegistry,
    UnknownCapabilityError,
    load_capability_catalog,
)
from ariadne_geoloadst.engine import DatasetSpec, GeoLoadSTEngine
from ariadne_geoloadst.schemas import CapabilityCatalog, ExecutionRequest
from ariadne_geoloadst.simbench import SimBenchProvider
from tests.conftest import AvailablePlugin, ExplodingAnalyzer, FakeAnalyzer

NETWORK_CODE = "1-complete_data-mixed-all-1-sw"


def _request(capability_id: str, **kwargs: Any) -> ExecutionRequest:
    return ExecutionRequest(
        capability_id=capability_id,
        simbench_network_code=NETWORK_CODE,
        **kwargs,
    )


def test_execute_unknown_capability_fails_before_engine() -> None:
    plugin = GeoLoadSTPlugin()
    with pytest.raises(UnknownCapabilityError, match="made_up_method"):
        plugin.execute(ExecutionRequest(capability_id="made_up_method"))


def test_execute_records_provenance_and_does_not_invent_values() -> None:
    plugin = GeoLoadSTPlugin()
    result = plugin.execute(
        _request(
            "spatial_clustering_of_instability",
            selection_reason="User asked if high-instability nodes are clustered.",
        )
    )
    assert result.status in {"unavailable", "completed", "engine_error", "not_bound"}
    assert result.capability_id == "spatial_clustering_of_instability"
    assert "payload" not in result.provenance
    assert result.provenance["plugin_id"] == "ariadne_geoloadst"
    assert result.provenance["simbench_network_code"] == NETWORK_CODE
    assert result.provenance["capability_id"] == "spatial_clustering_of_instability"
    assert "chain_of_thought" not in result.provenance
    assert "think" not in str(result.provenance).lower()


def test_missing_engine_is_reported_not_raised() -> None:
    """A host without the scientific extra still gets a structured answer."""
    plugin = GeoLoadSTPlugin()
    if plugin.is_available().status == "available":
        pytest.skip("GeoLoadST is installed in this environment")
    result = plugin.execute(_request("load_instability_rms"))
    assert result.status == "unavailable"
    assert result.outputs == {}
    assert result.provenance["availability_status"] == "package_missing"


def test_bound_capability_dispatches_and_normalizes(
    plugin: AvailablePlugin,
    fake_analyzers: list[FakeAnalyzer],
) -> None:
    result = plugin.execute(_request("load_instability_rms"))

    assert result.status == "completed"
    assert [name for name, _ in fake_analyzers[0].calls] == [
        "prepare_data",
        "compute_spatiotemporal_instability",
    ]
    instability = result.outputs["instability_index"]
    assert isinstance(instability, dict)
    assert instability["kind"] == "array"
    assert instability["values"] == [0.4, 1.9, 0.7]
    assert result.outputs["threshold"] == 1.5


def test_catalog_defaults_reach_the_engine(
    plugin: AvailablePlugin,
    fake_analyzers: list[FakeAnalyzer],
) -> None:
    """Declared defaults are forwarded; the adapter never fabricates arguments."""
    plugin.execute(_request("load_instability_rms"))

    _, kwargs = fake_analyzers[0].calls[1]
    assert kwargs == {
        "max_buses": 500,
        "max_times": 96,
        "max_pairs": 200000,
        "random_state": 42,
    }


def test_request_parameters_override_defaults(
    plugin: AvailablePlugin,
    fake_analyzers: list[FakeAnalyzer],
) -> None:
    plugin.execute(_request("global_moran_instability", parameters={"k_neighbors": 12}))

    _, kwargs = fake_analyzers[0].calls[1]
    assert kwargs == {"k_neighbors": 12, "permutations": 999}


def test_workflow_replays_every_declared_step(
    plugin: AvailablePlugin,
    fake_analyzers: list[FakeAnalyzer],
) -> None:
    result = plugin.execute(_request("spatial_clustering_of_instability"))

    assert result.status == "completed"
    assert [name for name, _ in fake_analyzers[0].calls] == [
        "prepare_data",
        "compute_spatiotemporal_instability",
        "compute_moran_analysis",
    ]
    moran = result.outputs["moran_instability"]
    assert isinstance(moran, dict)
    assert moran["kind"] == "spatial_statistic"
    assert moran["statistics"]["I"] == 0.42


def test_dataset_selection_reaches_the_engine_factory(
    plugin: AvailablePlugin,
    fake_analyzers: list[FakeAnalyzer],
) -> None:
    plugin.execute(_request("topology_centrality", roi_fraction=0.25, dt_minutes=30.0))

    dataset = fake_analyzers[0].dataset
    assert dataset.simbench_network_code == NETWORK_CODE
    assert dataset.roi_fraction == 0.25
    assert dataset.dt_minutes == 30.0


def test_declared_capability_is_not_dispatched(
    plugin: AvailablePlugin,
    fake_analyzers: list[FakeAnalyzer],
) -> None:
    result = plugin.execute(_request("vulnerability_index"))

    assert result.status == "not_bound"
    assert result.outputs == {}
    assert fake_analyzers == []


def test_request_without_dataset_is_rejected(plugin: AvailablePlugin) -> None:
    result = plugin.execute(ExecutionRequest(capability_id="load_instability_rms"))

    assert result.status == "rejected"
    assert "SimBench" in result.detail
    assert result.outputs == {}


def test_extension_capability_without_simbench_is_not_forced_through_simbench() -> None:
    """A future domain can be catalogued without changing the adapter core."""
    extension = CapabilityCatalog.model_validate(
        {
            "catalog_version": "example-extension-1",
            "capabilities": [
                {
                    "capability_id": "pv_suitability_placeholder",
                    "name": "Example extension capability",
                    "domain": "energy",
                    "engine": "ExampleEngine",
                    "kind": "primitive",
                    "analytical_goal": "pv_suitability",
                    "suitable_intents": ["example"],
                    "description": "Illustrates a future capability that is not SimBench-backed.",
                    "required_data": [
                        {
                            "requirement_id": "irradiance_series",
                            "kind": "irradiance_series",
                            "description": "Example requirement.",
                        }
                    ],
                    "geoloadst_binding": "not_applicable.example",
                    "output_semantics": "Example output only.",
                    "units": "example",
                    "limitations": ["Not a real capability; used by the extension test."],
                }
            ],
        }
    )
    plugin = AvailablePlugin(
        registry=CapabilityRegistry.from_catalogs([load_capability_catalog(), extension])
    )
    result = plugin.execute(ExecutionRequest(capability_id="pv_suitability_placeholder"))
    assert result.status == "not_bound"
    assert "SimBench" not in result.detail


def test_engine_failure_is_reported_as_engine_error() -> None:
    plugin = AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=ExplodingAnalyzer))
    result = plugin.execute(_request("load_instability_rms"))

    assert result.status == "engine_error"
    assert "No buses available" in result.detail
    assert result.outputs == {}
    assert result.provenance["execution_status"] == "engine_error"


def test_engine_missing_method_is_a_contract_error() -> None:
    class OldEngine(FakeAnalyzer):
        compute_topology_analysis = None  # type: ignore[assignment]

    def factory(dataset: DatasetSpec) -> FakeAnalyzer:
        return OldEngine(dataset)

    plugin = AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=factory))
    result = plugin.execute(_request("topology_centrality"))

    assert result.status == "engine_error"
    assert "compute_topology_analysis" in result.detail


def test_provenance_traces_the_actual_engine_calls(plugin: AvailablePlugin) -> None:
    result = plugin.execute(
        _request(
            "lisa_instability",
            parameters={"k_neighbors": 6},
            selection_reason="User asked where instability hotspots are.",
        )
    )

    provenance = result.provenance
    assert provenance["engine_calls"] == [
        {"method": "prepare_data", "arguments": {}},
        {
            "method": "compute_moran_analysis",
            "arguments": {"k_neighbors": 6, "permutations": 999},
        },
    ]
    assert provenance["engine_entry_point"] == "InstabilityAnalyzer"
    assert provenance["geoloadst_binding"] == "geoloadst.core.moran.local_moran_clusters"
    assert provenance["requested_parameters"] == {"k_neighbors": 6}
    assert provenance["parameters"] == {"k_neighbors": 6, "permutations": 999}
    assert provenance["catalog_version"] == "geoloadst-capabilities-1"
    assert isinstance(provenance["dataset_fingerprint"], str)
    assert isinstance(provenance["duration_ms"], float)
    assert "outputs" not in provenance


def test_missing_result_key_is_warned_not_faked() -> None:
    class PartialAnalyzer(FakeAnalyzer):
        def compute_spatiotemporal_instability(self, **kwargs: Any) -> dict[str, Any]:
            result = super().compute_spatiotemporal_instability(**kwargs)
            del result["threshold"]
            return result

    plugin = AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=PartialAnalyzer))
    result = plugin.execute(_request("load_instability_rms"))

    assert result.status == "completed"
    assert "threshold" not in result.outputs
    assert any("threshold" in warning for warning in result.warnings)


def test_describe_capabilities_marks_availability(plugin: AvailablePlugin) -> None:
    entries = {entry["capability_id"]: entry for entry in plugin.describe_capabilities()}

    assert entries["load_instability_rms"]["available"] is True
    assert entries["vulnerability_index"]["available"] is False
    assert entries["load_instability_rms"]["engine"] == "GeoLoadST"


def test_every_bound_capability_completes_offline(plugin: AvailablePlugin) -> None:
    """Every catalogued engine plan is replayable without GeoLoadST installed."""
    from ariadne_geoloadst.capabilities import load_default_registry

    registry = load_default_registry()
    for spec in registry.filter(executable_only=True):
        result = plugin.execute(_request(spec.capability_id))
        assert result.status == "completed", spec.capability_id
        assert result.outputs, spec.capability_id
        assert result.provenance["engine_entry_point"] == "InstabilityAnalyzer"


def test_simbench_is_not_overpass() -> None:
    provider = SimBenchProvider()
    assert NETWORK_CODE in provider.available_example_codes()
    assert "Overpass" in provider.describe_limitation()
    assert "city query" in provider.describe_limitation()
