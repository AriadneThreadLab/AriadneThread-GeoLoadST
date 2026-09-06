"""Offline test doubles.

Nothing here talks to SimBench, GitHub or a running service. The fakes mimic
the *shapes* GeoLoadST returns (inspected at main 079dc2cb) so the adapter
contract can be tested without the scientific stack installed.
"""

from __future__ import annotations

from typing import Any

import pytest

from ariadne_geoloadst.adapter import GeoLoadSTPlugin
from ariadne_geoloadst.compatibility import SUPPORTED_GEOLOADST_RANGE
from ariadne_geoloadst.engine import DatasetSpec, GeoLoadSTEngine
from ariadne_geoloadst.schemas import AvailabilityReport


class FakeArray:
    """Minimal ndarray-like object: normalization must not require numpy."""

    def __init__(self, values: list[Any], dtype: str = "float64") -> None:
        self._values = values
        self.dtype = dtype
        self.shape = (len(values),)

    def tolist(self) -> list[Any]:
        return list(self._values)


class FakeMoran:
    """Stands in for an esda Moran result."""

    def __init__(self, i: float = 0.42, p_sim: float = 0.001) -> None:
        self.I = i
        self.EI = -0.01
        self.p_sim = p_sim
        self.z_sim = 3.2
        self.permutations = 999


class FakeMoranLocal:
    """Stands in for an esda Moran_Local result."""

    def __init__(self) -> None:
        self.Is = FakeArray([0.11, 0.82, -0.21])
        self.p_sim = FakeArray([0.20, 0.01, 0.03])
        self.q = FakeArray([1, 1, 3], dtype="int64")


class FakeLineTable:
    """Minimal pandapower-like table: supports ``iterrows``."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def iterrows(self) -> list[tuple[int, dict[str, Any]]]:
        return list(enumerate(self._rows))


class FakeElectricalModel:
    """Tiny WGS84 grid used so spatial export can be tested without SimBench."""

    def __init__(self) -> None:
        self.line = FakeLineTable(
            [
                {"from_bus": 1, "to_bus": 2, "length_km": 1.0},
                {"from_bus": 2, "to_bus": 3, "length_km": 1.2},
            ]
        )
        self.trafo = FakeLineTable([])
        self.load = FakeLineTable([{"bus": 1}, {"bus": 2}, {"bus": 3}])


class FakeAnalyzer:
    """Records the plan the adapter replayed and returns engine-shaped results."""

    def __init__(self, dataset: DatasetSpec) -> None:
        self.dataset = dataset
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.prepared = False
        self.bus_ids: list[int] | None = None
        self.coords: list[list[float]] | None = None
        self.net = FakeElectricalModel()

    def prepare_data(self) -> FakeAnalyzer:
        self.calls.append(("prepare_data", {}))
        self.prepared = True
        # Lon/lat near the GeoLoadST SimBench example ROI (northern Germany).
        self.bus_ids = [1, 2, 3]
        self.coords = [[10.90, 53.30], [11.00, 53.35], [11.10, 53.40]]
        return self

    def compute_spatiotemporal_instability(self, **kwargs: Any) -> dict[str, Any]:
        self._require_prepared("compute_spatiotemporal_instability")
        self.calls.append(("compute_spatiotemporal_instability", dict(kwargs)))
        return {
            "instability_index": FakeArray([0.4, 1.9, 0.7]),
            "bus_ids_used": FakeArray([1, 2, 3], dtype="int64"),
            "critical_mask": FakeArray([False, True, False], dtype="bool"),
            "critical_indices": FakeArray([1], dtype="int64"),
            "critical_bus_ids": FakeArray([2], dtype="int64"),
            "threshold": 1.5,
            "stv": {
                "space_range": 120.5,
                "time_range_steps": 6.0,
                "time_range_hours": 1.5,
                "max_valid_space_lag": 300.0,
                "max_valid_time_lag": 12.0,
            },
        }

    def compute_moran_analysis(self, **kwargs: Any) -> dict[str, Any]:
        self._require_prepared("compute_moran_analysis")
        self.calls.append(("compute_moran_analysis", dict(kwargs)))
        return {
            "moran_instability": FakeMoran(),
            "moran_mean_load": FakeMoran(i=0.11),
            "lisa_instability": FakeMoranLocal(),
            "clusters_instability": FakeArray([0, 1, 2], dtype="int64"),
            "clusters_mean_load": FakeArray([0, 0, 1], dtype="int64"),
            "cluster_labels_map": {0: "Not Significant", 1: "High-High", 2: "Low-Low"},
            "bus_ids_used": FakeArray([1, 2, 3], dtype="int64"),
            "weights": object(),
        }

    def compute_topology_analysis(self) -> dict[str, Any]:
        self._require_prepared("compute_topology_analysis")
        self.calls.append(("compute_topology_analysis", {}))
        return {
            "graph": object(),
            "metrics": {
                "degree": FakeArray([2.0, 3.0, 1.0]),
                "betweenness": FakeArray([0.10, 0.80, 0.00]),
                "closeness": FakeArray([0.40, 0.90, 0.20]),
                "bus_ids": FakeArray([1, 2, 3], dtype="int64"),
            },
            "correlations": {"degree": 0.51, "betweenness": float("nan")},
        }

    def compute_directional_variograms(self, **kwargs: Any) -> dict[str, Any]:
        self._require_prepared("compute_directional_variograms")
        self.calls.append(("compute_directional_variograms", dict(kwargs)))
        return {
            "ranges": {0: 80.0, 45: 55.0, 90: 40.0, 135: 60.0},
            "major_azimuth": 0,
            "minor_azimuth": 90,
            "a_global": 80.0,
            "b_global": 40.0,
            "angle_global": 0.0,
        }

    def compute_local_anisotropy(self, **kwargs: Any) -> dict[str, Any]:
        self._require_prepared("compute_local_anisotropy")
        self.calls.append(("compute_local_anisotropy", dict(kwargs)))
        return {
            "local_iso": FakeArray([12.0, float("nan"), 9.0]),
            "local_a": FakeArray([15.0, float("nan"), 11.0]),
            "local_b": FakeArray([8.0, float("nan"), 6.0]),
            "local_angle": FakeArray([45.0, float("nan"), 10.0]),
        }

    def compute_multidim_instability(self, **kwargs: Any) -> dict[str, Any]:
        self._require_prepared("compute_multidim_instability")
        self.calls.append(("compute_multidim_instability", dict(kwargs)))
        return {
            "feature_names": ["load_rms", "roc_mean", "osc_rate"],
            "cluster_summary": {"0": {"load_rms": 0.4}, "1": {"load_rms": 1.2}},
            "pca_results": {
                "cluster_labels": FakeArray([0, 1, 0], dtype="int64"),
                "explained_variance_ratio": FakeArray([0.7, 0.2]),
                "cumulative_variance": 0.9,
            },
        }

    def run_industrial_daynight_scenario(self, **kwargs: Any) -> dict[str, Any]:
        self._require_prepared("run_industrial_daynight_scenario")
        self.calls.append(("run_industrial_daynight_scenario", dict(kwargs)))
        return {
            "moran_comparison": {"delta": {"I": 0.05}},
            "lisa_comparison": {"changed": 2},
            "midday_time_idx": 56,
        }

    def _require_prepared(self, method: str) -> None:
        if not self.prepared:
            raise RuntimeError(f"Data not prepared. Call prepare_data() before {method}().")


class ExplodingAnalyzer(FakeAnalyzer):
    """An engine that fails the way GeoLoadST fails on an empty ROI."""

    def compute_spatiotemporal_instability(self, **kwargs: Any) -> dict[str, Any]:
        raise ValueError("No buses available after preparation.")


class AvailablePlugin(GeoLoadSTPlugin):
    """Plugin whose availability probe is forced, so dispatch can be tested offline."""

    def is_available(self) -> AvailabilityReport:
        return AvailabilityReport(
            status="available",
            package_available=True,
            compatible_version=True,
            installed_version="0.1.1",
            supported_version_range=SUPPORTED_GEOLOADST_RANGE,
            detail="Forced available for offline adapter tests.",
        )


@pytest.fixture
def fake_analyzers() -> list[FakeAnalyzer]:
    return []


@pytest.fixture
def plugin(fake_analyzers: list[FakeAnalyzer]) -> AvailablePlugin:
    """Adapter wired to a fake engine, with every analyzer it built kept for assertions."""

    def factory(dataset: DatasetSpec) -> FakeAnalyzer:
        analyzer = FakeAnalyzer(dataset)
        fake_analyzers.append(analyzer)
        return analyzer

    return AvailablePlugin(engine=GeoLoadSTEngine(analyzer_factory=factory))
