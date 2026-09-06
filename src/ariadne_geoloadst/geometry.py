"""Electrical model → coordinate-mapped spatial network.

GeoLoadST and SimBench supply buses, lines, transformers and loads. They do
not always supply map coordinates. This module never invents geometry.

Required geometry inputs
------------------------
- Bus coordinates as ``(x, y)`` pairs, typically from ``bus_geodata`` /
  ``bus.geo`` via GeoLoadST ``extract_bus_coordinates``, or from
  ``InstabilityAnalyzer.bus_ids`` + ``coords`` after ``prepare_data``.
- Line / transformer incidence (``from_bus`` / ``to_bus``, ``hv_bus`` /
  ``lv_bus``) to build edges.

Missing geometry behaviour
--------------------------
- A bus without finite coordinates is kept as a node with ``has_geometry=False``.
- An edge whose endpoints lack coordinates is kept with ``has_geometry=False``.
- Those objects are omitted from GeoJSON. They are not given placeholder points.

Limitations
-----------
- Coordinates in ``[-180, 180] x [-90, 90]`` are treated as WGS84 lon/lat
  (SimBench / GeoLoadST examples such as ``1-complete_data-mixed-all-1-sw``).
- Projected or local coordinates are recorded as ``crs="local"`` and are **not**
  reprojected. Ariadne's viewer requires WGS84 ``[lon, lat]``.
- Loads are attributes of buses, not separate geometries.
- No impedance-weighted layout and no OSM join.
"""

from __future__ import annotations

import math
from typing import Any

from ariadne_geoloadst.schemas import NetworkCrs, NetworkEdge, NetworkNode, SpatialNetwork

_LON_LIMIT = 180.0
_LAT_LIMIT = 90.0


def extract_spatial_network(source: Any) -> SpatialNetwork:
    """Build a spatial network from an analyzer, electrical model, or mapping.

    Accepted sources (first match wins):

    * :class:`SpatialNetwork` — returned unchanged
    * object with ``bus_ids`` and ``coords`` (GeoLoadST analyzer after prepare)
    * object with ``net`` (analyzer wrapping a pandapower net)
    * pandapower-like net (``bus``, ``line``, optional ``bus_geodata`` / ``trafo``)
    * mapping with ``nodes`` / ``edges``
    """
    if isinstance(source, SpatialNetwork):
        return source
    if source is None:
        return SpatialNetwork(source="empty")

    analyzer_ids, analyzer_coords = _analyzer_coordinate_source(source)
    if analyzer_ids is not None and analyzer_coords is not None:
        nodes = _nodes_from_pairs(_sequence(analyzer_ids), analyzer_coords)
        net = getattr(source, "net", None)
        edges = _edges_from_net(net, {node.bus_id for node in nodes}) if net is not None else ()
        return _finalize(nodes, edges, source="analyzer")

    net = getattr(source, "net", None)
    if net is not None:
        return extract_spatial_network(net)

    if _looks_like_electrical_net(source):
        nodes = _nodes_from_electrical_net(source)
        edges = _edges_from_net(source, {node.bus_id for node in nodes})
        return _finalize(nodes, edges, source="electrical_model")

    if isinstance(source, dict):
        return _from_mapping(source)

    return SpatialNetwork(source="unrecognized")


def is_geographic(x: float, y: float) -> bool:
    """True when a pair can be published as WGS84 lon/lat without reprojection."""
    return math.isfinite(x) and math.isfinite(y) and abs(x) <= _LON_LIMIT and abs(y) <= _LAT_LIMIT


def _finalize(
    nodes: tuple[NetworkNode, ...],
    edges: tuple[NetworkEdge, ...],
    *,
    source: str,
) -> SpatialNetwork:
    located = [node for node in nodes if node.has_geometry]
    crs = _infer_crs(located)
    if crs != "EPSG:4326":
        nodes = tuple(
            node.model_copy(update={"has_geometry": False}) if node.has_geometry else node
            for node in nodes
        )
        edges = tuple(edge.model_copy(update={"has_geometry": False}) for edge in edges)
        located = []
    else:
        located_ids = {node.bus_id for node in located}
        edges = tuple(
            edge.model_copy(
                update={"has_geometry": edge.from_bus in located_ids and edge.to_bus in located_ids}
            )
            for edge in edges
        )
    return SpatialNetwork(
        nodes=nodes,
        edges=edges,
        crs=crs,
        source=source,
        missing_node_count=sum(1 for node in nodes if not node.has_geometry),
        missing_edge_count=sum(1 for edge in edges if not edge.has_geometry),
    )


def _infer_crs(nodes: list[NetworkNode]) -> NetworkCrs:
    if not nodes:
        return "unknown"
    geographic = all(
        node.x is not None and node.y is not None and is_geographic(node.x, node.y)
        for node in nodes
    )
    return "EPSG:4326" if geographic else "local"


def _analyzer_coordinate_source(source: Any) -> tuple[Any, Any] | tuple[None, None]:
    """Prefer the active Moran/LISA subset when GeoLoadST has subsampled buses."""
    active_ids = getattr(source, "bus_ids_active", None)
    active_coords = getattr(source, "coords_active", None)
    if active_ids is not None and active_coords is not None:
        return active_ids, active_coords
    bus_ids = getattr(source, "bus_ids", None)
    coords = getattr(source, "coords", None)
    if bus_ids is not None and coords is not None:
        return bus_ids, coords
    return None, None


def _looks_like_electrical_net(source: Any) -> bool:
    return hasattr(source, "line") or hasattr(source, "bus") or hasattr(source, "bus_geodata")


def _nodes_from_pairs(bus_ids: list[Any], coords: Any) -> tuple[NetworkNode, ...]:
    pairs = _coordinate_pairs(coords)
    nodes: list[NetworkNode] = []
    for index, raw_id in enumerate(bus_ids):
        bus_id = _as_int(raw_id)
        if bus_id is None:
            continue
        x, y, ok = _xy_at(pairs, index)
        nodes.append(
            NetworkNode(
                bus_id=bus_id,
                x=x,
                y=y,
                has_geometry=ok,
                name=f"Bus {bus_id}",
            )
        )
    return tuple(nodes)


def _nodes_from_electrical_net(net: Any) -> tuple[NetworkNode, ...]:
    coords_by_id = _coords_from_geodata(net)
    coords_by_id.update(_coords_from_bus_geo_column(net))
    bus_ids = _bus_ids_from_net(net, coords_by_id)
    nodes: list[NetworkNode] = []
    for bus_id in bus_ids:
        pair = coords_by_id.get(bus_id)
        x = pair[0] if pair is not None else None
        y = pair[1] if pair is not None else None
        ok = x is not None and y is not None and math.isfinite(x) and math.isfinite(y)
        nodes.append(
            NetworkNode(
                bus_id=bus_id,
                x=x if ok else None,
                y=y if ok else None,
                has_geometry=bool(ok),
                name=f"Bus {bus_id}",
            )
        )
    return tuple(nodes)


def _bus_ids_from_net(net: Any, coords_by_id: dict[int, tuple[float, float]]) -> list[int]:
    bus = getattr(net, "bus", None)
    ids: list[int] = []
    if bus is not None and hasattr(bus, "index"):
        for raw in list(bus.index):
            parsed = _as_int(raw)
            if parsed is not None:
                ids.append(parsed)
    if ids:
        return ids
    return sorted(coords_by_id)


def _coords_from_geodata(net: Any) -> dict[int, tuple[float, float]]:
    geodata = getattr(net, "bus_geodata", None)
    if geodata is None:
        return {}
    out: dict[int, tuple[float, float]] = {}
    for index, row in _iter_rows(geodata):
        bus_id = _as_int(index)
        x = _as_float(_row_get(row, "x"))
        y = _as_float(_row_get(row, "y"))
        if bus_id is None or x is None or y is None:
            continue
        out[bus_id] = (x, y)
    return out


def _coords_from_bus_geo_column(net: Any) -> dict[int, tuple[float, float]]:
    """Best-effort parse of ``net.bus['geo']`` GeoJSON-like strings or [x, y] lists."""
    bus = getattr(net, "bus", None)
    if bus is None or not hasattr(bus, "columns"):
        return {}
    columns = [str(column) for column in list(bus.columns)]
    if "geo" not in columns:
        return {}
    out: dict[int, tuple[float, float]] = {}
    for index, row in _iter_rows(bus):
        bus_id = _as_int(index)
        raw = _row_get(row, "geo")
        pair = _parse_geo_cell(raw)
        if bus_id is None or pair is None:
            continue
        out[bus_id] = pair
    return out


def _parse_geo_cell(raw: Any) -> tuple[float, float] | None:
    if raw is None:
        return None
    if isinstance(raw, list | tuple) and len(raw) >= 2:
        x, y = _as_float(raw[0]), _as_float(raw[1])
        if x is None or y is None:
            return None
        return (x, y)
    if not isinstance(raw, str) or "coordinates" not in raw:
        return None
    # Minimal parse: look for the first two numbers after "coordinates".
    # Full GeoJSON parsing lives in GeoLoadST; this only recovers obvious pairs.
    digits: list[float] = []
    current: list[str] = []
    for char in raw:
        if char.isdigit() or char in ".-":
            current.append(char)
            continue
        if current:
            parsed = _as_float("".join(current))
            if parsed is not None:
                digits.append(parsed)
            current = []
        if len(digits) >= 2:
            break
    if current and len(digits) < 2:
        parsed = _as_float("".join(current))
        if parsed is not None:
            digits.append(parsed)
    if len(digits) < 2:
        return None
    return (digits[0], digits[1])


def _edges_from_net(net: Any, known_buses: set[int]) -> tuple[NetworkEdge, ...]:
    edges: list[NetworkEdge] = []
    for index, row in _iter_rows(getattr(net, "line", None)):
        frm = _as_int(_row_get(row, "from_bus"))
        to = _as_int(_row_get(row, "to_bus"))
        if frm is None or to is None:
            continue
        if known_buses and (frm not in known_buses or to not in known_buses):
            continue
        edge_id = f"line:{index}"
        edges.append(
            NetworkEdge(
                edge_id=edge_id,
                kind="line",
                from_bus=frm,
                to_bus=to,
                has_geometry=False,
                name=f"Line {index}",
            )
        )
    for index, row in _iter_rows(getattr(net, "trafo", None)):
        frm = _as_int(_row_get(row, "hv_bus"))
        to = _as_int(_row_get(row, "lv_bus"))
        if frm is None or to is None:
            continue
        if known_buses and (frm not in known_buses or to not in known_buses):
            continue
        edges.append(
            NetworkEdge(
                edge_id=f"transformer:{index}",
                kind="transformer",
                from_bus=frm,
                to_bus=to,
                has_geometry=False,
                name=f"Transformer {index}",
            )
        )
    return tuple(edges)


def _from_mapping(payload: dict[str, Any]) -> SpatialNetwork:
    raw_nodes = payload.get("nodes")
    nodes: list[NetworkNode] = []
    if isinstance(raw_nodes, list | tuple):
        for item in raw_nodes:
            if isinstance(item, NetworkNode):
                nodes.append(item)
                continue
            if not isinstance(item, dict):
                continue
            bus_id = _as_int(item.get("bus_id"))
            if bus_id is None:
                continue
            x = _as_float(item.get("x", item.get("lon")))
            y = _as_float(item.get("y", item.get("lat")))
            ok = x is not None and y is not None and math.isfinite(x) and math.isfinite(y)
            nodes.append(
                NetworkNode(
                    bus_id=bus_id,
                    x=x if ok else None,
                    y=y if ok else None,
                    has_geometry=ok,
                    name=str(item["name"]) if item.get("name") is not None else f"Bus {bus_id}",
                )
            )
    raw_edges = payload.get("edges")
    edges: list[NetworkEdge] = []
    if isinstance(raw_edges, list | tuple):
        for item in raw_edges:
            if isinstance(item, NetworkEdge):
                edges.append(item)
                continue
            if not isinstance(item, dict):
                continue
            frm = _as_int(item.get("from_bus"))
            to = _as_int(item.get("to_bus"))
            if frm is None or to is None:
                continue
            kind = item.get("kind", "line")
            edge_kind = kind if kind in {"line", "transformer"} else "line"
            edges.append(
                NetworkEdge(
                    edge_id=str(item.get("edge_id") or f"{edge_kind}:{frm}-{to}"),
                    kind=edge_kind,  # type: ignore[arg-type]
                    from_bus=frm,
                    to_bus=to,
                    has_geometry=False,
                    name=str(item["name"]) if item.get("name") is not None else None,
                )
            )
    return _finalize(tuple(nodes), tuple(edges), source="mapping")


def _coordinate_pairs(coords: Any) -> list[tuple[float | None, float | None]]:
    raw = coords.tolist() if hasattr(coords, "tolist") else coords
    if raw is None:
        return []
    pairs: list[tuple[float | None, float | None]] = []
    if hasattr(raw, "__iter__") and not isinstance(raw, str | bytes):
        for item in raw:
            if isinstance(item, list | tuple) and len(item) >= 2:
                pairs.append((_as_float(item[0]), _as_float(item[1])))
            elif hasattr(item, "__iter__") and not isinstance(item, str | bytes):
                values = list(item)
                if len(values) >= 2:
                    pairs.append((_as_float(values[0]), _as_float(values[1])))
    return pairs


def _xy_at(
    pairs: list[tuple[float | None, float | None]], index: int
) -> tuple[float | None, float | None, bool]:
    if index >= len(pairs):
        return None, None, False
    x, y = pairs[index]
    ok = x is not None and y is not None and math.isfinite(x) and math.isfinite(y)
    return (x if ok else None), (y if ok else None), ok


def _sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        return list(value.tolist())
    if isinstance(value, list | tuple):
        return list(value)
    if hasattr(value, "__iter__") and not isinstance(value, str | bytes):
        return list(value)
    return []


def _iter_rows(table: Any) -> list[tuple[Any, Any]]:
    if table is None:
        return []
    if hasattr(table, "iterrows"):
        return list(table.iterrows())
    if isinstance(table, list | tuple):
        return list(enumerate(table))
    if hasattr(table, "index") and hasattr(table, "__getitem__"):
        rows: list[tuple[Any, Any]] = []
        for index in list(table.index):
            try:
                rows.append((index, table.loc[index] if hasattr(table, "loc") else table[index]))
            except Exception:
                continue
        return rows
    return []


def _row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "get"):
        try:
            return row.get(key)
        except Exception:
            pass
    try:
        return row[key]
    except Exception:
        return getattr(row, key, None)


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int):
        return float(value)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
