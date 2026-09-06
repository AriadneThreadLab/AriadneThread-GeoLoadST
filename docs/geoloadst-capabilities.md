# GeoLoadST capability inventory

Inspection source: [GeoLoadSTLab/geoloadst](https://github.com/GeoLoadSTLab/geoloadst),
local clone of `main` at commit `079dc2cb` (tags `v0.1.0`, `v0.1.1`).
The installed package version string is `0.1.0`.

This list is taken from the Python modules. Marketing text and visualization
helpers are not treated as scientific capabilities. Nothing below is invented.

Public import:

```python
from geoloadst import InstabilityAnalyzer
```

`geoloadst.__init__` exports only `InstabilityAnalyzer` and `__version__`.

---

## Package structure

```text
geoloadst/
  __init__.py                 public export
  api.py                      InstabilityAnalyzer
  io/simbench_adapter.py      SimBench / pandapower I/O
  core/
    preprocessing.py          detrend_and_standardize
    instability_index.py      RMS, RoCoL, oscillation, critical nodes
    spatiotemporal.py         STV, directional and local variograms
    moran.py                  KNN weights, global Moran, LISA
    topology.py               graph, centralities, correlation
    resilience.py             scenario compare, vulnerability blend
    multidim_instability.py   features, PCA, KMeans
    roi.py                    bbox / centre-fraction helpers
  scenarios/industrial_daynight.py
  viz/                        plots and maps (out of plugin scope)
```

---

## Input formats

GeoLoadST does not accept a city name or an OSM query.

| Input | Source | Shape / meaning |
|---|---|---|
| `pandapowerNet` | `geoloadst.io.load_simbench_network(code)` | SimBench case with `net.profiles["load"]` |
| Bus coordinates | `extract_bus_coordinates` | `(N, 2)` from `bus_geodata` or `bus.geo` |
| Load time series | `build_bus_load_timeseries` | `DataFrame` time × bus; relative profile × `p_mw`, summed per bus |
| ROI | constructor `roi=(xmin, xmax, ymin, ymax)` or `roi_fraction` | Filter on the case's own coordinates |
| Time window | constructor `time_window=(start, end)` | Slice of the profile; default `(0, 96)` |
| `dt_minutes` | constructor, default `15.0` | Used for hours conversion and day/night hours |

Documented example code: `1-complete_data-mixed-all-1-sw`.

Networks without `net.profiles["load"]` raise in `load_simbench_network`.

---

## Output formats

Analyzer methods return Python `dict` values. Typical payloads:

- `numpy.ndarray` (instability scores, masks, coordinates, cluster codes)
- `pandas.DataFrame` (load tables, `get_summary`)
- `esda.Moran` / `Moran_Local` objects
- nested dicts (`stv`, `pca_results`, scenario comparisons)
- opaque handles (`libpysal` weights, NetworkX graph, GeoPandas frames)

This plugin normalizes those values. It does not recompute them.

---

## SimBench integration

| Function | Role |
|---|---|
| `load_simbench_network(code)` | `simbench.get_simbench_net`; requires load profiles |
| `extract_bus_coordinates` | `bus_geodata` or `bus.geo` |
| `select_roi_buses` | bbox or centred fraction |
| `build_bus_load_timeseries` | relative profiles × `p_mw`, summed per bus |

SimBench is a **named dataset**, not Overpass. A code is not “the power
network of an arbitrary city”.

---

## Dependency requirements

From GeoLoadST `pyproject.toml`:

Required: `numpy`, `pandas`, `matplotlib`, `scipy`, `scikit-learn`,
`pandapower`, `simbench`, `scikit-gstat`, `libpysal`, `esda`, `networkx`.

Optional viz extra: `geopandas`, `shapely`, `contextily`. Not required for
analysis. This plugin does not depend on the viz extra.

Python: GeoLoadST declares `>=3.9`. This plugin stays on 3.10 to match Ariadne.

---

## Engine entry points (`InstabilityAnalyzer`)

| Method | Analytical purpose | Required inputs | Outputs | Limitations |
|---|---|---|---|---|
| `prepare_data` | Materialize buses, coords, load table | `net`, optional ROI / time window | `bus_ids`, `coords`, `bus_load_df` | Empty ROI raises |
| `compute_spatiotemporal_instability` | Detrend, RMS score, critical mask, STV | prepared data | `instability_index`, `critical_*`, `threshold`, `stv`, `bus_ids_used` | Subsamples highest-mean-load buses; pair budget `max_pairs` |
| `compute_directional_variograms` | Anisotropy of the instability field | prior instability (+ coords) | `ranges`, major/minor azimuth, `a_global` / `b_global` | Default azimuths 0/45/90/135 |
| `compute_local_anisotropy` | Local ellipses around critical nodes | critical mask + instability | `local_iso`, `local_a`, `local_b`, `local_angle` | Only the first `max_crit_local` critical nodes |
| `compute_multidim_instability` | RMS / RoCoL / osc features + PCA/KMeans | prepared load table | `feature_names`, `pca_results`, `cluster_summary` | Voltage flags are not passed |
| `compute_moran_analysis` | Global Moran + LISA on mean load and instability | prepared data; instability computed if missing | `moran_*`, `clusters_*`, `cluster_labels_map`, weights | KNN on coordinates, not impedance |
| `run_industrial_daynight_scenario` | Scale an industrial cluster and compare Moran/LISA | prepared load + coords | `moran_comparison`, `lisa_comparison`, `midday_time_idx` | Synthetic scaling, not a market study |
| `compute_topology_analysis` | Degree / betweenness / closeness + Pearson vs instability | `net` + prepared buses | `metrics`, `correlations`, graph | Length-weighted graph, not impedance |
| `run_full_workflow` | Convenience wrapper | many knobs | combined dict + optional GeoPandas | Not registered as a first-class plugin capability |
| `get_summary` | Per-bus table of accumulated results | prior steps | `DataFrame` | Only columns that already exist |

---

## Catalogued capabilities

Each row is a plugin `capability_id`. Bindings name callables that exist in
the inspected tree. `status: bound` means `execute()` will replay a declared
`InstabilityAnalyzer` plan. `status: declared` means the science exists in
GeoLoadST but the analyzer has no dedicated method, so dispatch is withheld.

### `load_instability_rms`

| Field | Value |
|---|---|
| Capability name | RMS load instability |
| Analytical purpose | Per-node RMS of temporally and spatially detrended load |
| Required inputs | load time series, node coordinates |
| Outputs | `instability_index`, `bus_ids_used`, `threshold` |
| Limitations | Load-profile fluctuation, not transient or frequency stability; subsample bounds change the population |
| GeoLoadST API | `geoloadst.core.instability_index.rms_instability` via `InstabilityAnalyzer.compute_spatiotemporal_instability` |
| Status | bound |

### `load_rate_of_change`

| Field | Value |
|---|---|
| Capability name | Load rate of change |
| Analytical purpose | Mean absolute first difference (RoCoL-style) |
| Required inputs | load time series |
| Outputs | per-node mean absolute temporal difference |
| Limitations | Not Rate of Change of Frequency (RoCoF). Analyzer exposes it only inside the multidimensional feature matrix |
| GeoLoadST API | `geoloadst.core.instability_index.rate_of_change` |
| Status | declared |

### `load_oscillation_rate`

| Field | Value |
|---|---|
| Capability name | Load oscillation rate |
| Analytical purpose | Fraction of sign changes in a node's series |
| Required inputs | load time series |
| Outputs | per-node rate in `[0, 1]` |
| Limitations | Sign flips, not modal or protection oscillation. Analyzer exposes it only inside the feature matrix |
| GeoLoadST API | `geoloadst.core.instability_index.oscillation_rate` |
| Status | declared |

### `critical_node_classification`

| Field | Value |
|---|---|
| Capability name | Critical load-instability nodes |
| Analytical purpose | Threshold the RMS instability distribution (default 90th percentile) |
| Required inputs | load time series, node coordinates |
| Outputs | `critical_mask`, `critical_indices`, `critical_bus_ids`, `threshold` |
| Limitations | “Critical” means a high load-instability score, not N-1 or protection criticality |
| GeoLoadST API | `geoloadst.core.instability_index.classify_critical_nodes` via `compute_spatiotemporal_instability` |
| Status | bound |

### `global_moran_instability`

| Field | Value |
|---|---|
| Capability name | Global Moran I of load instability |
| Analytical purpose | Test spatial autocorrelation of the RMS instability field |
| Required inputs | node coordinates, load time series |
| Outputs | `moran_instability`, `moran_mean_load` (Moran diagnostics) |
| Limitations | KNN weights on coordinates, not electrical distance; p-values are permutation-based |
| GeoLoadST API | `geoloadst.core.moran.global_moran` via `InstabilityAnalyzer.compute_moran_analysis` |
| Status | bound |

### `lisa_instability`

| Field | Value |
|---|---|
| Capability name | Local Moran LISA of load instability |
| Analytical purpose | Local hotspots / outliers of instability |
| Required inputs | node coordinates, load time series |
| Outputs | `clusters_instability`, `clusters_mean_load`, `cluster_labels_map` |
| Limitations | Codes 0=NS, 1=HH, 2=LL, 3=LH, 4=HL. Statistical classes, not protection zones |
| GeoLoadST API | `geoloadst.core.moran.local_moran_clusters` via `compute_moran_analysis` |
| Status | bound |

### `moran_time_series`

| Field | Value |
|---|---|
| Capability name | Moran I time series of load |
| Analytical purpose | Global Moran of each load snapshot |
| Required inputs | load table, shared spatial weights |
| Outputs | one Moran I per time step |
| Limitations | Analyzer has no method; a caller must pass weights explicitly |
| GeoLoadST API | `geoloadst.core.moran.moran_time_series` |
| Status | declared |

### `space_time_variogram`

| Field | Value |
|---|---|
| Capability name | Space-time variogram of load anomalies |
| Analytical purpose | Spatial and temporal correlation lengths of the detrended field |
| Required inputs | detrended standardized load `(N, T)`, coordinates |
| Outputs | `stv.space_range`, `stv.time_range_steps`, `stv.time_range_hours`, valid lag bounds |
| Limitations | Pairwise STV is memory-heavy; GeoLoadST bounds buses, times, and pairs. Ranges are geostatistical, not electrical |
| GeoLoadST API | `geoloadst.core.spatiotemporal.compute_stv` via `compute_spatiotemporal_instability` |
| Status | bound |

### `directional_variogram`

| Field | Value |
|---|---|
| Capability name | Directional variogram of instability |
| Analytical purpose | Major / minor azimuth of the instability field |
| Required inputs | coordinates plus a prior instability field |
| Outputs | `ranges`, `major_azimuth`, `minor_azimuth`, `a_global`, `b_global`, `angle_global` |
| Limitations | Default azimuths are 0/45/90/135; they are not a catalog parameter |
| GeoLoadST API | `geoloadst.core.spatiotemporal.compute_directional_variograms` via `InstabilityAnalyzer.compute_directional_variograms` |
| Status | bound |

### `local_anisotropy`

| Field | Value |
|---|---|
| Capability name | Local anisotropy around critical nodes |
| Analytical purpose | Local directional structure around the top critical buses |
| Required inputs | coordinates, instability field, critical mask |
| Outputs | `local_iso`, `local_a`, `local_b`, `local_angle` |
| Limitations | Only the first few critical nodes are analysed; local k-NN depends on bus density |
| GeoLoadST API | `geoloadst.core.spatiotemporal.compute_local_variograms` via `InstabilityAnalyzer.compute_local_anisotropy` |
| Status | bound |

### `topology_centrality`

| Field | Value |
|---|---|
| Capability name | Network topology centrality |
| Analytical purpose | Degree, betweenness, closeness on the line / transformer graph |
| Required inputs | pandapower network |
| Outputs | `metrics` (degree, betweenness, closeness) |
| Limitations | Graph distance uses `length_km` when present, not impedance. Switching state is not modelled |
| GeoLoadST API | `geoloadst.core.topology.compute_topological_metrics` via `compute_topology_analysis` |
| Status | bound |

### `instability_topology_correlation`

| Field | Value |
|---|---|
| Capability name | Instability–topology correlation |
| Analytical purpose | Pearson r between RMS instability and each centrality |
| Required inputs | load time series, network topology |
| Outputs | `correlations` |
| Limitations | Linear association only. Zero-variance centrality yields NaN (reported as absent) |
| GeoLoadST API | `geoloadst.core.topology.correlate_instability_topology` via `compute_topology_analysis` |
| Status | bound |

### `vulnerability_index`

| Field | Value |
|---|---|
| Capability name | Instability–degree vulnerability index |
| Analytical purpose | `0.5 * norm(instability) + 0.5 * norm(degree)` by default |
| Required inputs | instability vector, degree vector |
| Outputs | per-node blended score |
| Limitations | A simple linear blend, not a published resilience standard. Analyzer has no method |
| GeoLoadST API | `geoloadst.core.resilience.vulnerability_index` |
| Status | declared |

### `multidim_pca_clustering`

| Field | Value |
|---|---|
| Capability name | Multidimensional instability PCA and clustering |
| Analytical purpose | Mix RMS, RoCoL, and oscillation, then PCA and KMeans |
| Required inputs | load time series |
| Outputs | `feature_names`, `cluster_summary`, PCA labels and explained variance |
| Limitations | Optional `voltage_std` / `voltage_sag` exist on `build_instability_features` but `InstabilityAnalyzer` does not pass them. Cluster count is a parameter |
| GeoLoadST API | `geoloadst.core.multidim_instability.pca_and_cluster` via `compute_multidim_instability` |
| Status | bound |

### `industrial_daynight_scenario`

| Field | Value |
|---|---|
| Capability name | Industrial day/night load scenario |
| Analytical purpose | Scale a detected industrial cluster and compare Moran / LISA |
| Required inputs | load time series, coordinates, optional day/night factors |
| Outputs | `moran_comparison`, `lisa_comparison`, `midday_time_idx` |
| Limitations | Synthetic profile scaling. The industrial cluster is KMeans on coordinates and mean load, not tariff data |
| GeoLoadST API | `geoloadst.scenarios.industrial_daynight.apply_industrial_daynight_pattern` via `run_industrial_daynight_scenario` |
| Status | bound |

### `spatial_clustering_of_instability`

| Field | Value |
|---|---|
| Capability name | Spatial clustering workflow for instability |
| Analytical purpose | RMS instability on a bounded subset, then global Moran and LISA |
| Required inputs | load time series, node coordinates, optional SimBench code |
| Outputs | `moran_instability`, `clusters_instability`, `cluster_labels_map` |
| Limitations | Workflow steps are fixed by the catalog. Moran/LISA run on the instability subset, not the full case |
| GeoLoadST API | `InstabilityAnalyzer.compute_spatiotemporal_instability` then `compute_moran_analysis` |
| Status | bound |

---

## Present in GeoLoadST, not registered as standalone plugin capabilities

| Callable | Why it is not a first-class capability |
|---|---|
| `detrend_and_standardize` | Prerequisite of the RMS path, not a user-facing analysis |
| `oscillation_rate_from_diff` | Variant of oscillation rate; analyzer does not expose it |
| `compare_scenarios` / `critical_node_summary` | Helpers; no analyzer method |
| `run_full_workflow` / `get_summary` | Convenience wrappers; plugin capabilities are the individual analyses |
| `geoloadst.viz.*` | Plotting. The plugin returns data; Ariadne/UI decide rendering |
| Voltage features | Only optional arguments on `build_instability_features`; not supplied by the analyzer |

---

## Not implemented as GeoLoadST science

- Transient, frequency, or rotor-angle stability
- Protection coordination
- Arbitrary-city OSM → SimBench joining
- A geographic query API equivalent to Overpass
- PV suitability (no such module; a future catalog extension, not a GeoLoadST capability)

---

## Mapping to this plugin

See `src/ariadne_geoloadst/data/capabilities.yaml`. Every `geoloadst_binding`
names a function or analyzer method listed above. Adding a future domain
(PV suitability, a second engine) is a new catalog file, not a change to the
registry module.
