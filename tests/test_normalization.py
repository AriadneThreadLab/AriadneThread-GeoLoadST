"""Output normalization: JSON-safe, lossless about provenance, never invented."""

from __future__ import annotations

import json

from ariadne_geoloadst.normalization import (
    MAX_ARRAY_ITEMS,
    TruncationWarningCollector,
    extract_result_keys,
    normalize_result,
)
from tests.conftest import FakeArray, FakeMoran, FakeMoranLocal


def test_arrays_keep_dtype_shape_and_values() -> None:
    normalized = normalize_result(FakeArray([1.0, 2.0], dtype="float64"))
    assert normalized == {
        "kind": "array",
        "dtype": "float64",
        "shape": [2],
        "truncated": False,
        "values": [1.0, 2.0],
    }


def test_nan_and_infinity_become_absent_not_zero() -> None:
    normalized = normalize_result({"space_range": float("nan"), "ratio": float("inf")})
    assert normalized == {"space_range": None, "ratio": None}


def test_moran_objects_become_scalar_diagnostics() -> None:
    normalized = normalize_result(FakeMoran())
    assert isinstance(normalized, dict)
    assert normalized["kind"] == "spatial_statistic"
    assert normalized["statistics"]["I"] == 0.42
    assert normalized["statistics"]["p_sim"] == 0.001


def test_moran_local_objects_keep_per_node_arrays() -> None:
    normalized = normalize_result(FakeMoranLocal())
    assert isinstance(normalized, dict)
    assert normalized["kind"] == "local_spatial_statistic"
    is_vals = normalized["Is"]
    assert isinstance(is_vals, dict)
    assert is_vals["values"] == [0.11, 0.82, -0.21]


def test_engine_handles_are_described_not_serialized() -> None:
    normalized = normalize_result({"weights": object()})
    assert isinstance(normalized, dict)
    handle = normalized["weights"]
    assert isinstance(handle, dict)
    assert handle["kind"] == "engine_object"
    assert handle["type"] == "builtins.object"


def test_large_arrays_are_truncated_and_flagged() -> None:
    warnings = TruncationWarningCollector()
    values = [float(index) for index in range(MAX_ARRAY_ITEMS + 10)]
    normalized = normalize_result(FakeArray(values), warnings=warnings)
    assert isinstance(normalized, dict)
    assert normalized["truncated"] is True
    assert len(normalized["values"]) == MAX_ARRAY_ITEMS
    assert warnings.messages


def test_outputs_are_json_serializable() -> None:
    normalized = normalize_result(
        {
            "instability_index": FakeArray([0.1, 0.2]),
            "moran": FakeMoran(),
            "threshold": 1.5,
            "labels": {0: "Not Significant"},
        }
    )
    assert json.loads(json.dumps(normalized)) == normalized


def test_dotted_result_keys_reach_nested_engine_output() -> None:
    outputs = extract_result_keys(
        {"stv": {"space_range": 120.5, "time_range_hours": 1.5}},
        ("stv.space_range", "stv.time_range_hours"),
    )
    assert outputs == {"stv_space_range": 120.5, "stv_time_range_hours": 1.5}


def test_missing_key_is_reported_rather_than_substituted() -> None:
    warnings = TruncationWarningCollector()
    outputs = extract_result_keys({"present": 1}, ("present", "absent"), warnings=warnings)
    assert outputs == {"present": 1}
    assert any("absent" in message for message in warnings.messages)
