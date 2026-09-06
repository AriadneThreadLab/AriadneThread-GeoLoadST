"""Convert GeoLoadST outputs + a spatial network into Ariadne-ready GeoJSON.

This module performs **no** science and **no** frontend rendering. It joins
engine values onto geometries GeoLoadST already prepared, then emits a
standard GeoJSON FeatureCollection that Ariadne Thread can put in
``AgentQueryResponse.geojson``.

Ariadne's viewer splits one FeatureCollection into topology and a dedicated
LISA cluster source. This plugin therefore:

- emits one FeatureCollection (not a second map protocol)
- never copies electrical LineStrings into a LISA result
- sets ``cluster_type`` / ``indicator`` / ``value`` / ``p_value`` on LISA points
- still sets Ariadne target properties for non-LISA layers

Pipeline::

    GeoLoadST result  →  SpatialNetwork  →  FeatureCollection  →  Ariadne map
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ariadne_geoloadst.schemas import (
    CapabilitySpec,
    ClassificationBreak,
    ClassificationKind,
    ExecutionRequest,
    ExecutionResult,
    GeoJsonFeature,
    GeoJsonFeatureCollectionModel,
    GeoJsonGeometry,
    GeometryKind,
    GeometryStatus,
    LayerType,
    NetworkNode,
    SpatialAnalysisResult,
    SpatialLayer,
    SpatialNetwork,
    VisualizationMetadata,
    VisualizationType,
)

#: Visualization-only colours. Not a GeoLoadST scientific scale.
COLOR_LOW = "#22c55e"
COLOR_MEDIUM = "#eab308"
COLOR_HIGH = "#dc2626"
COLOR_EDGE = "#64748b"
COLOR_EXTENT = "#818cf8"
COLOR_MISSING = "#94a3b8"

#: LISA codes from ``geoloadst.core.moran`` (0=NS, 1=HH, 2=LL, 3=LH, 4=HL).
LISA_CLUSTER_TYPES = {
    1: "HIGH_HIGH",
    2: "LOW_LOW",
    3: "LOW_HIGH",
    4: "HIGH_LOW",
}
LISA_CLUSTER_COLORS = {
    "HIGH_HIGH": "#dc2626",
    "LOW_LOW": "#2563eb",
    "HIGH_LOW": "#ea580c",
    "LOW_HIGH": "#7c3aed",
}
LISA_LAYER_NAME = "GeoLoadST LISA Clusters"
TOPOLOGY_LAYER_NAME = "GeoLoadST Topology Centrality"
TOPOLOGY_CAPABILITY_ID = "topology_centrality"
TOPOLOGY_METRIC_KEYS = (
    ("degree_centrality", ("metrics.degree", "degree")),
    ("betweenness_centrality", ("metrics.betweenness", "betweenness")),
    ("closeness_centrality", ("metrics.closeness", "closeness")),
)
#: Prefer betweenness for paint when GeoLoadST produced that vector.
TOPOLOGY_VIZ_PREFERENCE = (
    "betweenness_centrality",
    "degree_centrality",
    "closeness_centrality",
)
LISA_COLORS = {
    0: "#94a3b8",
    1: LISA_CLUSTER_COLORS["HIGH_HIGH"],
    2: LISA_CLUSTER_COLORS["LOW_LOW"],
    3: LISA_CLUSTER_COLORS["LOW_HIGH"],
    4: LISA_CLUSTER_COLORS["HIGH_LOW"],
}
LISA_LABELS = {
    0: "Not Significant",
    1: "High-High",
    2: "Low-Low",
    3: "Low-High",
    4: "High-Low",
}

MAX_MAP_FEATURES = 2048
DEFAULT_TARGET_ID = "t1"
DEFAULT_TARGET_INDEX = 0


@dataclass(frozen=True)
class VisualizationBinding:
    """How a catalogued capability is drawn. No extra calculation."""

    layer_type: LayerType
    visualization_type: VisualizationType
    value_key: str | None = None
    bus_id_key: str = "bus_ids_used"
    classification: ClassificationKind = "none"
    include_edges: bool = True
    include_extent: bool = True
    lisa_clusters: bool = False


#: Only capabilities whose engine outputs have a spatial join path.
BINDINGS: dict[str, VisualizationBinding] = {
    "load_instability_rms": VisualizationBinding(
        "network_hotspot", "point_choropleth", "instability_index", classification="threshold"
    ),
    "critical_node_classification": VisualizationBinding(
        "network_hotspot", "point_choropleth", "critical_mask", classification="binary"
    ),
    "lisa_instability": VisualizationBinding(
        "network_hotspot",
        "point_class",
        "clusters_instability",
        classification="categorical",
        include_edges=False,
        include_extent=False,
        lisa_clusters=True,
    ),
    "moran_lisa": VisualizationBinding(
        "network_hotspot",
        "point_class",
        "clusters_instability",
        classification="categorical",
        include_edges=False,
        include_extent=False,
        lisa_clusters=True,
    ),
    "global_moran_instability": VisualizationBinding(
        "network_nodes", "network", include_edges=True
    ),
    "spatial_clustering_of_instability": VisualizationBinding(
        "network_hotspot", "point_class", "clusters_instability", classification="categorical"
    ),
    "topology_centrality": VisualizationBinding(
        "network_hotspot",
        "point_choropleth",
        "metrics.degree",
        classification="tertile",
        include_edges=False,
        include_extent=False,
    ),
    "instability_topology_correlation": VisualizationBinding(
        "network_nodes", "line_network", include_edges=True
    ),
    "space_time_variogram": VisualizationBinding("network_nodes", "network"),
    "directional_variogram": VisualizationBinding("network_nodes", "network"),
    "local_anisotropy": VisualizationBinding(
        "network_nodes", "point_choropleth", "local_iso", classification="tertile"
    ),
    "multidim_pca_clustering": VisualizationBinding(
        "network_nodes",
        "point_class",
        "pca_results_cluster_labels",
        classification="categorical",
    ),
    "industrial_daynight_scenario": VisualizationBinding("network_nodes", "network"),
}


def binding_for(capability_id: str) -> VisualizationBinding:
    return BINDINGS.get(
        capability_id,
        VisualizationBinding("network_nodes", "network"),
    )


def build_spatial_result(
    *,
    spec: CapabilitySpec,
    outputs: dict[str, object],
    network: SpatialNetwork | None,
    request: ExecutionRequest | None = None,
) -> SpatialAnalysisResult:
    """Join engine outputs onto mapped geometry. Values are never invented."""
    binding = binding_for(spec.capability_id)
    warnings: list[str] = []
    spatial = network if network is not None else SpatialNetwork(source="missing")

    if spatial.crs == "local":
        warnings.append(
            "Network coordinates are not WGS84 lon/lat. Ariadne's map viewer requires "
            "EPSG:4326; features were omitted rather than reprojected."
        )
    if spatial.missing_node_count:
        warnings.append(
            f"{spatial.missing_node_count} buses have no usable coordinates and were omitted."
        )
    if spatial.missing_edge_count:
        warnings.append(
            f"{spatial.missing_edge_count} edges have an endpoint without coordinates "
            "and were omitted."
        )

    values_by_bus = _join_values(outputs, spatial, binding, warnings)
    threshold = _as_optional_float(outputs.get("threshold"))
    labels_map = _label_map(outputs)
    breaks = _classification_breaks(binding, list(values_by_bus.values()), threshold, labels_map)

    features: list[GeoJsonFeature] = []
    if spatial.crs == "EPSG:4326" and binding.lisa_clusters:
        features.extend(_lisa_cluster_features(spec, spatial.nodes, values_by_bus, outputs))
        if not features:
            warnings.append(
                "GeoLoadST produced no significant LISA cluster geometries. "
                "The electrical topology was not reused as a substitute layer."
            )
    elif spatial.crs == "EPSG:4326" and spec.capability_id == TOPOLOGY_CAPABILITY_ID:
        features.extend(_topology_centrality_features(spec, spatial.nodes, outputs))
        if not features:
            warnings.append(
                "GeoLoadST produced no topology-centrality geometries. "
                "The electrical topology was not reused as a substitute layer."
            )
    elif spatial.crs == "EPSG:4326":
        features.extend(
            _node_features(
                spec, binding, spatial.nodes, values_by_bus, threshold, labels_map, breaks
            )
        )
        if binding.include_edges:
            features.extend(_edge_features(spec, spatial))
        if binding.include_extent and request is not None:
            extent = _extent_feature(spec, request)
            if extent is not None:
                features.append(extent)

    if len(features) > MAX_MAP_FEATURES:
        warnings.append(f"map features truncated to {MAX_MAP_FEATURES} of {len(features)}")
        features = features[:MAX_MAP_FEATURES]

    collection = GeoJsonFeatureCollectionModel(features=tuple(features))
    geojson = collection.model_dump(exclude_none=True)
    dumped_features = geojson.get("features")
    if isinstance(dumped_features, tuple):
        geojson["features"] = list(dumped_features)
    layers = _summarize_layers(spec, features, binding)
    status = _geometry_status(spatial, features)
    if status == "missing" and spatial.crs != "EPSG:4326":
        warnings.append(
            "No map geometry could be produced. The electrical model has no WGS84 coordinates."
        )

    visualization = VisualizationMetadata(
        layer_name=_layer_name_for(spec, binding),
        indicator=spec.analytical_goal,
        unit=spec.units,
        classification=binding.classification,
        visualization_type=binding.visualization_type,
        styling_hints=_styling_hints(binding),
        breaks=tuple(breaks),
        crs="EPSG:4326" if spatial.crs == "EPSG:4326" else spatial.crs,
        limitations=(
            *spec.limitations,
            "Styling classes are visualization metadata, not a new GeoLoadST metric.",
            "Ariadne's current map colours features by target_id; severity colours are hints.",
        ),
    )
    return SpatialAnalysisResult(
        layer_type=binding.layer_type,
        indicator=spec.analytical_goal,
        geojson=geojson,
        layers=layers,
        visualization=visualization,
        feature_count=len(features),
        geometry_status=status,
        warnings=tuple(warnings),
    )


def to_ariadne_map_payload(result: ExecutionResult) -> dict[str, object] | None:
    """Host-facing slice for ``AgentQueryResponse.geojson``.

    The host still decides ``live_data_available``. Today's UI gates the map on
    that OSM-era flag; energy results should set it (or the host should relax
    the gate) when attaching this payload.
    """
    spatial = result.spatial
    if spatial is None or spatial.feature_count == 0:
        return None
    return {
        "geojson": spatial.geojson,
        "feature_count": spatial.feature_count,
        "attribution": (
            "Energy-grid analysis via GeoLoadST and SimBench. "
            "Not OpenStreetMap; OSM Overpass was not used."
        ),
        "layer_type": spatial.layer_type,
        "indicator": spatial.indicator,
        "visualization": spatial.visualization.model_dump(),
    }


def export_geojson(result: SpatialAnalysisResult | ExecutionResult, path: Path) -> Path:
    """Write the FeatureCollection as GeoJSON for download or inspection."""
    spatial = result.spatial if isinstance(result, ExecutionResult) else result
    if spatial is None:
        raise ValueError("no spatial result to export")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spatial.geojson, indent=2, sort_keys=False), encoding="utf-8")
    return path


def _join_values(
    outputs: dict[str, object],
    network: SpatialNetwork,
    binding: VisualizationBinding,
    warnings: list[str],
) -> dict[int, float | int | None]:
    if binding.value_key is None:
        return {}
    raw = _lookup_output(outputs, binding.value_key)
    values = _unwrap_sequence(raw)
    if values is None:
        warnings.append(f"engine output {binding.value_key!r} is not a per-node sequence")
        return {}
    bus_ids = _unwrap_ids(_lookup_output(outputs, binding.bus_id_key))
    joined: dict[int, float | int | None] = {}
    if bus_ids is not None and len(bus_ids) == len(values):
        for bus_id, value in zip(bus_ids, values, strict=False):
            joined[bus_id] = value
        return joined
    if len(values) == len(network.nodes):
        for node, value in zip(network.nodes, values, strict=False):
            joined[node.bus_id] = value
        return joined
    warnings.append(
        f"could not align {binding.value_key!r} ({len(values)} values) with "
        f"{len(bus_ids or [])} bus ids or {len(network.nodes)} network nodes"
    )
    return {}


def _layer_name_for(spec: CapabilitySpec, binding: VisualizationBinding) -> str:
    if spec.capability_id == TOPOLOGY_CAPABILITY_ID:
        return TOPOLOGY_LAYER_NAME
    if binding.lisa_clusters:
        return LISA_LAYER_NAME
    return spec.name


def _topology_centrality_features(
    spec: CapabilitySpec,
    nodes: tuple[NetworkNode, ...],
    outputs: dict[str, object],
) -> list[GeoJsonFeature]:
    """Point overlay of copied centrality values. Not the electrical LineString graph."""
    series = _topology_metric_series(outputs, nodes)
    if not series:
        return []
    viz_metric = _topology_visualization_metric(series)
    features: list[GeoJsonFeature] = []
    for node in nodes:
        if not node.has_geometry or node.x is None or node.y is None:
            continue
        metrics = {
            key: values[node.bus_id] for key, values in series.items() if node.bus_id in values
        }
        if not metrics:
            continue
        name = node.name or f"Bus {node.bus_id}"
        viz_value = metrics.get(viz_metric) if viz_metric else None
        extra: dict[str, object] = {
            "bus_id": node.bus_id,
            "analysis": TOPOLOGY_CAPABILITY_ID,
            "layer_name": TOPOLOGY_LAYER_NAME,
            "layer_type": "network_hotspot",
            "indicator": spec.analytical_goal,
            "unit": spec.units,
            "tags": {"name": name, "kind": "topology_bus"},
            **metrics,
        }
        if viz_metric is not None:
            extra["visualization_metric"] = viz_metric
        if viz_value is not None:
            extra["value"] = viz_value
        properties = _ariadne_properties(
            spec,
            name=name,
            element_kind="bus",
            layer_type="network_hotspot",
            extra=extra,
        )
        properties["target_label"] = TOPOLOGY_LAYER_NAME
        properties["analysis_target"] = TOPOLOGY_LAYER_NAME
        properties["analysis_target_label"] = TOPOLOGY_LAYER_NAME
        nested = properties.get("ariadne")
        if isinstance(nested, dict):
            updated = dict(nested)
            updated["analysis_target"] = TOPOLOGY_LAYER_NAME
            updated["analysis_targets"] = [TOPOLOGY_LAYER_NAME]
            properties["ariadne"] = updated
        features.append(
            GeoJsonFeature(
                id=f"topology:{node.bus_id}",
                geometry=GeoJsonGeometry(type="Point", coordinates=[node.x, node.y]),
                properties=properties,
            )
        )
    return features


def _topology_metric_series(
    outputs: dict[str, object],
    nodes: tuple[NetworkNode, ...],
) -> dict[str, dict[int, float]]:
    """Align each GeoLoadST centrality vector onto bus ids. Skip missing metrics."""
    bus_ids = _unwrap_ids(_lookup_output(outputs, "metrics.bus_ids"))
    if bus_ids is None:
        bus_ids = _unwrap_ids(_lookup_output(outputs, "bus_ids_used"))
    aligned: dict[str, dict[int, float]] = {}
    for dest_key, aliases in TOPOLOGY_METRIC_KEYS:
        values = None
        for alias in aliases:
            values = _unwrap_sequence(_lookup_output(outputs, alias))
            if values is not None:
                break
        if values is None:
            continue
        mapped = _align_numeric_series(values, bus_ids, nodes)
        if mapped:
            aligned[dest_key] = mapped
    return aligned


def _align_numeric_series(
    values: list[float | int | None],
    bus_ids: list[int] | None,
    nodes: tuple[NetworkNode, ...],
) -> dict[int, float]:
    keys: list[int] | None
    if bus_ids is not None and len(bus_ids) == len(values):
        keys = bus_ids
    elif len(values) == len(nodes):
        keys = [node.bus_id for node in nodes]
    else:
        return {}
    out: dict[int, float] = {}
    for bus_id, raw in zip(keys, values, strict=False):
        number = _as_optional_float(raw)
        if number is None:
            continue
        out[bus_id] = number
    return out


def _topology_visualization_metric(series: dict[str, dict[int, float]]) -> str | None:
    for key in TOPOLOGY_VIZ_PREFERENCE:
        if series.get(key):
            return key
    return None


def _lisa_cluster_features(
    spec: CapabilitySpec,
    nodes: tuple[NetworkNode, ...],
    codes_by_bus: dict[int, float | int | None],
    outputs: dict[str, object],
) -> list[GeoJsonFeature]:
    """Point layer of significant LISA classes. Not the electrical topology."""
    local_i, local_p = _lisa_local_series(outputs, codes_by_bus, nodes)
    features: list[GeoJsonFeature] = []
    for node in nodes:
        if not node.has_geometry or node.x is None or node.y is None:
            continue
        raw_code = codes_by_bus.get(node.bus_id)
        if not isinstance(raw_code, int | float) or isinstance(raw_code, bool):
            continue
        cluster_type = LISA_CLUSTER_TYPES.get(int(raw_code))
        if cluster_type is None:
            continue
        value = local_i.get(node.bus_id)
        p_value = local_p.get(node.bus_id)
        if value is None or p_value is None:
            continue
        name = node.name or f"Bus {node.bus_id}"
        color = LISA_CLUSTER_COLORS[cluster_type]
        properties = _ariadne_properties(
            spec,
            name=name,
            element_kind="bus",
            layer_type="lisa_clusters",
            extra={
                "bus_id": node.bus_id,
                "cluster_type": cluster_type,
                "indicator": "LISA",
                "value": value,
                "p_value": p_value,
                "color": color,
                "layer_name": LISA_LAYER_NAME,
                "severity": LISA_LABELS.get(int(raw_code)),
                "unit": spec.units,
                "tags": {"name": name, "kind": "lisa_cluster"},
            },
        )
        features.append(
            GeoJsonFeature(
                id=f"lisa:{node.bus_id}",
                geometry=GeoJsonGeometry(type="Point", coordinates=[node.x, node.y]),
                properties=properties,
            )
        )
    return features


def _lisa_local_series(
    outputs: dict[str, object],
    codes_by_bus: dict[int, float | int | None],
    nodes: tuple[NetworkNode, ...],
) -> tuple[dict[int, float], dict[int, float]]:
    """Align Local Moran ``Is`` / ``p_sim`` onto bus ids. Never invent numbers."""
    local = outputs.get("lisa_instability")
    if not isinstance(local, dict):
        return {}, {}
    is_vals = _unwrap_sequence(local.get("Is"))
    p_vals = _unwrap_sequence(local.get("p_sim"))
    if is_vals is None or p_vals is None:
        return {}, {}
    bus_ids = _unwrap_ids(_lookup_output(outputs, "bus_ids_used"))
    node_ids = [node.bus_id for node in nodes]
    keys: list[int]
    if bus_ids is not None and len(bus_ids) == len(is_vals) == len(p_vals):
        keys = bus_ids
    elif len(node_ids) == len(is_vals) == len(p_vals):
        keys = node_ids
    elif len(codes_by_bus) == len(is_vals) == len(p_vals):
        keys = list(codes_by_bus)
    else:
        return {}, {}
    local_i: dict[int, float] = {}
    local_p: dict[int, float] = {}
    for bus_id, raw_i, raw_p in zip(keys, is_vals, p_vals, strict=False):
        number_i = _as_optional_float(raw_i)
        number_p = _as_optional_float(raw_p)
        if number_i is None or number_p is None:
            continue
        local_i[bus_id] = number_i
        local_p[bus_id] = number_p
    return local_i, local_p


def _node_features(
    spec: CapabilitySpec,
    binding: VisualizationBinding,
    nodes: tuple[NetworkNode, ...],
    values_by_bus: dict[int, float | int | None],
    threshold: float | None,
    labels_map: dict[int, str],
    breaks: list[ClassificationBreak],
) -> list[GeoJsonFeature]:
    features: list[GeoJsonFeature] = []
    for node in nodes:
        if not node.has_geometry or node.x is None or node.y is None:
            continue
        value = values_by_bus.get(node.bus_id)
        severity, color, class_label = _classify(binding, value, threshold, labels_map, breaks)
        name = node.name or f"Bus {node.bus_id}"
        properties = _ariadne_properties(
            spec,
            name=name,
            element_kind="bus",
            layer_type=binding.layer_type,
            extra={
                "bus_id": node.bus_id,
                "value": value,
                "severity": severity,
                "color": color,
                "class_label": class_label,
                "unit": spec.units,
                "indicator": spec.analytical_goal,
                "tags": {"name": name, "kind": "grid_bus"},
            },
        )
        features.append(
            GeoJsonFeature(
                id=f"bus:{node.bus_id}",
                geometry=GeoJsonGeometry(type="Point", coordinates=[node.x, node.y]),
                properties=properties,
            )
        )
    return features


def _edge_features(spec: CapabilitySpec, network: SpatialNetwork) -> list[GeoJsonFeature]:
    by_id = {node.bus_id: node for node in network.nodes}
    features: list[GeoJsonFeature] = []
    for edge in network.edges:
        if not edge.has_geometry:
            continue
        start = by_id.get(edge.from_bus)
        end = by_id.get(edge.to_bus)
        if (
            start is None
            or end is None
            or start.x is None
            or start.y is None
            or end.x is None
            or end.y is None
        ):
            continue
        name = edge.name or f"{edge.kind} {edge.from_bus}-{edge.to_bus}"
        properties = _ariadne_properties(
            spec,
            name=name,
            element_kind=edge.kind,
            layer_type="network_edges",
            extra={
                "from_bus": edge.from_bus,
                "to_bus": edge.to_bus,
                "color": COLOR_EDGE,
                "severity": None,
                "tags": {"name": name, "kind": f"grid_{edge.kind}"},
            },
        )
        features.append(
            GeoJsonFeature(
                id=edge.edge_id,
                geometry=GeoJsonGeometry(
                    type="LineString",
                    coordinates=[[start.x, start.y], [end.x, end.y]],
                ),
                properties=properties,
            )
        )
    return features


def _extent_feature(spec: CapabilitySpec, request: ExecutionRequest) -> GeoJsonFeature | None:
    bbox = request.roi_bbox
    if bbox is None:
        return None
    xmin, xmax, ymin, ymax = bbox
    if not all(map(_finite, (xmin, xmax, ymin, ymax))):
        return None
    if abs(xmin) > 180 or abs(xmax) > 180 or abs(ymin) > 90 or abs(ymax) > 90:
        return None
    ring = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]
    properties = _ariadne_properties(
        spec,
        name="Analysis extent",
        element_kind="extent",
        layer_type="analysis_extent",
        extra={
            "color": COLOR_EXTENT,
            "tags": {"name": "Analysis extent", "kind": "analysis_extent"},
        },
    )
    return GeoJsonFeature(
        id="extent:roi",
        geometry=GeoJsonGeometry(type="Polygon", coordinates=[ring]),
        properties=properties,
    )


def _ariadne_properties(
    spec: CapabilitySpec,
    *,
    name: str,
    element_kind: str,
    layer_type: str,
    extra: dict[str, object],
) -> dict[str, object]:
    """Properties the current viewer already reads, plus analysis attributes."""
    label = spec.name
    return {
        "name": name,
        "element_kind": element_kind,
        "layer_type": layer_type,
        "capability_id": spec.capability_id,
        "target_id": DEFAULT_TARGET_ID,
        "target_index": DEFAULT_TARGET_INDEX,
        "target_label": label,
        "analysis_target": label,
        "analysis_target_label": label,
        "ariadne": {
            "analysis_target": label,
            "analysis_targets": [label],
            "target_id": DEFAULT_TARGET_ID,
            "target_index": DEFAULT_TARGET_INDEX,
            "capability_id": spec.capability_id,
            "domain": spec.domain,
        },
        **extra,
    }


def _classify(
    binding: VisualizationBinding,
    value: float | int | None,
    threshold: float | None,
    labels_map: dict[int, str],
    breaks: list[ClassificationBreak],
) -> tuple[str | None, str, str | None]:
    if value is None:
        return None, COLOR_MISSING, None
    kind = binding.classification
    if kind == "categorical":
        code = int(value) if isinstance(value, int | float) else None
        if code is None:
            return None, COLOR_MISSING, None
        color = LISA_COLORS.get(code, COLOR_MISSING)
        label = labels_map.get(code, str(code))
        return label, color, label
    if kind == "binary":
        high = bool(value) if isinstance(value, bool | int) else float(value) >= 0.5
        if high:
            return "high", COLOR_HIGH, "high"
        return "low", COLOR_LOW, "low"
    if kind == "threshold" and threshold is not None:
        if float(value) >= threshold:
            return "high", COLOR_HIGH, "high"
        return "low", COLOR_LOW, "low"
    if kind in {"tertile", "threshold"}:
        return _tertile(float(value), breaks)
    return None, COLOR_MISSING, None


def _tertile(value: float, breaks: list[ClassificationBreak]) -> tuple[str, str, str]:
    for item in breaks:
        low_ok = item.minimum is None or value >= item.minimum
        high_ok = item.maximum is None or value <= item.maximum
        if low_ok and high_ok:
            return item.label, item.color, item.label
    return "medium", COLOR_MEDIUM, "medium"


def _classification_breaks(
    binding: VisualizationBinding,
    values: list[float | int | None],
    threshold: float | None,
    labels_map: dict[int, str],
) -> list[ClassificationBreak]:
    kind = binding.classification
    if kind == "categorical":
        breaks: list[ClassificationBreak] = []
        codes = sorted({int(item) for item in values if isinstance(item, int | float)})
        for code in codes:
            breaks.append(
                ClassificationBreak(
                    label=labels_map.get(code, str(code)),
                    color=LISA_COLORS.get(code, COLOR_MISSING),
                    category=code,
                )
            )
        return breaks
    if kind == "binary":
        return [
            ClassificationBreak(label="low", color=COLOR_LOW, category="false"),
            ClassificationBreak(label="high", color=COLOR_HIGH, category="true"),
        ]
    if kind == "threshold" and threshold is not None:
        return [
            ClassificationBreak(label="low", color=COLOR_LOW, maximum=threshold),
            ClassificationBreak(label="high", color=COLOR_HIGH, minimum=threshold),
        ]
    finite = sorted(float(item) for item in values if isinstance(item, int | float))
    if len(finite) < 2:
        return [
            ClassificationBreak(label="low", color=COLOR_LOW),
            ClassificationBreak(label="medium", color=COLOR_MEDIUM),
            ClassificationBreak(label="high", color=COLOR_HIGH),
        ]
    q1 = _quantile(finite, 1.0 / 3.0)
    q2 = _quantile(finite, 2.0 / 3.0)
    return [
        ClassificationBreak(label="low", color=COLOR_LOW, minimum=finite[0], maximum=q1),
        ClassificationBreak(label="medium", color=COLOR_MEDIUM, minimum=q1, maximum=q2),
        ClassificationBreak(label="high", color=COLOR_HIGH, minimum=q2, maximum=finite[-1]),
    ]


def _quantile(sorted_vals: list[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    index = q * (len(sorted_vals) - 1)
    lo = int(index)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = index - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _styling_hints(binding: VisualizationBinding) -> dict[str, object]:
    if binding.classification == "categorical":
        return {
            "0": {"color": LISA_COLORS[0], "label": LISA_LABELS[0]},
            "1": {"color": LISA_COLORS[1], "label": LISA_LABELS[1]},
            "2": {"color": LISA_COLORS[2], "label": LISA_LABELS[2]},
            "3": {"color": LISA_COLORS[3], "label": LISA_LABELS[3]},
            "4": {"color": LISA_COLORS[4], "label": LISA_LABELS[4]},
        }
    return {
        "low": {"color": COLOR_LOW, "example": 0.1},
        "medium": {"color": COLOR_MEDIUM, "example": 0.5},
        "high": {"color": COLOR_HIGH, "example": 0.9},
        "note": "Examples illustrate a green→yellow→red hint scale; breaks follow engine values.",
    }


def _summarize_layers(
    spec: CapabilitySpec,
    features: list[GeoJsonFeature],
    binding: VisualizationBinding,
) -> tuple[SpatialLayer, ...]:
    counts: dict[tuple[LayerType, GeometryKind], int] = {}
    for feature in features:
        geometry_kind = feature.geometry.type
        raw_type = feature.properties.get("layer_type", binding.layer_type)
        layer_type = _as_layer_type(raw_type, binding.layer_type)
        key = (layer_type, geometry_kind)
        counts[key] = counts.get(key, 0) + 1
    layers: list[SpatialLayer] = []
    for (layer_type, geometry_kind), count in counts.items():
        layers.append(
            SpatialLayer(
                layer_id=f"{spec.capability_id}:{layer_type}",
                layer_type=layer_type,
                geometry_kind=geometry_kind,
                feature_count=count,
            )
        )
    return tuple(layers)


def _as_layer_type(raw: object, default: LayerType) -> LayerType:
    if raw == "network_hotspot":
        return "network_hotspot"
    if raw == "network_nodes":
        return "network_nodes"
    if raw == "network_edges":
        return "network_edges"
    if raw == "analysis_extent":
        return "analysis_extent"
    return default


def _geometry_status(network: SpatialNetwork, features: list[GeoJsonFeature]) -> GeometryStatus:
    if network.crs == "local":
        return "non_geographic"
    if not features:
        return "missing"
    if network.missing_node_count or network.missing_edge_count:
        return "partial"
    return "ready"


def _lookup_output(outputs: dict[str, object], key: str) -> object:
    if key in outputs:
        return outputs[key]
    current: object = outputs
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current


def _unwrap_sequence(value: object) -> list[float | int | None] | None:
    if value is None:
        return None
    if isinstance(value, dict) and value.get("kind") in {"array", "series"}:
        raw = value.get("values")
        if isinstance(raw, list):
            return [_as_number(item) for item in raw]
        return None
    if isinstance(value, list | tuple):
        return [_as_number(item) for item in value]
    return None


def _unwrap_ids(value: object) -> list[int] | None:
    sequence = _unwrap_sequence(value)
    if sequence is None:
        return None
    ids: list[int] = []
    for item in sequence:
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, float) and item.is_integer():
            ids.append(int(item))
    return ids if len(ids) == len(sequence) else None


def _label_map(outputs: dict[str, object]) -> dict[int, str]:
    raw = outputs.get("cluster_labels_map")
    if not isinstance(raw, dict):
        return dict(LISA_LABELS)
    out: dict[int, str] = {}
    for key, label in raw.items():
        try:
            out[int(key)] = str(label)
        except (TypeError, ValueError):
            continue
    return out or dict(LISA_LABELS)


def _as_number(value: object) -> float | int | None:
    if value is None or isinstance(value, bool):
        return int(value) if isinstance(value, bool) else None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if _finite(value) else None
    return None


def _as_optional_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if _finite(parsed) else None
    return None


def _finite(value: float) -> bool:
    return value == value and value not in {float("inf"), float("-inf")}
