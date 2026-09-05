# GeoLoadST capability inventory

Source: GeoLoadST repository
[GeoLoadSTLab/geoloadst](https://github.com/GeoLoadSTLab/geoloadst), inspected
`main` commit `079dc2cb` (tags `v0.1.0`, `v0.1.1`). Package version string is
`0.1.0`. This list is taken from the Python modules, not from marketing text.

Public import:

```python
from geoloadst import InstabilityAnalyzer
```

## Engine entry points

| Binding | Inputs | Outputs | Notes |
|---|---|---|---|
| `InstabilityAnalyzer.prepare_data` | `pandapowerNet`, optional ROI bbox or `roi_fraction`, `time_window`, `dt_minutes` | `bus_ids`, `coords`, `bus_load_df` | Uses `geoloadst.io` |
| `compute_spatiotemporal_instability` | prepared data; `max_buses`, `max_times`, `max_pairs` | RMS index, critical mask, STV dict | Subsamples high-mean-load buses |
| `compute_directional_variograms` | coords + instability field | ranges, major/minor azimuth, ellipse axes | Requires prior instability |
| `compute_local_anisotropy` | critical subset + local lags | local ellipse parameters | |
| `compute_multidim_instability` | load table | features, PCA, KMeans, cluster summary | Voltage flags not passed |
| `compute_moran_analysis` | coords + load + instability | Global Moran + LISA for mean load and instability | KNN weights |
| `run_industrial_daynight_scenario` | load + coords | scaled profiles, Moran/LISA comparison | Synthetic scenario |
| `compute_topology_analysis` | `net` + instability | degree/betweenness/closeness + correlations | NetworkX |
| `run_full_workflow` | many knobs | combined dict | Convenience wrapper |
| `get_summary` | accumulated results | per-bus `DataFrame` | |

## Instability primitives

| Function | File | Required input | Output | Limitation |
|---|---|---|---|---|
| `rms_instability` | `core/instability_index.py` | standardized `(N, T)` | per-node RMS | Load fluctuation, not transient stability |
| `rate_of_change` | same | `(N, T)` | mean abs first difference | **Not** RoCoF |
| `oscillation_rate` | same | `(N, T)` | sign-change fraction | Not modal analysis |
| `oscillation_rate_from_diff` | same | `(N, T)` | sign flips of diffs | |
| `classify_critical_nodes` | same | instability vector, quantile or threshold | mask, indices, threshold | “Critical” = high score |

`detrend_and_standardize` (`core/preprocessing.py`) is a prerequisite for the
RMS path used by the analyzer.

## Spatial statistics

| Function | File | Input | Output |
|---|---|---|---|
| `build_knn_weights` | `core/moran.py` | coords, `k` | libpysal weights |
| `global_moran` | same | value vector + W | Moran object |
| `local_moran` / `local_moran_clusters` | same | value vector + W | LISA / class codes |
| `classify_lisa_clusters` | same | LISA | 0=NS, 1=HH, 2=LL, 3=LH, 4=HL |
| `moran_time_series` | same | load `DataFrame` + W | I per time step |
| `moran_analysis_summary` | same | mean load + instability + W | both global and local results |

## Spatio-temporal and anisotropy

| Function | File | Output |
|---|---|---|
| `compute_stv` | `core/spatiotemporal.py` | space/time ranges, marginal variograms (`Vx`/`Vt` aliases) |
| `compute_directional_variograms` | same | per-azimuth ranges, major/minor azimuth |
| `compute_local_variograms` | same | local directional structure |

Pair counts are bounded (`max_pairs`). Ranges are geostatistical, not electrical.

## Topology

| Function | File | Output |
|---|---|---|
| `build_network_graph` | `core/topology.py` | NetworkX graph from lines (+ trafos) |
| `compute_topological_metrics` | same | degree, betweenness, closeness |
| `correlate_instability_topology` | same | Pearson r vs each centrality |
| `get_neighbors_isotropic` / `get_neighbors_directional` | same | neighbor indices |

Weights use `length_km` when present, not impedance.

## Multidimensional

| Function | File | Notes |
|---|---|---|
| `build_instability_features` | `core/multidim_instability.py` | `load_rms`, `roc_mean`, `osc_rate`; optional `voltage_std` / `voltage_sag` if the caller supplies arrays |
| `pca_and_cluster` | same | PCA + KMeans |
| `cluster_feature_summary` | same | per-cluster means |

Voltage is **not** produced by SimBench load profiles in the default analyzer
path. Do not register it as a supported standalone capability until a data
provider actually supplies those arrays.

## Scenario / resilience

| Function | File | Output |
|---|---|---|
| `compare_scenarios` | `core/resilience.py` | delta, ratio, pct_change for shared numeric keys |
| `vulnerability_index` | same | `0.5 * norm(instability) + 0.5 * norm(degree)` by default |
| `critical_node_summary` | same | top-n table |
| `apply_industrial_daynight_pattern` | `scenarios/industrial_daynight.py` | scaled industrial cluster |
| `compare_scenario_moran` / `compute_scenario_lisa_comparison` | same | baseline vs scenario spatial stats |

## SimBench I/O (data, not analysis)

| Function | Role |
|---|---|
| `load_simbench_network(code)` | `simbench.get_simbench_net`; requires `net.profiles["load"]` |
| `extract_bus_coordinates` | `bus_geodata` or `bus.geo` |
| `select_roi_buses` | bbox filter |
| `build_bus_load_timeseries` | relative profiles × `p_mw`, summed per bus |

Documented example code in GeoLoadST README:
`1-complete_data-mixed-all-1-sw`.

## Visualization (out of plugin scope)

`geoloadst.viz.plots` and `geoloadst.viz.maps` are plotting helpers. The plugin
should return data; Ariadne/UI decide rendering. Optional viz extras
(`geopandas`, `shapely`, `contextily`) are not required for analysis.

## Not implemented as first-class GeoLoadST science

- Transient, frequency, or rotor-angle stability
- Protection coordination
- Arbitrary-city OSM → SimBench joining
- A geographic query API equivalent to Overpass

## Mapping to this plugin's catalog

See `src/ariadne_geoloadst/data/capabilities.yaml`. Every `geoloadst_binding`
in that file names a function or analyzer method listed above.
