"""GeoLoadST adapter. Scientific algorithms stay in the external package."""

from __future__ import annotations

from ariadne_geoloadst.compatibility import probe_geoloadst
from ariadne_geoloadst.provenance import build_provenance
from ariadne_geoloadst.registry import CapabilityRegistry, load_default_registry
from ariadne_geoloadst.schemas import (
    AvailabilityReport,
    ExecutionRequest,
    ExecutionResult,
)


class GeoLoadSTPlugin:
    """Optional analysis plugin. Importing this class does not import geoloadst."""

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry if registry is not None else load_default_registry()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def is_available(self) -> AvailabilityReport:
        return probe_geoloadst()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Validate a registered capability. Do not invent methods or compute values.

        Phase 1 records provenance and refuses silent scientific execution.
        Phase 2 will dispatch to ``geoloadst.InstabilityAnalyzer`` only after
        this validation succeeds.
        """
        spec = self._registry.validate_request(request)
        availability = self.is_available()
        provenance = build_provenance(spec=spec, request=request, availability=availability)
        if availability.status != "available":
            return ExecutionResult(
                status="unavailable",
                capability_id=spec.capability_id,
                detail=availability.detail,
                provenance=provenance,
            )
        return ExecutionResult(
            status="not_bound",
            capability_id=spec.capability_id,
            detail=(
                f"Capability {spec.capability_id!r} is registered and GeoLoadST is "
                "available, but scientific dispatch is not implemented in this phase."
            ),
            provenance=provenance,
        )
