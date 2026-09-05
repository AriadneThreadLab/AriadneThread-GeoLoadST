"""Load the closed GeoLoadST capability catalog from package data."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ariadne_geoloadst.compatibility import CAPABILITY_CATALOG_VERSION
from ariadne_geoloadst.schemas import CapabilityCatalog

_DATA_PATH = Path(__file__).resolve().parent / "data" / "capabilities.yaml"


@lru_cache(maxsize=1)
def load_capability_catalog() -> CapabilityCatalog:
    """Return the versioned catalog. Unknown extra YAML keys are rejected."""
    raw = yaml.safe_load(_DATA_PATH.read_text(encoding="utf-8"))
    catalog = CapabilityCatalog.model_validate(raw)
    if catalog.catalog_version != CAPABILITY_CATALOG_VERSION:
        raise ValueError(
            f"capability catalog version {catalog.catalog_version!r} does not match "
            f"{CAPABILITY_CATALOG_VERSION!r}"
        )
    return catalog
