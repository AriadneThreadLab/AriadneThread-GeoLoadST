# Examples

Phase 1 ships no live notebooks. After scientific binding (Phase 2), examples
should:

1. Check `GeoLoadSTPlugin().is_available()`.
2. Select a **registered** `capability_id`.
3. Load SimBench only through GeoLoadST I/O (or this package's provider).
4. Print structured provenance, not hidden reasoning.

Until then, see `docs/architecture.md` for the intended question → capability
mapping (for example “are high-instability nodes clustered?” →
`spatial_clustering_of_instability`).
