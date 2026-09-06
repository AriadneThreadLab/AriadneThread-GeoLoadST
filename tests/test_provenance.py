"""Provenance records facts about what ran. It never stores reasoning."""

from __future__ import annotations

from ariadne_geoloadst.capabilities import load_default_registry
from ariadne_geoloadst.compatibility import PLUGIN_VERSION
from ariadne_geoloadst.provenance import build_provenance, dataset_fingerprint
from ariadne_geoloadst.schemas import AvailabilityReport, ExecutionRequest


def _availability() -> AvailabilityReport:
    return AvailabilityReport(
        status="available",
        package_available=True,
        compatible_version=True,
        installed_version="0.1.1",
        supported_version_range=">=0.1.0,<0.2.0",
        detail="test",
    )


def test_provenance_records_versions_capability_parameters_and_dataset() -> None:
    spec = load_default_registry().get("load_instability_rms")
    request = ExecutionRequest(
        capability_id="load_instability_rms",
        dataset_id="simbench:1-complete_data-mixed-all-1-sw",
        simbench_network_code="1-complete_data-mixed-all-1-sw",
        parameters={"max_buses": 200},
        selection_reason="User asked which buses fluctuate most.",
    )
    record = build_provenance(
        spec=spec,
        request=request,
        availability=_availability(),
        catalog_version="geoloadst-capabilities-1",
        resolved_parameters={"max_buses": 200, "max_times": 96},
        execution_status="completed",
    )

    assert record["plugin_id"] == "ariadne_geoloadst"
    assert record["plugin_version"] == PLUGIN_VERSION
    assert record["geoloadst_version"] == "0.1.1"
    assert record["capability_id"] == "load_instability_rms"
    assert record["parameters"] == {"max_buses": 200, "max_times": 96}
    assert record["dataset_id"] == "simbench:1-complete_data-mixed-all-1-sw"
    assert record["simbench_network_code"] == "1-complete_data-mixed-all-1-sw"
    assert record["dataset_fingerprint"] == dataset_fingerprint(request)
    assert record["execution_status"] == "completed"
    output = record["output"]
    assert isinstance(output, dict)
    assert output["format"] is None
    assert isinstance(record["duration_ms"], float)
    assert "started_at" in record
    assert "completed_at" in record


def test_provenance_excludes_chain_of_thought() -> None:
    spec = load_default_registry().get("lisa_instability")
    record = build_provenance(
        spec=spec,
        request=ExecutionRequest(capability_id="lisa_instability"),
        availability=_availability(),
    )
    serialized = str(record).lower()
    assert "chain_of_thought" not in record
    assert "think" not in serialized
    assert "reasoning" not in record
    assert "payload" not in record
