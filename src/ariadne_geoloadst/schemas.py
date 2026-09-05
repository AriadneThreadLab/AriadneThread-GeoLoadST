"""Closed schemas for capability metadata and plugin I/O.

These models are independent of Ariadne Thread's ``app`` package so this
repository can evolve without importing the host application. Ariadne should
map selected fields onto its Indicator Catalog / AnalysisBlock later.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CapabilityId = str
RequirementId = str
AnalyticalGoal = Literal[
    "load_instability",
    "critical_node_detection",
    "spatial_autocorrelation",
    "local_hotspot_detection",
    "spatiotemporal_range",
    "directional_structure",
    "topology_importance",
    "instability_topology_relationship",
    "multidimensional_structure",
    "scenario_comparison",
]
RequirementKind = Literal[
    "load_time_series",
    "node_coordinates",
    "network_topology",
    "spatial_weights",
    "simbench_network",
    "scenario_parameters",
]
CapabilityKind = Literal["primitive", "workflow"]
CapabilityStatus = Literal["declared", "bound", "experimental"]
AvailabilityStatus = Literal[
    "available",
    "package_missing",
    "incompatible_version",
    "optional_dependency_missing",
]
ExecutionStatus = Literal["validated", "unavailable", "rejected", "not_bound"]


class DataRequirement(BaseModel):
    """One named input a capability needs before GeoLoadST may run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: RequirementId = Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")
    kind: RequirementKind
    optional: bool = False
    description: str = Field(min_length=1, max_length=240)


class CapabilityParameter(BaseModel):
    """Declared numeric or categorical parameter. Values are not invented at runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    description: str = Field(min_length=1, max_length=240)
    default: float | int | str | bool | None = None


class CapabilitySpec(BaseModel):
    """One registered GeoLoadST capability. Unknown ids are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: CapabilityId = Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")
    name: str = Field(min_length=2, max_length=80)
    domain: Literal["energy_grid"] = "energy_grid"
    kind: CapabilityKind
    analytical_goal: AnalyticalGoal
    suitable_intents: tuple[str, ...] = Field(min_length=1, max_length=12)
    description: str = Field(min_length=8, max_length=400)
    required_data: tuple[DataRequirement, ...]
    geoloadst_binding: str = Field(min_length=3, max_length=160)
    output_semantics: str = Field(min_length=8, max_length=240)
    units: str = Field(min_length=1, max_length=80)
    limitations: tuple[str, ...] = Field(min_length=1)
    parameters: tuple[CapabilityParameter, ...] = ()
    prerequisites: tuple[CapabilityId, ...] = ()
    status: CapabilityStatus = "declared"
    plugin_id: Literal["ariadne_geoloadst"] = "ariadne_geoloadst"


class CapabilityCatalog(BaseModel):
    """Versioned capability collection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_version: str
    capabilities: tuple[CapabilitySpec, ...] = Field(min_length=1)


class AvailabilityReport(BaseModel):
    """Structured answer to ``GeoLoadSTPlugin.is_available()``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AvailabilityStatus
    package_available: bool
    compatible_version: bool
    installed_version: str | None = None
    supported_version_range: str
    missing: tuple[str, ...] = ()
    detail: str


class ExecutionRequest(BaseModel):
    """Validated request. Extra keys (raw Python, invented methods) are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: CapabilityId
    dataset_id: str | None = Field(default=None, max_length=120)
    simbench_network_code: str | None = Field(default=None, max_length=80)
    parameters: dict[str, float | int | str | bool] = Field(default_factory=dict)
    selection_reason: str = Field(default="", max_length=240)


class ExecutionResult(BaseModel):
    """Normalized plugin result. Scientific payloads are added in a later phase."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ExecutionStatus
    capability_id: CapabilityId
    detail: str
    provenance: dict[str, object]
