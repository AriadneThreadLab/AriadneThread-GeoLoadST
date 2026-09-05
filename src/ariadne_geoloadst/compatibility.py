"""Version and import compatibility for the optional GeoLoadST engine."""

from __future__ import annotations

from importlib import import_module, metadata
from importlib.util import find_spec

from ariadne_geoloadst.schemas import AvailabilityReport

PLUGIN_ID = "ariadne_geoloadst"
PLUGIN_VERSION = "0.1.0"
ADAPTER_VERSION = "adapter-1"
CAPABILITY_CATALOG_VERSION = "geoloadst-capabilities-1"

#: Inclusive lower bound, exclusive upper bound. Matches inspected tags v0.1.0 / v0.1.1.
SUPPORTED_GEOLOADST_RANGE = ">=0.1.0,<0.2.0"
_MIN_TUPLE = (0, 1, 0)
_MAX_EXCLUSIVE_TUPLE = (0, 2, 0)


def probe_geoloadst() -> AvailabilityReport:
    """Inspect the environment without importing Ariadne Thread or running analysis."""
    if find_spec("geoloadst") is None:
        return AvailabilityReport(
            status="package_missing",
            package_available=False,
            compatible_version=False,
            installed_version=None,
            supported_version_range=SUPPORTED_GEOLOADST_RANGE,
            missing=("geoloadst",),
            detail=(
                "The geoloadst package is not installed. OSM and other Ariadne "
                "capabilities are unaffected. Energy-grid analysis is unavailable."
            ),
        )

    installed = _installed_version()
    compatible = installed is not None and _is_supported(installed)
    missing: tuple[str, ...] = ()
    status: str
    detail: str
    if not compatible:
        status = "incompatible_version"
        detail = (
            f"Installed GeoLoadST {installed!r} is outside the supported range "
            f"{SUPPORTED_GEOLOADST_RANGE}."
        )
    else:
        optional_missing = _missing_scientific_imports()
        if optional_missing:
            status = "optional_dependency_missing"
            missing = optional_missing
            compatible = False
            detail = (
                "GeoLoadST is installed but required scientific dependencies are missing: "
                + ", ".join(optional_missing)
            )
        else:
            status = "available"
            detail = f"GeoLoadST {installed} is available and within {SUPPORTED_GEOLOADST_RANGE}."

    return AvailabilityReport(
        status=status,  # type: ignore[arg-type]
        package_available=True,
        compatible_version=compatible,
        installed_version=installed,
        supported_version_range=SUPPORTED_GEOLOADST_RANGE,
        missing=missing,
        detail=detail,
    )


def _installed_version() -> str | None:
    try:
        return metadata.version("geoloadst")
    except metadata.PackageNotFoundError:
        pass
    try:
        module = import_module("geoloadst")
    except Exception:
        return None
    version = getattr(module, "__version__", None)
    return version if isinstance(version, str) else None


def _is_supported(version: str) -> bool:
    parsed = _parse_version(version)
    if parsed is None:
        return False
    return _MIN_TUPLE <= parsed < _MAX_EXCLUSIVE_TUPLE


def _parse_version(version: str) -> tuple[int, int, int] | None:
    core = version.split("+", 1)[0].split("-", 1)[0]
    parts = core.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return None
    return (major, minor, patch)


def _missing_scientific_imports() -> tuple[str, ...]:
    required = ("numpy", "pandas", "pandapower", "simbench", "networkx")
    return tuple(name for name in required if find_spec(name) is None)
