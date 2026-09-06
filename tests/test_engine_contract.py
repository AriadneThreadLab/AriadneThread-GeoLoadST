"""The catalog may only name engine callables that GeoLoadST actually exposes.

The offline check compares every plan against the public surface inspected at
GeoLoadST main ``079dc2cb`` (tags v0.1.0, v0.1.1). When the scientific extra
happens to be installed, the same check runs against the imported class.
"""

from __future__ import annotations

import pytest

from ariadne_geoloadst.capabilities import load_capability_catalog
from ariadne_geoloadst.compatibility import probe_geoloadst
from ariadne_geoloadst.engine import (
    DatasetSpec,
    EngineNotAvailableError,
    default_analyzer_factory,
)

#: Public methods of geoloadst.api.InstabilityAnalyzer at the inspected commit.
INSPECTED_ANALYZER_METHODS = frozenset(
    {
        "prepare_data",
        "compute_spatiotemporal_instability",
        "compute_directional_variograms",
        "compute_local_anisotropy",
        "compute_multidim_instability",
        "compute_moran_analysis",
        "run_industrial_daynight_scenario",
        "compute_topology_analysis",
        "run_full_workflow",
        "get_summary",
    }
)

#: Top-level GeoLoadST modules the catalog is allowed to cite.
INSPECTED_BINDING_ROOTS = (
    "geoloadst.core.",
    "geoloadst.io.",
    "geoloadst.scenarios.",
    "geoloadst.api.",
)


def test_every_plan_uses_an_inspected_analyzer_method() -> None:
    for spec in load_capability_catalog().capabilities:
        plan = spec.engine_call
        if plan is None:
            continue
        assert plan.entry_point == "InstabilityAnalyzer", spec.capability_id
        if plan.preparation is not None:
            assert plan.preparation in INSPECTED_ANALYZER_METHODS, spec.capability_id
        for step in plan.steps:
            assert step.method in INSPECTED_ANALYZER_METHODS, (
                f"{spec.capability_id} names unknown engine method {step.method!r}"
            )


def test_every_binding_points_into_geoloadst() -> None:
    for spec in load_capability_catalog().capabilities:
        assert spec.geoloadst_binding.startswith(INSPECTED_BINDING_ROOTS), spec.capability_id


def test_bound_capabilities_declare_result_keys() -> None:
    for spec in load_capability_catalog().capabilities:
        if spec.status != "bound":
            continue
        assert spec.engine_call is not None
        assert spec.engine_call.result_keys, spec.capability_id


def test_declared_capabilities_have_no_plan() -> None:
    for spec in load_capability_catalog().capabilities:
        if spec.status == "declared":
            assert spec.engine_call is None, spec.capability_id
            assert spec.is_executable is False


def test_default_factory_refuses_to_guess_a_dataset() -> None:
    with pytest.raises(EngineNotAvailableError, match="SimBench network code"):
        default_analyzer_factory(DatasetSpec(simbench_network_code=None))


def test_plans_match_the_installed_engine() -> None:
    """Runs only where GeoLoadST is installed; never downloads anything."""
    if probe_geoloadst().status != "available":
        pytest.skip("GeoLoadST is not installed in this environment")

    from geoloadst import InstabilityAnalyzer

    for spec in load_capability_catalog().capabilities:
        plan = spec.engine_call
        if plan is None:
            continue
        for method in [plan.preparation, *(step.method for step in plan.steps)]:
            if method is None:
                continue
            assert hasattr(InstabilityAnalyzer, method), (
                f"{spec.capability_id} requires InstabilityAnalyzer.{method}"
            )
