# dscim-cil

[![Tests](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/test.yml/badge.svg)](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/test.yml)
<!-- TODO: codecov cannot see this repository yet. An org admin must authorise
the Codecov GitHub app for dscim-cil in the
org settings. Once that is done we can uncomment this badge:
[![codecov](https://codecov.io/gh/ClimateImpactLab/dscim-cil/graph/badge.svg)](https://codecov.io/gh/ClimateImpactLab/dscim-cil)
-->

[![container](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/container.yml/badge.svg)](https://github.com/ClimateImpactLab/dscim-cil/actions/workflows/container.yml)
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/ClimateImpactLab/dscim-cil/HEAD?labpath=examples%2Fdemo.ipynb)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)

A command-line interface to [dscim](https://github.com/ClimateImpactLab/dscim),
the Climate Impact Lab's social cost of carbon library. It drives both
of dscim's run modes from one YAML config: EPA/RFF (10,000
probabilistic draws over a `runid` dimension, precomputed damage
functions) and discrete SSP/RCP (enumerated scenarios, damage functions
fitted during the run).

Documentation: <https://climateimpactlab.github.io/dscim-cil>. It
covers every command with real output, the config schema, the
pipeline, the full options reference, and how to reproduce the EPA
SC-CO2 numbers.

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
generated fixtures; the Binder badge above launches it. Start a config
from [examples/minimal.yaml](examples/minimal.yaml).

## Container

Published to ghcr on every push to master (`edge`) and on version tags:

```shell
docker pull ghcr.io/climateimpactlab/dscim-cil:edge
docker run --rm -v ./conf:/mnt/conf:ro -v ./data:/mnt/data \
    ghcr.io/climateimpactlab/dscim-cil:edge run /mnt/conf/config.yml
```

## Development

```shell
uv sync --group tests
just validate      # format, lint, test
just serve-docs    # build and serve the documentation locally
```

Unit tests run without dscim installed; the integration suite is marked
`integration` and skipped unless dscim is importable.
