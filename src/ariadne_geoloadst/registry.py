"""Closed capability registry. The LLM may select ids; it may not invent them."""

from __future__ import annotations

from ariadne_geoloadst.capabilities import load_capability_catalog
from ariadne_geoloadst.schemas import CapabilityCatalog, CapabilitySpec, ExecutionRequest


class UnknownCapabilityError(ValueError):
    """Raised when a requested capability_id is not in the catalog."""


class CapabilityRegistry:
    """Immutable lookup over the YAML catalog."""

    def __init__(self, catalog: CapabilityCatalog) -> None:
        by_id = {item.capability_id: item for item in catalog.capabilities}
        if len(by_id) != len(catalog.capabilities):
            raise ValueError("duplicate capability_id in catalog")
        self._catalog = catalog
        self._by_id = by_id

    @property
    def catalog_version(self) -> str:
        return self._catalog.catalog_version

    def list_capabilities(self) -> tuple[CapabilitySpec, ...]:
        return self._catalog.capabilities

    def list_ids(self) -> tuple[str, ...]:
        return tuple(item.capability_id for item in self._catalog.capabilities)

    def get(self, capability_id: str) -> CapabilitySpec:
        try:
            return self._by_id[capability_id]
        except KeyError as exc:
            known = ", ".join(self.list_ids()) or "none"
            raise UnknownCapabilityError(
                f"unknown capability_id {capability_id!r}; available: {known}"
            ) from exc

    def validate_request(self, request: ExecutionRequest) -> CapabilitySpec:
        """Reject unknown ids and undeclared parameter names."""
        spec = self.get(request.capability_id)
        allowed = {item.name for item in spec.parameters}
        unknown = sorted(set(request.parameters) - allowed)
        if unknown:
            raise UnknownCapabilityError(
                f"capability {spec.capability_id!r} does not declare parameters: {unknown}"
            )
        return spec


def load_default_registry() -> CapabilityRegistry:
    return CapabilityRegistry(load_capability_catalog())
