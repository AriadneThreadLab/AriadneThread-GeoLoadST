"""GeoLoadST must be optional; importing the plugin must not require it."""

from __future__ import annotations

import importlib
import sys

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


def test_importing_the_package_never_imports_the_engine() -> None:
    """A host that only lists capabilities must not pay for the scientific stack."""
    for name in [key for key in sys.modules if key.startswith("ariadne_geoloadst")]:
        del sys.modules[name]
    importlib.import_module("ariadne_geoloadst")
    assert not any(name == "geoloadst" or name.startswith("geoloadst.") for name in sys.modules)


def test_catalog_is_readable_without_the_engine() -> None:
    plugin = GeoLoadSTPlugin()
    assert len(plugin.registry.list_ids()) > 1
    assert plugin.registry.catalog_version == "geoloadst-capabilities-1"


def test_availability_report_is_serializable_for_a_host_trace() -> None:
    report = GeoLoadSTPlugin().is_available()
    payload = report.model_dump()
    assert payload["supported_version_range"] == ">=0.1.0,<0.2.0"
    assert isinstance(payload["detail"], str)
