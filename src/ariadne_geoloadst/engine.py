"""Lazy binding to the GeoLoadST engine.

The plugin owns the *call*, GeoLoadST owns the *computation*. This module
builds an ``InstabilityAnalyzer`` from a validated request and replays the
capability's declared engine plan. It never chooses a method at runtime, never
derives a scientific quantity, and never imports ``geoloadst`` at module
import time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ariadne_geoloadst.capabilities import build_engine_arguments
from ariadne_geoloadst.geometry import extract_spatial_network
from ariadne_geoloadst.normalization import (
    TruncationWarningCollector,
    extract_result_keys,
)
from ariadne_geoloadst.schemas import (
    CapabilitySpec,
    EngineInvocation,
    ExecutionRequest,
    ParameterValue,
    SpatialNetwork,
)


class EngineError(RuntimeError):
    """Base class for failures on the engine side of the boundary."""


class EngineNotAvailableError(EngineError):
    """GeoLoadST (or its scientific stack) could not be imported."""


class EngineContractError(EngineError):
    """The installed engine does not expose a method the catalog declares."""


class EngineExecutionError(EngineError):
    """GeoLoadST raised while computing. The original error is chained."""


@runtime_checkable
class AnalyzerLike(Protocol):
    """Structural type of the engine entry point the plans are written against.

    Declared so tests can supply a stand-in without installing the scientific
    stack, and so the adapter never depends on a concrete import.
    """

    def prepare_data(self) -> Any: ...


@dataclass(frozen=True)
class DatasetSpec:
    """Everything needed to instantiate the engine for one run."""

    simbench_network_code: str | None
    dataset_id: str | None = None
    roi_bbox: tuple[float, float, float, float] | None = None
    roi_fraction: float | None = None
    time_window: tuple[int, int] | None = None
    dt_minutes: float = 15.0

    @classmethod
    def from_request(cls, request: ExecutionRequest) -> DatasetSpec:
        return cls(
            simbench_network_code=request.simbench_network_code,
            dataset_id=request.dataset_id,
            roi_bbox=request.roi_bbox,
            roi_fraction=request.roi_fraction,
            time_window=request.time_window,
            dt_minutes=request.dt_minutes,
        )

    def describe(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "simbench_network_code": self.simbench_network_code,
            "roi_bbox": list(self.roi_bbox) if self.roi_bbox is not None else None,
            "roi_fraction": self.roi_fraction,
            "time_window": list(self.time_window) if self.time_window is not None else None,
            "dt_minutes": self.dt_minutes,
        }


@dataclass(frozen=True)
class EngineRun:
    """Normalized engine outcome plus the trace of what was actually called."""

    outputs: dict[str, object]
    invocations: tuple[EngineInvocation, ...]
    warnings: tuple[str, ...] = ()
    dataset: dict[str, object] = field(default_factory=dict)
    network: SpatialNetwork | None = None


AnalyzerFactory = Callable[[DatasetSpec], AnalyzerLike]


def default_analyzer_factory(dataset: DatasetSpec) -> AnalyzerLike:
    """Load a SimBench case with GeoLoadST's own I/O and wrap it in its analyzer."""
    if dataset.simbench_network_code is None:
        raise EngineNotAvailableError(
            "no dataset selected: a SimBench network code is required to build the engine input"
        )
    try:
        from geoloadst import InstabilityAnalyzer
        from geoloadst.io import load_simbench_network
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise EngineNotAvailableError(
            "GeoLoadST is not importable; install the 'scientific' extra to enable analysis"
        ) from exc

    try:
        net = load_simbench_network(dataset.simbench_network_code)
    except Exception as exc:
        raise EngineExecutionError(
            f"GeoLoadST could not load SimBench case {dataset.simbench_network_code!r}: {exc}"
        ) from exc

    analyzer: AnalyzerLike = InstabilityAnalyzer(
        net=net,
        roi=dataset.roi_bbox,
        roi_fraction=dataset.roi_fraction,
        time_window=dataset.time_window,
        dt_minutes=dataset.dt_minutes,
    )
    return analyzer


class GeoLoadSTEngine:
    """Replays a capability's declared plan against the GeoLoadST analyzer."""

    def __init__(self, analyzer_factory: AnalyzerFactory | None = None) -> None:
        self._analyzer_factory = (
            analyzer_factory if analyzer_factory is not None else default_analyzer_factory
        )

    def run(
        self,
        *,
        spec: CapabilitySpec,
        dataset: DatasetSpec,
        parameters: dict[str, ParameterValue],
    ) -> EngineRun:
        plan = spec.engine_call
        if plan is None:
            raise EngineContractError(
                f"capability {spec.capability_id!r} has no engine plan to execute"
            )

        analyzer = self._analyzer_factory(dataset)
        warnings = TruncationWarningCollector()
        invocations: list[EngineInvocation] = []

        if plan.preparation is not None:
            self._call(analyzer, plan.preparation, {}, spec)
            invocations.append(EngineInvocation(method=plan.preparation))

        result: Any = None
        for step in plan.steps:
            arguments = build_engine_arguments(step.parameter_map, parameters)
            result = self._call(analyzer, step.method, arguments, spec)
            invocations.append(EngineInvocation(method=step.method, arguments=arguments))

        outputs = extract_result_keys(result, plan.result_keys, warnings=warnings)
        network = extract_spatial_network(analyzer)
        return EngineRun(
            outputs=outputs,
            invocations=tuple(invocations),
            warnings=warnings.messages,
            dataset=dataset.describe(),
            network=network,
        )

    @staticmethod
    def _call(
        analyzer: AnalyzerLike,
        method_name: str,
        arguments: dict[str, ParameterValue],
        spec: CapabilitySpec,
    ) -> Any:
        method = getattr(analyzer, method_name, None)
        if method is None or not callable(method):
            raise EngineContractError(
                f"installed GeoLoadST engine has no method {method_name!r} required by "
                f"capability {spec.capability_id!r}"
            )
        try:
            return method(**arguments)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineExecutionError(
                f"GeoLoadST failed during {method_name!r} for capability "
                f"{spec.capability_id!r}: {exc}"
            ) from exc
