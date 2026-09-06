#!/usr/bin/env python3
"""Load-instability → GeoJSON example for the Ariadne map viewer.

This script does not open a map. It shows the integration pipeline:

1. Select a registered capability
2. Run GeoLoadST when installed, otherwise a local stand-in
3. Normalize the result onto a spatial network
4. Export a FeatureCollection
5. Print the host payload Ariadne should put in ``response.geojson``

Run from the repository root::

    ./.venv/bin/python examples/load_instability_map_example.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ariadne_geoloadst import GeoLoadSTPlugin, export_geojson
from ariadne_geoloadst.engine import DatasetSpec, GeoLoadSTEngine
from ariadne_geoloadst.schemas import AvailabilityReport, ExecutionRequest

OUTPUT = Path("outputs/load_instability_map.geojson")
NETWORK_CODE = "1-complete_data-mixed-all-1-sw"


class _ExampleAnalyzer:
    """Tiny stand-in used only when GeoLoadST is not installed."""

    def __init__(self, dataset: DatasetSpec) -> None:
        self.dataset = dataset
        self.bus_ids = [1, 2, 3]
        self.coords = [[10.90, 53.30], [11.00, 53.35], [11.10, 53.40]]
        self.net = _ExampleNet()

    def prepare_data(self) -> _ExampleAnalyzer:
        return self

    def compute_spatiotemporal_instability(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "instability_index": _Array([0.12, 0.91, 0.48]),
            "bus_ids_used": _Array([1, 2, 3]),
            "threshold": 0.8,
        }


class _Array:
    def __init__(self, values: list[Any]) -> None:
        self._values = values
        self.dtype = "float64"
        self.shape = (len(values),)

    def tolist(self) -> list[Any]:
        return list(self._values)


class _ExampleNet:
    class _Lines:
        def iterrows(self) -> list[tuple[int, dict[str, int]]]:
            return [(0, {"from_bus": 1, "to_bus": 2}), (1, {"from_bus": 2, "to_bus": 3})]

    line = _Lines()
    trafo = _Lines()


class _AvailablePlugin(GeoLoadSTPlugin):
    def is_available(self) -> AvailabilityReport:
        return AvailabilityReport(
            status="available",
            package_available=True,
            compatible_version=True,
            installed_version="example-stand-in",
            supported_version_range=">=0.1.0,<0.2.0",
            detail="Offline example stand-in.",
        )


def _offline_plugin() -> GeoLoadSTPlugin:
    return _AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=_ExampleAnalyzer))


def main() -> None:
    live = GeoLoadSTPlugin()
    availability = live.is_available()
    if availability.status == "available":
        plugin: GeoLoadSTPlugin = live
        print(f"Using installed GeoLoadST {availability.installed_version}")
    else:
        plugin = _offline_plugin()
        print(f"GeoLoadST unavailable ({availability.status}); using offline stand-in.")

    request = ExecutionRequest(
        capability_id="load_instability_rms",
        dataset_id=f"simbench:{NETWORK_CODE}",
        simbench_network_code=NETWORK_CODE,
        roi_bbox=(10.8, 11.2, 53.2, 53.5),
        selection_reason="Example: show RMS load instability as a map layer.",
    )
    result = plugin.execute(request)
    print(f"status={result.status} capability={result.capability_id}")
    print(f"engine_calls={result.provenance.get('engine_calls')}")
    print(f"output={json.dumps(result.provenance.get('output'), indent=2)}")

    payload = plugin.to_map_payload(result)
    if payload is None:
        print("No map-ready geometry. Check coordinates / availability.")
        return

    path = export_geojson(result, OUTPUT)
    print(f"wrote {path} ({payload['feature_count']} features)")
    print("Ariadne host mapping:")
    print("  AgentQueryResponse.geojson        = payload['geojson']")
    print("  AgentQueryResponse.feature_count  = payload['feature_count']")
    print("  AgentQueryResponse.attribution    = payload['attribution']")
    print("The current viewer styles by target_id; severity/color are hints.")


if __name__ == "__main__":
    main()
