"""The declared GeoLoadST dependency must be importable after ``pip install -e .``."""

from __future__ import annotations

from ariadne_geoloadst import get_capabilities, health_status


def test_geoloadst_import_discovers_moran_lisa() -> None:
    import geoloadst

    assert geoloadst.__name__ == "geoloadst"
    assert hasattr(geoloadst, "InstabilityAnalyzer")
    ids = [item["capability_id"] for item in get_capabilities()]
    assert "moran_lisa" in ids
    report = health_status()
    assert report["geoloadst_available"] is True
    assert isinstance(report["version"], str) and report["version"]
    assert "moran_lisa" in report["capabilities"]


def test_health_status_shape_lists_moran_lisa() -> None:
    report = health_status()
    assert set(report) >= {"geoloadst_available", "version", "capabilities"}
    assert isinstance(report["geoloadst_available"], bool)
    assert isinstance(report["capabilities"], list)
    assert "moran_lisa" in report["capabilities"]
    assert report["capabilities"][0] == "moran_lisa"
