"""Structured scientific provenance. No chain-of-thought is recorded.

Everything here is a fact about *what ran*: which capability was selected,
which engine callable answered it, on which dataset, with which effective
parameters, and how long it took. Model deliberation is never stored.
"""

from __future__ import annotations

import hashlib
import json
import platform
import uuid
from datetime import datetime, timezone

from ariadne_geoloadst.compatibility import (
    ADAPTER_VERSION,
    PLUGIN_ID,
    PLUGIN_VERSION,
)
from ariadne_geoloadst.schemas import (
    AvailabilityReport,
    CapabilitySpec,
    EngineInvocation,
    ExecutionRequest,
    ParameterValue,
    SpatialAnalysisResult,
)


def new_run_id() -> str:
    """Opaque identifier so a host can correlate a trace with a result."""
    return uuid.uuid4().hex


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def dataset_fingerprint(request: ExecutionRequest) -> str:
    """Stable digest of the dataset selection, for reproducibility checks."""
    payload = {
        "dataset_id": request.dataset_id,
        "simbench_network_code": request.simbench_network_code,
        "roi_bbox": list(request.roi_bbox) if request.roi_bbox is not None else None,
        "roi_fraction": request.roi_fraction,
        "time_window": list(request.time_window) if request.time_window is not None else None,
        "dt_minutes": request.dt_minutes,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def build_provenance(
    *,
    spec: CapabilitySpec,
    request: ExecutionRequest,
    availability: AvailabilityReport,
    catalog_version: str | None = None,
    resolved_parameters: dict[str, ParameterValue] | None = None,
    run_id: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    invocations: tuple[EngineInvocation, ...] = (),
    execution_status: str | None = None,
    spatial: SpatialAnalysisResult | None = None,
) -> dict[str, object]:
    """Compact, serialisable provenance for Ariadne traces."""
    started = started_at if started_at is not None else utc_now()
    completed = completed_at if completed_at is not None else started
    plan = spec.engine_call

    record: dict[str, object] = {
        "run_id": run_id if run_id is not None else new_run_id(),
        "plugin_id": PLUGIN_ID,
        "plugin_version": PLUGIN_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "capability_id": spec.capability_id,
        "capability_kind": spec.kind,
        "capability_status": spec.status,
        "analytical_goal": spec.analytical_goal,
        "domain": spec.domain,
        "engine": spec.engine,
        "selection_reason": request.selection_reason,
        "geoloadst_binding": spec.geoloadst_binding,
        "geoloadst_version": availability.installed_version,
        "geoloadst_version_range": availability.supported_version_range,
        "availability_status": availability.status,
        "catalog_version": catalog_version,
        "dataset_id": request.dataset_id,
        "simbench_network_code": request.simbench_network_code,
        "dataset_fingerprint": dataset_fingerprint(request),
        "roi_bbox": list(request.roi_bbox) if request.roi_bbox is not None else None,
        "roi_fraction": request.roi_fraction,
        "time_window": list(request.time_window) if request.time_window is not None else None,
        "dt_minutes": request.dt_minutes,
        "requested_parameters": dict(request.parameters),
        "parameters": dict(resolved_parameters or request.parameters),
        "required_data": [item.requirement_id for item in spec.required_data],
        "limitations": list(spec.limitations),
        "engine_entry_point": plan.entry_point if plan is not None else None,
        "engine_calls": [
            {"method": item.method, "arguments": dict(item.arguments)} for item in invocations
        ],
        "execution_status": execution_status,
        "output": _output_record(spatial),
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "duration_ms": round((completed - started).total_seconds() * 1000.0, 3),
        "python_version": platform.python_version(),
        "recorded_at": utc_now().isoformat(),
    }
    return record


def _output_record(spatial: SpatialAnalysisResult | None) -> dict[str, object]:
    """Map-layer facts only. Scientific numbers stay in ExecutionResult.outputs."""
    if spatial is None:
        return {
            "format": None,
            "layer_type": None,
            "layer_id": None,
            "visualization_type": None,
            "feature_count": 0,
        }
    primary = spatial.layers[0] if spatial.layers else None
    return {
        "format": "GeoJSON",
        "layer_type": spatial.layer_type,
        "layer_id": primary.layer_id if primary is not None else None,
        "visualization_type": spatial.visualization.visualization_type,
        "feature_count": spatial.feature_count,
        "geometry_status": spatial.geometry_status,
        "crs": spatial.visualization.crs,
        "indicator": spatial.indicator,
    }
