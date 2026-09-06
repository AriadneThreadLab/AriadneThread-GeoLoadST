"""Backwards-compatible alias for :mod:`ariadne_geoloadst.capabilities`.

The registry now lives with the catalog loader. Existing imports of
``ariadne_geoloadst.registry`` keep working.
"""

from __future__ import annotations

from ariadne_geoloadst.capabilities import (
    CapabilityRegistry,
    InvalidParameterError,
    UnknownCapabilityError,
    load_capability_catalog,
    load_default_registry,
)

__all__ = [
    "CapabilityRegistry",
    "InvalidParameterError",
    "UnknownCapabilityError",
    "load_capability_catalog",
    "load_default_registry",
]
