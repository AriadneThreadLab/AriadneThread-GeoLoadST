"""Convert GeoLoadST scientific outputs into JSON-safe structures.

This module performs **no** science. It reshapes what the engine returned:
arrays, frames, ``esda`` Moran objects and opaque engine handles (NetworkX
graphs, ``libpysal`` weights, fitted scikit-learn models) become serialisable
records, and nothing is computed, rounded away or filled in.

``numpy`` and ``pandas`` are GeoLoadST dependencies, not plugin dependencies,
so values are recognised structurally instead of by ``isinstance``. The plugin
stays importable in an environment that has neither.
"""

from __future__ import annotations

import math
from typing import Any

#: Element budget per array. Larger arrays are truncated and flagged.
MAX_ARRAY_ITEMS = 4096
#: Row budget per table.
MAX_TABLE_ROWS = 512
_MAX_DEPTH = 8

#: Scalar diagnostics read off an ``esda`` Moran / Moran_Local result.
_MORAN_ATTRIBUTES = (
    "I",
    "EI",
    "VI_sim",
    "p_sim",
    "p_norm",
    "z_sim",
    "z_norm",
    "permutations",
)


class TruncationWarningCollector:
    """Collects human-readable notes about truncated payloads."""

    def __init__(self) -> None:
        self._messages: list[str] = []

    def add(self, message: str) -> None:
        if message not in self._messages:
            self._messages.append(message)

    @property
    def messages(self) -> tuple[str, ...]:
        return tuple(self._messages)


def normalize_result(
    value: Any,
    *,
    warnings: TruncationWarningCollector | None = None,
) -> object:
    """Normalize an engine return value into JSON-safe Python."""
    collector = warnings if warnings is not None else TruncationWarningCollector()
    return _normalize(value, collector, "result", 0)


def extract_result_keys(
    result: Any,
    keys: tuple[str, ...],
    *,
    warnings: TruncationWarningCollector | None = None,
) -> dict[str, object]:
    """Pull declared (optionally dotted) keys out of an engine result mapping.

    A key the engine did not produce is reported as missing rather than
    replaced by a substitute value.
    """
    collector = warnings if warnings is not None else TruncationWarningCollector()
    outputs: dict[str, object] = {}
    for key in keys:
        found, raw = _lookup(result, key)
        if not found:
            collector.add(f"engine result did not contain {key!r}")
            continue
        outputs[key.replace(".", "_")] = _normalize(raw, collector, key, 0)
    return outputs


def _lookup(result: Any, dotted_key: str) -> tuple[bool, Any]:
    current = result
    for part in dotted_key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if hasattr(current, "get") and not isinstance(current, dict):
            candidate = current.get(part)
            if candidate is not None:
                current = candidate
                continue
        return False, None
    return True, current


def _normalize(value: Any, warnings: TruncationWarningCollector, path: str, depth: int) -> object:
    if depth > _MAX_DEPTH:
        return _opaque(value, note="max depth reached")
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _finite(value)
    if isinstance(value, dict):
        return {
            str(key): _normalize(item, warnings, f"{path}.{key}", depth + 1)
            for key, item in value.items()
        }
    if _is_table(value):
        return _normalize_table(value, warnings, path)
    if _is_series(value):
        return _normalize_series(value, warnings, path)
    if _is_array(value):
        return _normalize_array(value, warnings, path)
    if isinstance(value, list | tuple | set | frozenset):
        items = list(value)
        truncated = len(items) > MAX_ARRAY_ITEMS
        if truncated:
            warnings.add(f"{path}: sequence truncated to {MAX_ARRAY_ITEMS} items")
            items = items[:MAX_ARRAY_ITEMS]
        return [_normalize(item, warnings, path, depth + 1) for item in items]
    if _is_moran_local(value):
        return _normalize_moran_local(value, warnings, path, depth)
    if _is_moran(value):
        return _normalize_moran(value)
    return _opaque(value)


def _finite(value: float) -> float | None:
    """NaN and infinity are not JSON values; report them as absent."""
    return value if math.isfinite(value) else None


def _is_array(value: Any) -> bool:
    return hasattr(value, "tolist") and hasattr(value, "shape") and hasattr(value, "dtype")


def _is_table(value: Any) -> bool:
    return hasattr(value, "columns") and hasattr(value, "index") and hasattr(value, "itertuples")


def _is_series(value: Any) -> bool:
    """A pandas Series has a labelled index; a numpy array does not."""
    return hasattr(value, "index") and hasattr(value, "tolist") and not hasattr(value, "columns")


def _is_moran(value: Any) -> bool:
    return hasattr(value, "I") and (hasattr(value, "p_sim") or hasattr(value, "EI"))


def _is_moran_local(value: Any) -> bool:
    """``esda.Moran_Local`` exposes per-node ``Is`` / ``q``, not global ``I``."""
    return hasattr(value, "Is") and hasattr(value, "q")


def _normalize_array(value: Any, warnings: TruncationWarningCollector, path: str) -> object:
    shape = tuple(int(dim) for dim in value.shape)
    if shape == ():
        return _scalar(value.tolist())
    items = value.tolist()
    flat = _flatten(items)
    truncated = len(flat) > MAX_ARRAY_ITEMS
    if truncated:
        warnings.add(f"{path}: array truncated to {MAX_ARRAY_ITEMS} of {len(flat)} values")
        flat = flat[:MAX_ARRAY_ITEMS]
    return {
        "kind": "array",
        "dtype": str(value.dtype),
        "shape": list(shape),
        "truncated": truncated,
        "values": [_scalar(item) for item in flat],
    }


def _normalize_series(value: Any, warnings: TruncationWarningCollector, path: str) -> object:
    values = list(value.tolist()) if hasattr(value, "tolist") else list(value)
    index = [_scalar(item) for item in list(value.index)]
    truncated = len(values) > MAX_ARRAY_ITEMS
    if truncated:
        warnings.add(f"{path}: series truncated to {MAX_ARRAY_ITEMS} of {len(values)} values")
        values = values[:MAX_ARRAY_ITEMS]
        index = index[:MAX_ARRAY_ITEMS]
    return {
        "kind": "series",
        "truncated": truncated,
        "index": index,
        "values": [_scalar(item) for item in values],
    }


def _normalize_table(value: Any, warnings: TruncationWarningCollector, path: str) -> object:
    columns = [str(column) for column in list(value.columns)]
    total_rows = len(value.index)
    truncated = total_rows > MAX_TABLE_ROWS
    frame = value.iloc[:MAX_TABLE_ROWS] if truncated else value
    if truncated:
        warnings.add(f"{path}: table truncated to {MAX_TABLE_ROWS} of {total_rows} rows")
    records = [
        {column: _scalar(cell) for column, cell in zip(columns, row, strict=False)}
        for row in frame.itertuples(index=False, name=None)
    ]
    return {
        "kind": "table",
        "columns": columns,
        "row_count": total_rows,
        "truncated": truncated,
        "records": records,
    }


def _normalize_moran_local(
    value: Any,
    warnings: TruncationWarningCollector,
    path: str,
    depth: int,
) -> object:
    """Copy Local Moran arrays. Does not classify clusters or invent values."""
    payload: dict[str, object] = {
        "kind": "local_spatial_statistic",
        "type": _qualified_type(value),
    }
    for name in ("Is", "p_sim", "q"):
        if hasattr(value, name):
            payload[name] = _normalize(getattr(value, name), warnings, f"{path}.{name}", depth + 1)
    return payload


def _normalize_moran(value: Any) -> object:
    statistics = {
        name: _scalar(getattr(value, name)) for name in _MORAN_ATTRIBUTES if hasattr(value, name)
    }
    return {
        "kind": "spatial_statistic",
        "type": _qualified_type(value),
        "statistics": statistics,
    }


def _scalar(value: Any) -> object:
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return _finite(value)
    if hasattr(value, "tolist") and hasattr(value, "shape") and getattr(value, "shape", None) == ():
        return _scalar(value.tolist())
    if hasattr(value, "item") and not isinstance(value, list | tuple | dict):
        try:
            return _scalar(value.item())
        except (ValueError, TypeError):
            pass
    if isinstance(value, list | tuple):
        return [_scalar(item) for item in value]
    return _opaque(value)


def _flatten(items: Any) -> list[Any]:
    if not isinstance(items, list):
        return [items]
    flat: list[Any] = []
    for item in items:
        flat.extend(_flatten(item))
    return flat


def _opaque(value: Any, *, note: str | None = None) -> dict[str, object]:
    """Engine handles are described, never serialised."""
    record: dict[str, object] = {
        "kind": "engine_object",
        "type": _qualified_type(value),
    }
    if note is not None:
        record["note"] = note
    return record


def _qualified_type(value: Any) -> str:
    cls = type(value)
    module = getattr(cls, "__module__", "builtins")
    return f"{module}.{cls.__qualname__}"
