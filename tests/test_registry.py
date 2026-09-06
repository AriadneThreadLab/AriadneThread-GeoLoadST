"""Only catalogued capabilities are valid, and only with declared parameters."""

from __future__ import annotations

import pytest

from ariadne_geoloadst.capabilities import (
    CapabilityRegistry,
    InvalidParameterError,
    UnknownCapabilityError,
    load_capability_catalog,
    load_default_registry,
)
from ariadne_geoloadst.schemas import CapabilityCatalog, ExecutionRequest


def test_catalog_contains_inspected_geoloadst_bindings() -> None:
    registry = load_default_registry()
    ids = set(registry.list_ids())
    assert "load_instability_rms" in ids
    assert "lisa_instability" in ids
    assert registry.get("moran_lisa").capability_id == "lisa_instability"
    assert "space_time_variogram" in ids
    assert "topology_centrality" in ids
    spec = registry.get("load_instability_rms")
    assert spec.domain == "energy_grid"
    assert spec.engine == "GeoLoadST"
    assert spec.geoloadst_binding.endswith("rms_instability")
    assert spec.analytical_goal == "load_instability"


def test_unknown_capability_is_rejected() -> None:
    registry = load_default_registry()
    with pytest.raises(UnknownCapabilityError, match="invented_stability_index"):
        registry.get("invented_stability_index")


def test_undeclared_parameter_is_rejected() -> None:
    registry = load_default_registry()
    request = ExecutionRequest(
        capability_id="load_instability_rms",
        parameters={"invented_formula": "x**2"},
    )
    with pytest.raises(UnknownCapabilityError, match="invented_formula"):
        registry.validate_request(request)


def test_valid_request_is_accepted() -> None:
    registry = load_default_registry()
    spec = registry.validate_request(
        ExecutionRequest(
            capability_id="global_moran_instability",
            parameters={"k_neighbors": 8},
            selection_reason="User asked whether unstable nodes are clustered.",
        )
    )
    assert spec.capability_id == "global_moran_instability"


def test_out_of_range_parameter_is_rejected() -> None:
    registry = load_default_registry()
    with pytest.raises(InvalidParameterError, match="k_neighbors"):
        registry.validate_request(
            ExecutionRequest(
                capability_id="global_moran_instability",
                parameters={"k_neighbors": 5000},
            )
        )


def test_parameter_of_wrong_type_is_rejected() -> None:
    registry = load_default_registry()
    with pytest.raises(InvalidParameterError, match="number"):
        registry.validate_request(
            ExecutionRequest(
                capability_id="global_moran_instability",
                parameters={"k_neighbors": "many"},
            )
        )


def test_parameter_outside_declared_choices_is_rejected() -> None:
    registry = load_default_registry()
    with pytest.raises(InvalidParameterError, match="model"):
        registry.validate_request(
            ExecutionRequest(
                capability_id="directional_variogram",
                parameters={"model": "hand_written_kernel"},
            )
        )


def test_resolve_parameters_merges_defaults_with_request() -> None:
    registry = load_default_registry()
    resolved = registry.resolve_parameters(
        ExecutionRequest(
            capability_id="multidim_pca_clustering",
            parameters={"n_clusters": 5},
        )
    )
    assert resolved == {"n_clusters": 5, "n_pca_components": 2}


def test_registry_can_be_filtered_for_selection() -> None:
    registry = load_default_registry()
    goals = registry.filter(analytical_goal="spatial_autocorrelation")
    assert {spec.capability_id for spec in goals} >= {
        "global_moran_instability",
        "spatial_clustering_of_instability",
    }
    assert all(spec.is_executable for spec in registry.filter(executable_only=True))


def test_registry_entries_are_a_compact_selection_view() -> None:
    entry = load_default_registry().get("load_instability_rms").to_registry_entry()
    assert entry == {
        "capability_id": "load_instability_rms",
        "domain": "energy_grid",
        "goal": "load_instability",
        "required_data": ["load_time_series", "node_coordinates"],
        "engine": "GeoLoadST",
        "status": "bound",
    }


def test_extension_catalogs_do_not_require_core_changes() -> None:
    """A future domain (PV suitability, resilience) is added as data, not code."""
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
                    "description": "Illustrates that the registry is open for extension.",
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
    registry = CapabilityRegistry.from_catalogs([load_capability_catalog(), extension])
    assert "pv_suitability_placeholder" in registry.list_ids()
    assert "load_instability_rms" in registry.list_ids()
    assert registry.get("pv_suitability_placeholder").is_executable is False


def test_duplicate_ids_are_rejected() -> None:
    catalog = load_capability_catalog()
    with pytest.raises(ValueError, match="duplicate capability_id"):
        CapabilityRegistry.from_catalogs([catalog, catalog])
