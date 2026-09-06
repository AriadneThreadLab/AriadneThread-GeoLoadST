"""The adapter boundary: validate, prepare, call, normalize, record.

No scientific calculation happens here. Every number in an
:class:`~ariadne_geoloadst.schemas.ExecutionResult` was produced by GeoLoadST
and reshaped by :mod:`ariadne_geoloadst.normalization`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ariadne_geoloadst.capabilities import (
    CapabilityRegistry,
    InvalidParameterError,
    UnknownCapabilityError,
    load_default_registry,
)
from ariadne_geoloadst.compatibility import probe_geoloadst
from ariadne_geoloadst.engine import (
    DatasetSpec,
    EngineError,
    EngineNotAvailableError,
    EngineRun,
    GeoLoadSTEngine,
)
from ariadne_geoloadst.provenance import build_provenance, new_run_id, utc_now
from ariadne_geoloadst.schemas import (
    AvailabilityReport,
    CapabilitySpec,
    ExecutionRequest,
    ExecutionResult,
    SpatialAnalysisResult,
)
from ariadne_geoloadst.visualization import build_spatial_result, to_ariadne_map_payload


class GeoLoadSTPlugin:
    """Optional analysis plugin. Importing this class does not import geoloadst."""

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        engine: GeoLoadSTEngine | None = None,
    ) -> None:
        self._registry = registry if registry is not None else load_default_registry()
        self._engine = engine if engine is not None else GeoLoadSTEngine()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def is_available(self) -> AvailabilityReport:
        """Environment probe. Safe to call at host startup."""
        return probe_geoloadst()

    def describe_capabilities(self) -> tuple[dict[str, object], ...]:
        """Selection view for a planner, annotated with current availability."""
        engine_ready = self.is_available().status == "available"
        entries: list[dict[str, object]] = []
        for spec in self._registry.list_capabilities():
            entry = spec.to_registry_entry()
            entry["available"] = bool(engine_ready and spec.is_executable)
            entries.append(entry)
        return tuple(entries)

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Run one registered capability through GeoLoadST.

        Unknown ids and undeclared parameters raise before the engine is
        touched. A capability without an engine plan, or a missing engine,
        returns a status instead of a fabricated result.
        """
        run_id = new_run_id()
        started_at = utc_now()
        spec = self._registry.validate_request(request)
        parameters = self._registry.resolve_parameters(request)
        availability = self.is_available()

        def finish(
            status: str,
            detail: str,
            run: EngineRun | None = None,
        ) -> ExecutionResult:
            spatial: SpatialAnalysisResult | None = None
            extra_warnings: tuple[str, ...] = ()
            if status == "completed" and run is not None:
                spatial = build_spatial_result(
                    spec=spec,
                    outputs=run.outputs,
                    network=run.network,
                    request=request,
                )
                extra_warnings = spatial.warnings
            provenance = build_provenance(
                spec=spec,
                request=request,
                availability=availability,
                catalog_version=self._registry.catalog_version,
                resolved_parameters=parameters,
                run_id=run_id,
                started_at=started_at,
                completed_at=utc_now(),
                invocations=run.invocations if run is not None else (),
                execution_status=status,
                spatial=spatial,
            )
            warnings = (run.warnings if run is not None else ()) + extra_warnings
            return ExecutionResult(
                status=status,  # type: ignore[arg-type]
                capability_id=spec.capability_id,
                detail=detail,
                outputs=run.outputs if run is not None else {},
                warnings=warnings,
                provenance=provenance,
                spatial=spatial,
            )

        if availability.status != "available":
            return finish("unavailable", availability.detail)

        if not spec.is_executable:
            return finish(
                "not_bound",
                f"Capability {spec.capability_id!r} is catalogued but has no engine plan yet; "
                f"its binding {spec.geoloadst_binding} is not reachable through "
                "InstabilityAnalyzer.",
            )

        rejection = _dataset_rejection(spec, request)
        if rejection is not None:
            return finish("rejected", rejection)

        try:
            run = self._engine.run(
                spec=spec,
                dataset=DatasetSpec.from_request(request),
                parameters=parameters,
            )
        except EngineNotAvailableError as exc:
            return finish("unavailable", str(exc))
        except EngineError as exc:
            return finish("engine_error", str(exc))

        return finish(
            "completed",
            f"GeoLoadST computed {spec.capability_id!r} via {spec.geoloadst_binding}.",
            run,
        )

    def to_map_payload(self, result: ExecutionResult) -> dict[str, object] | None:
        """Ariadne-compatible ``geojson`` slice. Does not render a map."""
        return to_ariadne_map_payload(result)


#: Requirement kinds the current SimBench provider can satisfy.
_SIMBENCH_BACKED_KINDS = frozenset(
    {
        "load_time_series",
        "node_coordinates",
        "network_topology",
        "simbench_network",
    }
)


def _dataset_rejection(spec: CapabilitySpec, request: ExecutionRequest) -> str | None:
    """Refuse to run when a required, SimBench-backed input cannot be sourced.

    A future catalog entry (for example PV suitability) that does not declare
    these kinds is not forced through SimBench.
    """
    needs_simbench = any(
        item.kind in _SIMBENCH_BACKED_KINDS and not item.optional for item in spec.required_data
    )
    if needs_simbench and request.simbench_network_code is None:
        return (
            f"Capability {spec.capability_id!r} needs a network and load profiles, but the "
            "request selected no SimBench network code. SimBench is a named dataset, not a "
            "place query."
        )
    return None


def analyze(
    network_id: str,
    capability_id: str,
    network_data: Mapping[str, Any] | object | None = None,
) -> dict[str, object]:
    """Public Ariadne entry point. This package never imports ``app``.

    ``network_data`` is the host-supplied loaded-network snapshot. The current
    GeoLoadST engine still materializes the SimBench case from ``network_id``;
    the snapshot is accepted so Ariadne can pass data without a type coupling.
    """
    del network_data
    if not isinstance(network_id, str) or not network_id.strip():
        raise ValueError("network_id must be a non-empty string")
    if not isinstance(capability_id, str) or not capability_id.strip():
        raise ValueError("capability_id must be a non-empty string")
    requested = capability_id.strip()
    result = GeoLoadSTPlugin().execute(
        ExecutionRequest(
            capability_id=requested,
            simbench_network_code=network_id.strip(),
        )
    )
    return _to_host_payload(result, requested)


def _to_host_payload(result: ExecutionResult, requested_capability: str) -> dict[str, object]:
    """Ariadne-facing dict. Empty statistics/features mean the engine produced none."""
    status: str = "success" if result.status == "completed" else result.status
    return {
        "status": status,
        "capability": requested_capability,
        "statistics": _copy_statistics(result.outputs),
        "features": _features_from_result(result),
        "detail": result.detail,
        "warnings": list(result.warnings),
    }


def _copy_statistics(outputs: Mapping[str, Any]) -> dict[str, float]:
    """Copy finite scalars GeoLoadST already computed. Never invent values."""
    stats: dict[str, float] = {}
    _take(stats, outputs, "moran_i", ("moran_i", "morans_i", "I", "Moran_I"))
    _take(stats, outputs, "p_value", ("p_value", "p_sim", "pvalue", "p"))
    nested = outputs.get("moran_instability")
    if isinstance(nested, Mapping):
        inner = nested.get("statistics")
        source = inner if isinstance(inner, Mapping) else nested
        _take(stats, source, "moran_i", ("moran_i", "morans_i", "I", "Moran_I", "I_obs"))
        _take(stats, source, "p_value", ("p_value", "p_sim", "pvalue", "p"))
    elif "moran_i" not in stats:
        number = _as_finite_float(nested)
        if number is not None:
            stats["moran_i"] = number
    return stats


def _features_from_result(result: ExecutionResult) -> list[object]:
    spatial = result.spatial
    if spatial is None:
        return []
    geojson = spatial.geojson
    features = geojson.get("features") if isinstance(geojson, dict) else None
    # Pydantic model_dump keeps FeatureCollection.features as a tuple.
    if not isinstance(features, list | tuple):
        return []
    items: list[object] = [item for item in features if isinstance(item, dict)]
    if result.capability_id in {"lisa_instability", "moran_lisa"}:
        return [item for item in items if _is_lisa_cluster_feature(item)]
    if result.capability_id == "topology_centrality":
        return [item for item in items if _is_topology_overlay_feature(item)]
    return items


def _is_topology_overlay_feature(feature: object) -> bool:
    if not isinstance(feature, dict):
        return False
    geometry = feature.get("geometry")
    props = feature.get("properties")
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return False
    if not isinstance(props, dict):
        return False
    if props.get("analysis") == "topology_centrality":
        return True
    return props.get("layer_name") == "GeoLoadST Topology Centrality"


def _is_lisa_cluster_feature(feature: object) -> bool:
    if not isinstance(feature, dict):
        return False
    geometry = feature.get("geometry")
    props = feature.get("properties")
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return False
    if not isinstance(props, dict):
        return False
    return props.get("indicator") == "LISA" and props.get("cluster_type") in {
        "HIGH_HIGH",
        "LOW_LOW",
        "HIGH_LOW",
        "LOW_HIGH",
    }


def _take(
    dest: dict[str, float],
    source: Mapping[str, Any],
    dest_key: str,
    aliases: tuple[str, ...],
) -> None:
    if dest_key in dest:
        return
    for alias in aliases:
        number = _as_finite_float(source.get(alias))
        if number is not None:
            dest[dest_key] = number
            return


def _as_finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        number = float(value)
        if math.isfinite(number):
            return number
    return None


__all__ = [
    "GeoLoadSTPlugin",
    "InvalidParameterError",
    "UnknownCapabilityError",
    "analyze",
]
