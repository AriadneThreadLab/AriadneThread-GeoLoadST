"""Capability registry: the only place a ``capability_id`` becomes real.

The registry is data-driven. A capability is a YAML record describing what a
question needs and which engine callable answers it; adding PV suitability,
grid resilience, spatial clustering or topology analysis later means adding a
catalog file, not editing this module.

A host (Ariadne Thread) may *select* an id. It may not invent one, and it may
not pass a parameter the selected capability does not declare.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path

import yaml

from ariadne_geoloadst.compatibility import CAPABILITY_CATALOG_VERSION, probe_geoloadst
from ariadne_geoloadst.schemas import (
    CapabilityCatalog,
    CapabilityParameter,
    CapabilitySpec,
    ExecutionRequest,
    ParameterValue,
)

_DATA_PATH = Path(__file__).resolve().parent / "data" / "capabilities.yaml"

#: Host-facing ids Ariadne may send. Values are catalog ids; science is unchanged.
HOST_CAPABILITY_ALIASES: dict[str, str] = {
    "moran_lisa": "lisa_instability",
    "lisa": "lisa_instability",
}


class UnknownCapabilityError(ValueError):
    """Raised when a requested capability_id is not in the catalog."""


class InvalidParameterError(ValueError):
    """Raised when a parameter is undeclared or outside its declared domain."""


def load_catalog_file(path: Path) -> CapabilityCatalog:
    """Parse one catalog file. Unknown YAML keys are rejected by the schema."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CapabilityCatalog.model_validate(raw)


@lru_cache(maxsize=1)
def load_capability_catalog() -> CapabilityCatalog:
    """Return the shipped catalog, pinned to the adapter's catalog version."""
    catalog = load_catalog_file(_DATA_PATH)
    if catalog.catalog_version != CAPABILITY_CATALOG_VERSION:
        raise ValueError(
            f"capability catalog version {catalog.catalog_version!r} does not match "
            f"{CAPABILITY_CATALOG_VERSION!r}"
        )
    return catalog


class CapabilityRegistry:
    """Immutable lookup over one or more catalogs."""

    def __init__(self, catalog: CapabilityCatalog) -> None:
        by_id = {item.capability_id: item for item in catalog.capabilities}
        if len(by_id) != len(catalog.capabilities):
            raise ValueError("duplicate capability_id in catalog")
        self._catalog = catalog
        self._by_id = by_id

    @classmethod
    def from_catalogs(cls, catalogs: Sequence[CapabilityCatalog]) -> CapabilityRegistry:
        """Merge extension catalogs onto the shipped one. Ids must stay unique.

        This is the supported extension point for a future domain (PV
        suitability, grid resilience) or a second engine.
        """
        if not catalogs:
            raise ValueError("at least one catalog is required")
        merged: list[CapabilitySpec] = []
        for catalog in catalogs:
            merged.extend(catalog.capabilities)
        return cls(
            CapabilityCatalog(
                catalog_version="+".join(item.catalog_version for item in catalogs),
                capabilities=tuple(merged),
            )
        )

    @property
    def catalog_version(self) -> str:
        return self._catalog.catalog_version

    def list_capabilities(self) -> tuple[CapabilitySpec, ...]:
        return self._catalog.capabilities

    def list_ids(self) -> tuple[str, ...]:
        return tuple(item.capability_id for item in self._catalog.capabilities)

    def list_entries(self) -> tuple[dict[str, object], ...]:
        """Compact records a planner can rank without seeing engine internals."""
        return tuple(item.to_registry_entry() for item in self._catalog.capabilities)

    def filter(
        self,
        *,
        domain: str | None = None,
        analytical_goal: str | None = None,
        engine: str | None = None,
        executable_only: bool = False,
    ) -> tuple[CapabilitySpec, ...]:
        """Narrow the catalog by declared metadata."""
        selected: Iterable[CapabilitySpec] = self._catalog.capabilities
        if domain is not None:
            selected = (item for item in selected if item.domain == domain)
        if analytical_goal is not None:
            selected = (item for item in selected if item.analytical_goal == analytical_goal)
        if engine is not None:
            selected = (item for item in selected if item.engine == engine)
        if executable_only:
            selected = (item for item in selected if item.is_executable)
        return tuple(selected)

    def get(self, capability_id: str) -> CapabilitySpec:
        resolved = resolve_host_capability_id(capability_id)
        try:
            return self._by_id[resolved]
        except KeyError as exc:
            known = ", ".join((*HOST_CAPABILITY_ALIASES, *self.list_ids())) or "none"
            raise UnknownCapabilityError(
                f"unknown capability_id {capability_id!r}; available: {known}"
            ) from exc

    def validate_request(self, request: ExecutionRequest) -> CapabilitySpec:
        """Reject unknown ids, undeclared parameter names and out-of-domain values."""
        spec = self.get(request.capability_id)
        allowed = {item.name for item in spec.parameters}
        unknown = sorted(set(request.parameters) - allowed)
        if unknown:
            raise UnknownCapabilityError(
                f"capability {spec.capability_id!r} does not declare parameters: {unknown}"
            )
        for parameter in spec.parameters:
            if parameter.name in request.parameters:
                _validate_parameter_value(parameter, request.parameters[parameter.name])
        return spec

    def resolve_parameters(self, request: ExecutionRequest) -> dict[str, ParameterValue]:
        """Catalog defaults overridden by the validated request."""
        spec = self.validate_request(request)
        resolved = spec.parameter_defaults()
        resolved.update(request.parameters)
        return resolved


def _is_number(value: ParameterValue | None) -> bool:
    """``bool`` is a subclass of ``int``; a flag is not a quantity."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _validate_parameter_value(parameter: CapabilityParameter, value: ParameterValue) -> None:
    expected = parameter.default
    if isinstance(expected, bool) and not isinstance(value, bool):
        raise InvalidParameterError(f"parameter {parameter.name!r} expects a boolean")
    if isinstance(expected, str) and not isinstance(value, str):
        raise InvalidParameterError(f"parameter {parameter.name!r} expects a string")
    if _is_number(expected) and not _is_number(value):
        raise InvalidParameterError(f"parameter {parameter.name!r} expects a number")
    if parameter.choices and value not in parameter.choices:
        raise InvalidParameterError(
            f"parameter {parameter.name!r} must be one of {list(parameter.choices)}"
        )
    if not _is_number(value):
        return
    if parameter.minimum is not None and value < parameter.minimum:  # type: ignore[operator]
        raise InvalidParameterError(
            f"parameter {parameter.name!r} is below its minimum {parameter.minimum}"
        )
    if parameter.maximum is not None and value > parameter.maximum:  # type: ignore[operator]
        raise InvalidParameterError(
            f"parameter {parameter.name!r} is above its maximum {parameter.maximum}"
        )


def build_engine_arguments(
    parameter_map: Mapping[str, str],
    resolved_parameters: Mapping[str, ParameterValue],
) -> dict[str, ParameterValue]:
    """Translate catalog parameter names into engine keyword arguments.

    Parameters absent from ``resolved_parameters`` are omitted so the engine
    keeps its own documented defaults rather than receiving invented values.
    """
    return {
        engine_kwarg: resolved_parameters[catalog_name]
        for catalog_name, engine_kwarg in parameter_map.items()
        if catalog_name in resolved_parameters
    }


def load_default_registry() -> CapabilityRegistry:
    return CapabilityRegistry(load_capability_catalog())


def resolve_host_capability_id(capability_id: str) -> str:
    """Map a host-facing id such as ``moran_lisa`` onto a catalog id."""
    return HOST_CAPABILITY_ALIASES.get(capability_id, capability_id)


def health_status() -> dict[str, object]:
    """Startup health payload for Ariadne. Does not import ``geoloadst``."""
    report = probe_geoloadst()
    return {
        "geoloadst_available": report.status == "available",
        "version": report.installed_version,
        "capabilities": [str(item["capability_id"]) for item in get_capabilities()],
    }


def get_capabilities() -> list[dict[str, object]]:
    """Public catalog for Ariadne. ``moran_lisa`` is listed as a first-class id."""
    registry = load_default_registry()
    engine_ready = probe_geoloadst().status == "available"
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for host_id, catalog_id in HOST_CAPABILITY_ALIASES.items():
        spec = registry.get(catalog_id)
        entry = spec.to_registry_entry()
        entry["capability_id"] = host_id
        entry["available"] = bool(engine_ready and spec.is_executable)
        entries.append(entry)
        seen.add(host_id)
    for spec in registry.list_capabilities():
        if spec.capability_id in seen:
            continue
        entry = spec.to_registry_entry()
        entry["available"] = bool(engine_ready and spec.is_executable)
        entries.append(entry)
    return entries
