# Examples

`load_instability_map_example.py` runs the spatial pipeline offline (or with
GeoLoadST if installed) and writes `outputs/load_instability_map.geojson`.

```bash
./.venv/bin/python examples/load_instability_map_example.py
```

It does not open a browser. The host should attach the FeatureCollection to
Ariadne's existing `AgentQueryResponse.geojson`. See
[spatial-visualization.md](../docs/spatial-visualization.md).

Later examples should also:

1. Check `GeoLoadSTPlugin().is_available()`.
2. Select a **registered** `capability_id`.
3. Load SimBench only through GeoLoadST I/O (or this package's provider).
4. Print structured provenance, not hidden reasoning.

Until then, see `docs/architecture.md` for the intended question → capability
mapping (for example “are high-instability nodes clustered?” →
`spatial_clustering_of_instability`).
