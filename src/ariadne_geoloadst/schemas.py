"""Closed schemas for capability metadata and plugin I/O.

These models are independent of Ariadne Thread's ``app`` package so this
repository can evolve without importing the host application. Ariadne should
map selected fields onto its Indicator Catalog / AnalysisBlock later.

Vocabulary fields (``domain``, ``analytical_goal``, ``kind`` of a data
requirement) are pattern-validated rather than hard ``Literal`` enums so that
a future catalog entry -- PV suitability, grid resilience, a second engine --
can be added as data without editing this module. The safety guarantee is
*catalog closure*: a host may only select a ``capability_id`` that exists in a
loaded catalog, and may only pass parameters that the catalog declares.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CapabilityId = str
RequirementId = str

#: Identifier style shared by capability ids, requirement ids, goals and domains.
_ID_PATTERN = r"^[a-z][a-z0-9_]{2,47}$"
_PARAM_PATTERN = r"^[a-z][a-z0-9_]{1,31}$"
_METHOD_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
#: Dotted extraction path into an engine result mapping, e.g. ``stv.space_range``.
_RESULT_KEY_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"

#: Goals present in the shipped catalog. Informational; not an enforcement list.
KNOWN_ANALYTICAL_GOALS: frozenset[str] = frozenset(
    {
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
    }
)

#: Data kinds the shipped catalog requires. Informational; not an enforcement list.
KNOWN_REQUIREMENT_KINDS: frozenset[str] = frozenset(
    {
        "load_time_series",
        "node_coordinates",
        "network_topology",
        "spatial_weights",
        "simbench_network",
        "scenario_parameters",
    }
)

CapabilityKind = Literal["primitive", "workflow"]
#: ``declared`` = catalogued only; ``bound`` = has an executable engine call.
CapabilityStatus = Literal["declared", "bound", "experimental"]
AvailabilityStatus = Literal[
    "available",
    "package_missing",
    "incompatible_version",
    "optional_dependency_missing",
]
ExecutionStatus = Literal[
    "completed",
    "not_bound",
    "unavailable",
    "rejected",
    "engine_error",
]
ParameterValue = float | int | str | bool


class DataRequirement(BaseModel):
    """One named input a capability needs before GeoLoadST may run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requirement_id: RequirementId = Field(pattern=_ID_PATTERN)
    kind: str = Field(pattern=_ID_PATTERN)
    optional: bool = False
    description: str = Field(min_length=1, max_length=240)


class CapabilityParameter(BaseModel):
    """Declared numeric or categorical parameter. Values are not invented at runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=_PARAM_PATTERN)
    description: str = Field(min_length=1, max_length=240)
    default: ParameterValue | None = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _check_bounds(self) -> CapabilityParameter:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"parameter {self.name!r} has minimum greater than maximum")
        if self.choices and not isinstance(self.default, str | type(None)):
            raise ValueError(f"parameter {self.name!r} declares choices but a non-string default")
        if self.choices and isinstance(self.default, str) and self.default not in self.choices:
            raise ValueError(f"parameter {self.name!r} default is not one of its choices")
        return self


class EngineStep(BaseModel):
    """One call on the engine entry point.

    ``parameter_map`` translates catalog parameter names to engine keyword
    names. Only declared parameters are ever forwarded, so a host cannot reach
    an engine argument that the catalog does not expose.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str = Field(pattern=_METHOD_PATTERN)
    purpose: str = Field(min_length=4, max_length=200)
    parameter_map: dict[str, str] = Field(default_factory=dict)


class EngineCall(BaseModel):
    """Declarative plan describing how a capability reaches the engine.

    The plugin never chooses methods at runtime: it replays this plan. Adding
    a capability therefore means adding catalog data, not adapter code.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_point: str = "InstabilityAnalyzer"
    #: Method that materializes buses, coordinates and load profiles.
    preparation: str | None = Field(default="prepare_data", pattern=_METHOD_PATTERN)
    steps: tuple[EngineStep, ...] = Field(min_length=1)
    #: Keys (dotted paths allowed) read from the final step's result mapping.
    result_keys: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_result_keys(self) -> EngineCall:
        for key in self.result_keys:
            if not re.fullmatch(_RESULT_KEY_PATTERN, key):
                raise ValueError(f"invalid result key {key!r}")
        return self


class CapabilitySpec(BaseModel):
    """One registered scientific capability. Unknown ids are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: CapabilityId = Field(pattern=_ID_PATTERN)
    name: str = Field(min_length=2, max_length=80)
    domain: str = Field(default="energy_grid", pattern=_ID_PATTERN)
    engine: str = Field(default="GeoLoadST", min_length=2, max_length=40)
    kind: CapabilityKind
    analytical_goal: str = Field(pattern=_ID_PATTERN)
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
    engine_call: EngineCall | None = None
    plugin_id: Literal["ariadne_geoloadst"] = "ariadne_geoloadst"

    @model_validator(mode="after")
    def _check_binding_state(self) -> CapabilitySpec:
        if self.status == "bound" and self.engine_call is None:
            raise ValueError(
                f"capability {self.capability_id!r} is marked bound but declares no engine_call"
            )
        if self.engine_call is not None:
            declared = {item.name for item in self.parameters}
            for step in self.engine_call.steps:
                unknown = sorted(set(step.parameter_map) - declared)
                if unknown:
                    raise ValueError(
                        f"capability {self.capability_id!r} maps undeclared parameters "
                        f"{unknown} onto engine method {step.method!r}"
                    )
        return self

    @property
    def is_executable(self) -> bool:
        """True when a plan exists; availability of the engine is checked separately."""
        return self.status == "bound" and self.engine_call is not None

    def parameter_defaults(self) -> dict[str, ParameterValue]:
        return {item.name: item.default for item in self.parameters if item.default is not None}

    def to_registry_entry(self) -> dict[str, object]:
        """Compact selection view for a planner. Not the full scientific record."""
        return {
            "capability_id": self.capability_id,
            "domain": self.domain,
            "goal": self.analytical_goal,
            "required_data": [item.requirement_id for item in self.required_data],
            "engine": self.engine,
            "status": self.status,
        }


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
    #: ``(xmin, xmax, ymin, ymax)`` in the case's own coordinates, not an OSM place.
    roi_bbox: tuple[float, float, float, float] | None = None
    roi_fraction: float | None = Field(default=None, gt=0.0, le=1.0)
    time_window: tuple[int, int] | None = None
    dt_minutes: float = Field(default=15.0, gt=0.0)
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)
    selection_reason: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def _check_dataset_selection(self) -> ExecutionRequest:
        if self.roi_bbox is not None and self.roi_fraction is not None:
            raise ValueError("give either roi_bbox or roi_fraction, not both")
        if self.time_window is not None and self.time_window[0] >= self.time_window[1]:
            raise ValueError("time_window must be an increasing (start, end) pair")
        return self


class EngineInvocation(BaseModel):
    """One replayed engine call, recorded for provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str
    arguments: dict[str, ParameterValue] = Field(default_factory=dict)


GeometryKind = Literal["Point", "LineString", "Polygon"]
GeometryStatus = Literal["ready", "partial", "missing", "non_geographic"]
NetworkCrs = Literal["EPSG:4326", "local", "unknown"]
ElementKind = Literal["bus", "line", "transformer", "load", "extent"]
LayerType = Literal[
    "network_hotspot",
    "network_nodes",
    "network_edges",
    "analysis_extent",
]
VisualizationType = Literal[
    "point_choropleth",
    "point_class",
    "line_network",
    "extent_polygon",
    "network",
]
ClassificationKind = Literal["tertile", "threshold", "categorical", "binary", "none"]


class GeoJsonGeometry(BaseModel):
    """RFC 7946 geometry. Coordinates are WGS84 ``[lon, lat]`` when emitted for Ariadne."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: GeometryKind
    coordinates: list[object]


class GeoJsonFeature(BaseModel):
    """One map feature. Properties include Ariadne target fields plus analysis attributes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["Feature"] = "Feature"
    geometry: GeoJsonGeometry
    properties: dict[str, object] = Field(default_factory=dict)
    id: str | int | None = None


class GeoJsonFeatureCollectionModel(BaseModel):
    """Standard FeatureCollection. This is what Ariadne puts in ``response.geojson``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: tuple[GeoJsonFeature, ...] = ()


class NetworkNode(BaseModel):
    """One electrical bus after coordinate mapping. Geometry may be absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bus_id: int
    x: float | None = None
    y: float | None = None
    has_geometry: bool = False
    name: str | None = None


class NetworkEdge(BaseModel):
    """One electrical connection. Drawn only when both endpoints have coordinates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    edge_id: str
    kind: Literal["line", "transformer"]
    from_bus: int
    to_bus: int
    has_geometry: bool = False
    name: str | None = None


class SpatialNetwork(BaseModel):
    """Geometry abstraction: electrical model → coordinate-mapped spatial network."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[NetworkNode, ...] = ()
    edges: tuple[NetworkEdge, ...] = ()
    crs: NetworkCrs = "unknown"
    source: str = "unknown"
    missing_node_count: int = 0
    missing_edge_count: int = 0


class AnalysisAttribute(BaseModel):
    """One per-feature analysis property attached to a spatial object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    value: float | int | str | bool | None = None
    unit: str | None = None


class ClassificationBreak(BaseModel):
    """Visualization class. Not a GeoLoadST scientific threshold unless noted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    color: str
    minimum: float | None = None
    maximum: float | None = None
    category: str | int | None = None


class VisualizationMetadata(BaseModel):
    """Styling hints for a host map. This plugin does not render them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer_name: str
    indicator: str
    unit: str
    classification: ClassificationKind
    visualization_type: VisualizationType
    styling_hints: dict[str, object] = Field(default_factory=dict)
    breaks: tuple[ClassificationBreak, ...] = ()
    crs: str = "EPSG:4326"
    limitations: tuple[str, ...] = ()


class SpatialLayer(BaseModel):
    """One geometry role inside the combined FeatureCollection Ariadne already consumes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer_id: str
    layer_type: LayerType
    geometry_kind: GeometryKind
    feature_count: int


class SpatialAnalysisResult(BaseModel):
    """Map-ready spatial result. ``geojson`` is the Ariadne viewer payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer_type: LayerType
    indicator: str
    geojson: dict[str, object]
    layers: tuple[SpatialLayer, ...] = ()
    visualization: VisualizationMetadata
    feature_count: int = 0
    geometry_status: GeometryStatus
    warnings: tuple[str, ...] = ()


class ExecutionResult(BaseModel):
    """Normalized plugin result. Numeric payloads come from GeoLoadST only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ExecutionStatus
    capability_id: CapabilityId
    detail: str
    outputs: dict[str, object] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    provenance: dict[str, object]
    spatial: SpatialAnalysisResult | None = None
