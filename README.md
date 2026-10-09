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

Documentation: <https://climateimpactlab.github.io/dscim-cil>. It
covers the vocabulary, every command with real output, the config
schema, the pipeline, the full options reference, the API reference,
and how to reproduce the EPA SC-CO2 numbers.

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

## Examples

The outputs below come from the small generated inputs the demo
notebook uses, with the data directory shown as `/work`.

### One scenario with flags

A config without a `sweep` block can be driven entirely by flags. The
config holds the inputs; the flags choose what to compute:

```shell
dscim-cil run scenario.yml --sector labor --pulse-year 2020 \
    --recipe adding_up --discounting euler_ramsey --eta 2.0 --rho 0.0001
```

Add `--dry-run` first to see the settings and where each value came
from, without computing anything:

```console
$ dscim-cil run scenario.yml --sector labor --pulse-year 2020 \
    --recipe adding_up --discounting euler_ramsey --eta 2.0 --rho 0.0001 --dry-run
settings:
  discounting_type           euler_ramsey                           (flag)
  discrete_discounting       False                                  (default)
  eta                        2.0                                    (flag)
  ext_method                 global_c_ratio                         (default)
  fair_aggregation           ['ce', 'mean']                         (config)
  fit_type                   ols                                    (default)
  gases                      ['CO2_Fossil']                         (config)
  pulse_year                 2020                                   (flag)
  recipe                     adding_up                              (flag)
  rho                        0.0001                                 (flag)
  sector                     labor                                  (flag)
  weitzman_parameter         [0.1]                                  (config)
mode: ssp
runs: 1  (1 sectors x 1 pulse_years x 1 menu pairs x 1 eta_rho x 1 masks x 1 fair_dims)
missing inputs: none
outputs: 2 files, 0 already exist
blocked runs: 0 of 1 (missing inputs)
use --verbose or --runs N[,N...] for per-run detail
```

The real run ends with one line per run:

```console
completed: labor 2020 adding_up/euler_ramsey eta=2.0 rho=0.0001 (metadata: /work/results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_run_metadata.yaml)
```

### The same scenario as a config file

The flags above are the `sweep` block of a config:

```yaml
mode: ssp

climate:
  gases: [CO2_Fossil]
  gmst_path: /work/gmst.csv
  gmsl_path: ""
  gmst_fair_path: /work/fair.nc
  damages_pulse_conversion_path: /work/conversion.nc
  emission_scenarios: [rcp45, rcp85]

econ:
  path: /work/econ.zarr

paths:
  reduced_damages_library: /work/reduced
  results: /work/results

sectors:
  labor:
    sector_path: /work/labor_damages.zarr
    histclim: histclim
    delta: delta
    formula: "damages ~ -1 + anomaly + np.power(anomaly, 2)"

menu:
  fair_aggregation: [ce, mean]
  weitzman_parameter: [0.1]
  subset_dict: {ssp: [SSP2, SSP3]}
  save_files: [scc, uncollapsed_sccs]

sweep:
  sectors: [labor]
  pulse_years: [2020]
  menu_pairs:
    - {recipe: adding_up, discounting: euler_ramsey}
  eta_rho: [[2.0, 0.0001]]
```

```console
$ dscim-cil validate config.yml
config is valid
$ dscim-cil run config.yml
...
completed: labor 2020 adding_up/euler_ramsey eta=2.0 rho=0.0001 (metadata: /work/results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_run_metadata.yaml)
```

The run writes three files to `/work/results/labor/2020/unmasked`: the
SCC, the uncollapsed SCCs, and a `run_metadata.yaml` recording the
settings, where each came from, and the dscim version. Flags narrow a
config that has a sweep: `--pulse-year 2030` on a config sweeping
several years keeps only 2030.

### Running with Docker

The image is published to ghcr on every push to main (`edge`) and on
version tags. It has the `run` extra installed and `dscim-cil` as its
entry point. Put the config and the data under one directory, with the
paths in the config written as the container sees them (`/mnt/data/...`):

```shell
mkdir -p data/results
docker pull ghcr.io/climateimpactlab/dscim-cil:edge
```

The container runs as user 9876, so `data/results` must be writable by
that user (for example `chmod a+w data/results`). Then check the config
and run it, mounting the directory twice, read-only for the config:

```shell
docker run --rm -v ./conf:/mnt/conf:ro -v ./data:/mnt/data \
    ghcr.io/climateimpactlab/dscim-cil:edge validate /mnt/conf/config.yml

docker run --rm -v ./conf:/mnt/conf:ro -v ./data:/mnt/data \
    ghcr.io/climateimpactlab/dscim-cil:edge run /mnt/conf/config.yml
```

Any subcommand works the same way, so the same two mounts serve
`scc`, `plan`, and the others. The results appear in `data/results` on
the host. Build the image locally with `docker build -t dscim-cil:dev .`.

## Development

```shell
uv sync --group tests
just validate      # format, lint, test
just serve-docs    # build and serve the documentation locally
```

Unit tests run without dscim installed; the integration suite is marked
`integration` and skipped unless dscim is importable.
