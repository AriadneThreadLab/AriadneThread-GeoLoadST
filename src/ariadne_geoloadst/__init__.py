"""AriadneThread-GeoLoadST: optional scientific plugin boundary.

This package never vendors GeoLoadST. Importing it must succeed even when
``geoloadst`` is not installed.
"""

from __future__ import annotations

from ariadne_geoloadst.adapter import GeoLoadSTPlugin, analyze
from ariadne_geoloadst.capabilities import (
    CapabilityRegistry,
    InvalidParameterError,
    UnknownCapabilityError,
    get_capabilities,
    health_status,
    load_default_registry,
)
from ariadne_geoloadst.compatibility import PLUGIN_VERSION
from ariadne_geoloadst.schemas import (
    AvailabilityReport,
    CapabilitySpec,
    ExecutionRequest,
    ExecutionResult,
    SpatialAnalysisResult,
)
from ariadne_geoloadst.visualization import export_geojson, to_ariadne_map_payload

__version__ = PLUGIN_VERSION

__all__ = [
    "PLUGIN_VERSION",
    "AvailabilityReport",
    "CapabilityRegistry",
    "CapabilitySpec",
    "ExecutionRequest",
    "ExecutionResult",
    "GeoLoadSTPlugin",
    "InvalidParameterError",
    "SpatialAnalysisResult",
    "UnknownCapabilityError",
    "__version__",
    "analyze",
    "export_geojson",
    "get_capabilities",
    "health_status",
    "load_default_registry",
    "to_ariadne_map_payload",
]
