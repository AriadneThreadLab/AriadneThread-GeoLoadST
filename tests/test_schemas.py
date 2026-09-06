"""Schema validation: malformed catalog records and requests must not load."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ariadne_geoloadst.capabilities import load_capability_catalog
from ariadne_geoloadst.schemas import (
    CapabilitySpec,
    ExecutionRequest,
    ExecutionResult,
)

_MINIMAL_SPEC: dict[str, Any] = {
    "capability_id": "example_capability",
    "name": "Example",
    "kind": "primitive",
    "analytical_goal": "load_instability",
    "suitable_intents": ["example"],
    "description": "A minimal well-formed capability record.",
    "required_data": [
        {
            "requirement_id": "load_time_series",
            "kind": "load_time_series",
            "description": "Example requirement.",
        }
    ],
    "geoloadst_binding": "geoloadst.core.instability_index.rms_instability",
    "output_semantics": "Example output semantics.",
    "units": "dimensionless",
    "limitations": ["Example limitation."],
}


def _spec(**overrides: Any) -> dict[str, Any]:
    return {**_MINIMAL_SPEC, **overrides}


def test_minimal_spec_is_valid() -> None:
    spec = CapabilitySpec.model_validate(_spec())
    assert spec.status == "declared"
    assert spec.is_executable is False


def test_unknown_catalog_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CapabilitySpec.model_validate(_spec(secret_python_hook="os.system"))


def test_capability_id_must_be_a_snake_case_identifier() -> None:
    with pytest.raises(ValidationError):
        CapabilitySpec.model_validate(_spec(capability_id="Not An Id"))


def test_limitations_are_mandatory() -> None:
    with pytest.raises(ValidationError):
        CapabilitySpec.model_validate(_spec(limitations=[]))


def test_bound_capability_requires_an_engine_plan() -> None:
    with pytest.raises(ValidationError, match="declares no engine_call"):
        CapabilitySpec.model_validate(_spec(status="bound"))


def test_engine_plan_cannot_map_an_undeclared_parameter() -> None:
    plan = {
        "steps": [
            {
                "method": "compute_spatiotemporal_instability",
                "purpose": "Example step.",
                "parameter_map": {"undeclared_knob": "max_buses"},
            }
        ],
        "result_keys": ["instability_index"],
    }
    with pytest.raises(ValidationError, match="undeclared parameters"):
        CapabilitySpec.model_validate(_spec(status="bound", engine_call=plan))


def test_result_keys_must_be_plain_dotted_paths() -> None:
    plan = {
        "steps": [{"method": "prepare_data", "purpose": "Example step."}],
        "result_keys": ["__class__.__init__"],
    }
    with pytest.raises(ValidationError, match="invalid result key"):
        CapabilitySpec.model_validate(_spec(status="bound", engine_call=plan))


def test_parameter_default_must_match_its_choices() -> None:
    parameter = {
        "name": "model",
        "description": "Example parameter.",
        "default": "not_a_choice",
        "choices": ["spherical", "exponential"],
    }
    with pytest.raises(ValidationError, match="not one of its choices"):
        CapabilitySpec.model_validate(_spec(parameters=[parameter]))


def test_request_rejects_raw_python_and_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        ExecutionRequest.model_validate(
            {"capability_id": "load_instability_rms", "code": "import os"}
        )


def test_request_rejects_conflicting_roi_selection() -> None:
    with pytest.raises(ValidationError, match="not both"):
        ExecutionRequest(
            capability_id="load_instability_rms",
            roi_bbox=(0.0, 1.0, 0.0, 1.0),
            roi_fraction=0.5,
        )


def test_request_rejects_a_reversed_time_window() -> None:
    with pytest.raises(ValidationError, match="increasing"):
        ExecutionRequest(capability_id="load_instability_rms", time_window=(96, 0))


def test_request_rejects_an_out_of_range_roi_fraction() -> None:
    with pytest.raises(ValidationError):
        ExecutionRequest(capability_id="load_instability_rms", roi_fraction=1.5)


def test_result_is_frozen_so_a_host_cannot_edit_science() -> None:
    result = ExecutionResult(
        status="completed",
        capability_id="load_instability_rms",
        detail="Example.",
        outputs={"instability_index": {"kind": "array", "values": [1.0]}},
        provenance={"plugin_id": "ariadne_geoloadst"},
    )
    with pytest.raises(ValidationError):
        result.status = "rejected"


def test_every_shipped_capability_declares_a_limitation_and_units() -> None:
    for spec in load_capability_catalog().capabilities:
        assert spec.limitations, spec.capability_id
        assert spec.units, spec.capability_id
        assert spec.output_semantics, spec.capability_id


def test_shipped_prerequisites_reference_real_capabilities() -> None:
    catalog = load_capability_catalog()
    known = {spec.capability_id for spec in catalog.capabilities}
    for spec in catalog.capabilities:
        assert set(spec.prerequisites) <= known, spec.capability_id
