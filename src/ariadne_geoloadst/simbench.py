"""Thin SimBench data-provider boundary.

SimBench is a dataset, not an Overpass-style geographic query API.
This module does not reimplement GeoLoadST loaders; it delegates to
``geoloadst.io.load_simbench_network`` and adds only discovery and provenance.
"""

from __future__ import annotations

from typing import Any

from ariadne_geoloadst.compatibility import probe_geoloadst
from ariadne_geoloadst.engine import EngineExecutionError, EngineNotAvailableError


class SimBenchProvider:
    """Discovery and provenance wrapper. No city-name geocoding."""

    #: Codes that appear in GeoLoadST's own examples. Not a complete SimBench index.
    documented_example_codes: tuple[str, ...] = ("1-complete_data-mixed-all-1-sw",)

    def available_example_codes(self) -> tuple[str, ...]:
        return self.documented_example_codes

    def can_load(self) -> bool:
        return probe_geoloadst().status == "available"

    def load_network(self, code: str) -> Any:
        """Return a ``pandapowerNet`` built by GeoLoadST's own SimBench adapter.

        The network object is passed straight to the engine; this package never
        inspects or edits its electrical content.
        """
        try:
            from geoloadst.io import load_simbench_network
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise EngineNotAvailableError(
                "GeoLoadST is not installed, so SimBench cases cannot be loaded"
            ) from exc
        try:
            return load_simbench_network(code)
        except Exception as exc:
            raise EngineExecutionError(
                f"GeoLoadST could not load SimBench case {code!r}: {exc}"
            ) from exc

    def describe_limitation(self) -> str:
        return (
            "SimBench supplies a named network model and load profiles. "
            "It does not accept an arbitrary city query. ROI filtering uses "
            "the case's own coordinates via GeoLoadST, not OSM Overpass."
        )
