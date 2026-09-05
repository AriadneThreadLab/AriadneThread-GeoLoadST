"""Only catalogued capabilities are valid."""

from __future__ import annotations

import pytest

from ariadne_geoloadst.registry import UnknownCapabilityError, load_default_registry
from ariadne_geoloadst.schemas import ExecutionRequest


def test_catalog_contains_inspected_geoloadst_bindings() -> None:
    registry = load_default_registry()
    ids = set(registry.list_ids())
    assert "load_instability_rms" in ids
    assert "lisa_instability" in ids
    assert "space_time_variogram" in ids
    assert "topology_centrality" in ids
    spec = registry.get("load_instability_rms")
    assert spec.domain == "energy_grid"
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
