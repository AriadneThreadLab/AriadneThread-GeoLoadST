"""Thin SimBench data-provider boundary.

SimBench is a dataset, not an Overpass-style geographic query API.
This module does not reimplement GeoLoadST loaders. When scientific extras
are installed it will delegate to ``geoloadst.io.load_simbench_network``.
"""

from __future__ import annotations

from ariadne_geoloadst.compatibility import probe_geoloadst


class SimBenchProvider:
    """Discovery and provenance wrapper. No city-name geocoding."""

    #: Codes that appear in GeoLoadST's own examples. Not a complete SimBench index.
    documented_example_codes: tuple[str, ...] = ("1-complete_data-mixed-all-1-sw",)

    def available_example_codes(self) -> tuple[str, ...]:
        return self.documented_example_codes

    def can_load(self) -> bool:
        return probe_geoloadst().status == "available"

    def describe_limitation(self) -> str:
        return (
            "SimBench supplies a named network model and load profiles. "
            "It does not accept an arbitrary city query. ROI filtering uses "
            "the case's own coordinates via GeoLoadST, not OSM Overpass."
        )
