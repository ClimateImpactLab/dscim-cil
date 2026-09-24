# dscim-cil

[![Tests](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/test.yml/badge.svg)](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/ClimateImpactLab/dscim-cil/graph/badge.svg)](https://codecov.io/gh/ClimateImpactLab/dscim-cil)
[![container](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/container.yml/badge.svg)](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/container.yml)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/ClimateImpactLab/dscim-cil/HEAD?labpath=examples%2Fdemo.ipynb)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)

A command-line interface to [dscim](https://github.com/ClimateImpactLab/dscim),
the Climate Impact Lab's social cost of carbon library. It drives both
of dscim's run modes from one YAML config: EPA/RFF (10,000
probabilistic draws over a `runid` dimension, precomputed damage
functions) and discrete SSP/RCP (enumerated scenarios, damage functions
fitted during the run).

## Installation

The catalogue, validation, and planning commands need only click and
PyYAML:

```shell
uv pip install .
```

Real runs need dscim and its stack. The `run` extra pins the dscim
`main` commit the test suite runs against:

```shell
uv pip install ".[run]"
```

Every run writes a `*_run_metadata.yaml` recording the dscim version and
commit that produced it.

## Quick start

No data needed:

```shell
dscim-cil stages                      # the pipeline and its dimension collapses
dscim-cil options                     # the full option surface
dscim-cil explain fair_aggregation    # one option in detail
dscim-cil constraints                 # cross-option validity rules
dscim-cil defaults                    # dscim's defaults and what you must set
```

[examples/demo.ipynb](examples/demo.ipynb) runs the walkthrough on
generated fixtures; the Binder badge above launches it.

## Commands

| Command | What it does |
|---|---|
| `validate CONFIG` | Check a config and report every problem found. |
| `plan CONFIG` | The pipeline for this config as ordered steps, ready or blocked. |
| `run CONFIG` | Execute the configured sweep of menu runs (`--dry-run`, `--resume`). |
| `sum-sectors CONFIG` | Build aggregate sectors (dscim `sum_AMEL`). |
| `reduce CONFIG` | Collapse the batch dimension (dscim `reduce_damages`). |
| `combine CONFIG` | Merge coastal and AMEL damage-function coefficients. |
| `scc CONFIG` | Compose SCCs from uncollapsed run outputs. |
| `stages` | Explain the pipeline and its dimension collapses. |
| `options` | List every dscim option with status and default. |
| `explain OPTION` | Full catalogue record for one option. |
| `constraints` | Cross-option validity rules with citations. |
| `defaults [CONFIG]` | Every effective value and where it came from. |

Every command taking a config accepts `-c KEY=VALUE` overrides (dotted
keys, YAML-parsed values); options can also be set through `DSCIM_CIL_*`
environment variables. Start from
[examples/minimal.yaml](examples/minimal.yaml); the full surface is in
[examples/ssp.yaml](examples/ssp.yaml) and
[examples/rff.yaml](examples/rff.yaml).

## Running

```shell
dscim-cil validate config.yml
dscim-cil plan config.yml
dscim-cil run config.yml --dry-run
dscim-cil run config.yml --resume
dscim-cil scc config.yml
```

Values that select the scientific result (eta, rho, recipe,
discounting, formula, pulse years) must be set explicitly; dscim's
defaults for them are shown by `explain` but never applied silently.

## dscim versions

dscim-cil targets dscim `main`, pinned to the commit in the `run` extra.

## Container

Published to ghcr on every push to main (`edge`) and on version tags:

```shell
docker pull ghcr.io/c1587s/dscim-cil:edge
docker run --rm -v ./conf:/mnt/conf:ro -v ./data:/mnt/data \
    ghcr.io/c1587s/dscim-cil:edge run /mnt/conf/config.yml
```

Or build locally:

```shell
docker build -t dscim-cil:dev .
```

## Development

```shell
uv sync --group tests
just validate      # format, lint, test
```

Unit tests run without dscim installed; the integration suite is marked
`integration` and skipped unless dscim is importable.