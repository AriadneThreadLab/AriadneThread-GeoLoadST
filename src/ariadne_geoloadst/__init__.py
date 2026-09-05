"""AriadneThread-GeoLoadST: optional scientific plugin boundary.

This package never vendors GeoLoadST. Importing it must succeed even when
``geoloadst`` is not installed.
"""

from __future__ import annotations

from ariadne_geoloadst.adapter import GeoLoadSTPlugin
from ariadne_geoloadst.compatibility import PLUGIN_VERSION
from ariadne_geoloadst.registry import CapabilityRegistry, load_default_registry

__version__ = PLUGIN_VERSION

__all__ = [
    "PLUGIN_VERSION",
    "CapabilityRegistry",
    "GeoLoadSTPlugin",
    "__version__",
    "load_default_registry",
]
