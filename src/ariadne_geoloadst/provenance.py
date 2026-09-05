"""Structured scientific provenance. No chain-of-thought is recorded."""

from __future__ import annotations

from datetime import datetime, timezone

from ariadne_geoloadst.compatibility import (
    ADAPTER_VERSION,
    PLUGIN_ID,
    PLUGIN_VERSION,
)
from ariadne_geoloadst.schemas import AvailabilityReport, CapabilitySpec, ExecutionRequest


def build_provenance(
    *,
    spec: CapabilitySpec,
    request: ExecutionRequest,
    availability: AvailabilityReport,
) -> dict[str, object]:
    """Compact, serialisable provenance for Ariadne traces."""
    return {
        "plugin_id": PLUGIN_ID,
        "plugin_version": PLUGIN_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "capability_id": spec.capability_id,
        "capability_kind": spec.kind,
        "analytical_goal": spec.analytical_goal,
        "domain": spec.domain,
        "selection_reason": request.selection_reason,
        "geoloadst_binding": spec.geoloadst_binding,
        "geoloadst_version": availability.installed_version,
        "geoloadst_version_range": availability.supported_version_range,
        "availability_status": availability.status,
        "dataset_id": request.dataset_id,
        "simbench_network_code": request.simbench_network_code,
        "parameters": dict(request.parameters),
        "required_data": [item.requirement_id for item in spec.required_data],
        "limitations": list(spec.limitations),
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
    }
