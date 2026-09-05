# Local development

Recommended sibling layout (paths are examples, never hardcoded in code):

```text
~/projects/
    osm-geoagent/                 # Ariadne Thread
    geoloadst/                    # optional clone of GeoLoadST
    AriadneThread-GeoLoadST/      # this plugin
```

Python **3.10** only, to match Ariadne Thread.

## Plugin package (no GeoLoadST)

```bash
cd ~/projects/AriadneThread-GeoLoadST
python3.10 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/pytest
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy src tests
```

Energy analysis reports `package_missing`. Ariadne OSM workflows stay
independent.

## Editable GeoLoadST (active science development)

```bash
git clone https://github.com/GeoLoadSTLab/geoloadst.git ~/projects/geoloadst
cd ~/projects/AriadneThread-GeoLoadST
./.venv/bin/pip install -e ~/projects/geoloadst
```

Do not commit that filesystem path.

## Reproducible / CI extra

```bash
./.venv/bin/pip install -e ".[scientific]"
```

This pins

`geoloadst @ git+https://github.com/GeoLoadSTLab/geoloadst.git@v0.1.1`

and pulls GeoLoadST's own dependencies (`simbench`, `pandapower`, …).

## GitHub remote (manual)

```bash
cd ~/projects/AriadneThread-GeoLoadST
git remote add origin git@github.com:AriadneThreadLab/AriadneThread-GeoLoadST.git
# git push -u origin HEAD   # only when you choose to publish
```

## What not to commit

`.env`, tokens, local absolute paths, SimBench caches, generated outputs,
`.venv`, and editable-install artifacts (already in `.gitignore`).
