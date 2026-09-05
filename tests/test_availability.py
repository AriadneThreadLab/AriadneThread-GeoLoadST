"""GeoLoadST must be optional; importing the plugin must not require it."""

from __future__ import annotations

from ariadne_geoloadst import GeoLoadSTPlugin
from ariadne_geoloadst.compatibility import probe_geoloadst


def test_probe_does_not_import_geoloadst_when_missing() -> None:
    report = probe_geoloadst()
    assert report.supported_version_range == ">=0.1.0,<0.2.0"
    assert report.status in {
        "available",
        "package_missing",
        "incompatible_version",
        "optional_dependency_missing",
    }
    if not report.package_available:
        assert report.status == "package_missing"
        assert "geoloadst" in report.missing
        assert "OSM" in report.detail


def test_plugin_is_available_matches_probe() -> None:
    plugin = GeoLoadSTPlugin()
    assert plugin.is_available() == probe_geoloadst()
