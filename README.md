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

<!-- --8<-- [start:examples] -->
The examples run on the small inputs the test suite generates, so
nothing needs downloading. Each example below can be pasted as it is.

### Setup

From a checkout of this repository, with dscim-cil installed with the
`run` extra, generate the inputs and move into their directory:

```shell
mkdir -p example-data
python -W ignore - <<'EOF'
import pathlib
import sys

sys.path.insert(0, "tests")
import fixture_factory

fixture_factory.ssp_fixture_config(
    pathlib.Path("example-data"), pulse_years=(2020, 2030)
)
EOF
cd example-data
```

The directory now holds `econ.zarr`, `fair.nc`, `gmst.csv`,
`conversion.nc`, and the reduced damages in `reduced/`. Every config
below uses paths relative to it, so run the commands from there.

### 1. One scenario with flags

A config file is always required: the flags replace the `sweep` block,
not the config, and the data paths, the `sectors` block and the `menu`
options always live in the file. A config without a `sweep` block holds
the inputs, and the flags choose what to compute. Save the config:

```shell
cat > scenario.yml <<'EOF'
mode: ssp

climate:
  gases: [CO2_Fossil]
  gmst_path: gmst.csv
  gmsl_path: ""
  gmst_fair_path: fair.nc
  damages_pulse_conversion_path: conversion.nc
  emission_scenarios: [rcp45, rcp85]

econ:
  path: econ.zarr

paths:
  reduced_damages_library: reduced
  results: results

sectors:
  labor:
    sector_path: labor_damages.zarr
    histclim: histclim
    delta: delta
    formula: "damages ~ -1 + anomaly + np.power(anomaly, 2)"

menu:
  fair_aggregation: [ce, mean]
  weitzman_parameter: [0.1]
  subset_dict: {ssp: [SSP2, SSP3]}
  save_files:
    - scc
    - uncollapsed_sccs
    - uncollapsed_marginal_damages
    - uncollapsed_discount_factors
EOF
```

See what the flags expand to without computing anything. `--dry-run`
checks the config and the flags together; `validate` needs a `sweep`
block, so it is used from example 2 on:

```shell
dscim-cil run scenario.yml \
    --sector labor \
    --pulse-year 2020 \
    --recipe adding_up \
    --discounting euler_ramsey \
    --eta 2.0 \
    --rho 0.0001 \
    --dry-run
```

```console
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
outputs: 4 files, 0 already exist
blocked runs: 0 of 1 (missing inputs)
use --verbose or --runs N[,N...] for per-run detail
```

Each run takes one sector, one pulse year, one recipe, one discounting
type, and one eta and rho pair. This one finishes in about 7 seconds on
the example inputs. Drop `--dry-run` to run it:

```shell
dscim-cil run scenario.yml \
    --sector labor \
    --pulse-year 2020 \
    --recipe adding_up \
    --discounting euler_ramsey \
    --eta 2.0 \
    --rho 0.0001
```

dscim's own progress lines print first; the last line is

```console
completed: labor 2020 adding_up/euler_ramsey eta=2.0 rho=0.0001 (metadata: results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_run_metadata.yaml)
```

and `results/labor/2020/unmasked` holds the run's four outputs and its
`run_metadata.yaml`.

### 2. The same scenario as a config file

The flags above become a `sweep` block appended to the same config:

```shell
cp scenario.yml config.yml
cat >> config.yml <<'EOF'

sweep:
  sectors: [labor]
  pulse_years: [2020]
  menu_pairs:
    - {recipe: adding_up, discounting: euler_ramsey}
  eta_rho: [[2.0, 0.0001]]
EOF
```

```shell
dscim-cil validate config.yml
dscim-cil run config.yml
```

```console
config is valid
...
completed: labor 2020 adding_up/euler_ramsey eta=2.0 rho=0.0001 (metadata: results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_run_metadata.yaml)
```

The result is the same run. With a `sweep` block, flags narrow it:
`--pulse-year 2030` on a config that sweeps several years keeps only
2030.

### 3. A sweep

The same config with two pulse years and EPA's three discount-rate
calibrations (1.5%, 2.0%, and 2.5% Ramsey) runs six combinations. The
`scc` block says how to compose SCCs from the outputs. Replace the
`sweep` block and add it:

```shell
cp scenario.yml sweep.yml
cat >> sweep.yml <<'EOF'

sweep:
  sectors: [labor]
  pulse_years: [2020, 2030]
  menu_pairs:
    - {recipe: adding_up, discounting: euler_ramsey}
  eta_rho:
    - [1.016010255, 9.149608e-05]
    - [1.244459066, 0.00197263997]
    - [1.421158116, 0.00461878399]

scc:
  deflator: 1.0
  collapse: mean
  output: scghgs
EOF
```

The dry run shows how many runs the sweep expands to:

```shell
dscim-cil validate sweep.yml
dscim-cil run sweep.yml --dry-run
```

```console
config is valid
settings:
  discounting_type           euler_ramsey                           (config)
  discrete_discounting       False                                  (default)
  eta                        [1.016010255, 1.244459066, 1.421158116] (config)
  ext_method                 global_c_ratio                         (default)
  fair_aggregation           ['ce', 'mean']                         (config)
  fit_type                   ols                                    (default)
  gases                      ['CO2_Fossil']                         (config)
  pulse_year                 [2020, 2030]                           (config)
  recipe                     adding_up                              (config)
  rho                        [9.149608e-05, 0.00197263997, 0.00461878399] (config)
  sector                     labor                                  (config)
  weitzman_parameter         [0.1]                                  (config)
mode: ssp
runs: 6  (1 sectors x 2 pulse_years x 1 menu pairs x 3 eta_rho x 1 masks x 1 fair_dims)
missing inputs: none
outputs: 24 files, 0 already exist
blocked runs: 0 of 6 (missing inputs)
use --verbose or --runs N[,N...] for per-run detail
```

Run the sweep, then compose the SCCs. The six runs take about 40
seconds here and `scc` about 2:

```shell
dscim-cil run sweep.yml
dscim-cil scc sweep.yml
```

`run` prints dscim's progress for each run and ends with one line per
run:

```console
completed: labor 2020 adding_up/euler_ramsey eta=1.016010255 rho=9.149608e-05 (metadata: results/labor/2020/unmasked/adding_up_euler_ramsey_eta1.016010255_rho9.149608e-05_run_metadata.yaml)
completed: labor 2020 adding_up/euler_ramsey eta=1.244459066 rho=0.00197263997 (metadata: results/labor/2020/unmasked/adding_up_euler_ramsey_eta1.244459066_rho0.00197263997_run_metadata.yaml)
completed: labor 2020 adding_up/euler_ramsey eta=1.421158116 rho=0.00461878399 (metadata: results/labor/2020/unmasked/adding_up_euler_ramsey_eta1.421158116_rho0.00461878399_run_metadata.yaml)
completed: labor 2030 adding_up/euler_ramsey eta=1.016010255 rho=9.149608e-05 (metadata: results/labor/2030/unmasked/adding_up_euler_ramsey_eta1.016010255_rho9.149608e-05_run_metadata.yaml)
completed: labor 2030 adding_up/euler_ramsey eta=1.244459066 rho=0.00197263997 (metadata: results/labor/2030/unmasked/adding_up_euler_ramsey_eta1.244459066_rho0.00197263997_run_metadata.yaml)
completed: labor 2030 adding_up/euler_ramsey eta=1.421158116 rho=0.00461878399 (metadata: results/labor/2030/unmasked/adding_up_euler_ramsey_eta1.421158116_rho0.00461878399_run_metadata.yaml)
```

`scc` sums marginal damages times discount factors over the years for
each run, applies the deflator (1.0 here, no price-year conversion), and
averages over the simulations:

```console
completed: scghgs/labor/2020/unmasked/adding_up_euler_ramsey_eta1.016010255_rho9.149608e-05_scghg.nc4
completed: scghgs/labor/2020/unmasked/adding_up_euler_ramsey_eta1.244459066_rho0.00197263997_scghg.nc4
completed: scghgs/labor/2020/unmasked/adding_up_euler_ramsey_eta1.421158116_rho0.00461878399_scghg.nc4
completed: scghgs/labor/2030/unmasked/adding_up_euler_ramsey_eta1.016010255_rho9.149608e-05_scghg.nc4
completed: scghgs/labor/2030/unmasked/adding_up_euler_ramsey_eta1.244459066_rho0.00197263997_scghg.nc4
completed: scghgs/labor/2030/unmasked/adding_up_euler_ramsey_eta1.421158116_rho0.00461878399_scghg.nc4
```

### Running with Docker

The image is published to ghcr as `edge`, rebuilt on every push to
main, and under a version tag for each release. It has the `run` extra
installed and `dscim-cil` as its entry point.

Create the directory the container will use. The inputs from the setup
above are already in it; for real inputs, put them there instead.
[applications/epa-scc](https://github.com/ClimateImpactLab/dscim-cil/tree/main/applications/epa-scc) downloads dscim-facts-epa's
public input library, about 6 GB, with a script. The container runs as
user 9876, so the directory must be writable by that user:

```shell
mkdir -p example-data
chmod -R a+rwX example-data
```

Then pull the image and run example 1, with the data directory mounted at
`/mnt/data` and used as the working directory so the config's relative
paths resolve:

```shell
docker pull ghcr.io/climateimpactlab/dscim-cil:edge

docker run --rm \
    -v "$PWD/example-data:/mnt/data" \
    -w /mnt/data \
    ghcr.io/climateimpactlab/dscim-cil:edge \
    run scenario.yml \
    --sector labor \
    --pulse-year 2020 \
    --recipe adding_up \
    --discounting euler_ramsey \
    --eta 2.0 \
    --rho 0.0001
```

The results appear in `example-data/results` on the host. Any other
command takes the same mount, for example `validate sweep.yml` or
`scc sweep.yml`.

A floating tag such as `edge` moves with every push, so avoid it for
runs that must be reproducible. Use a version tag or an image digest
instead, and keep the config with the results; each run's
`run_metadata.yaml` records the dscim version and commit it used.

Build the image locally with `docker build -t dscim-cil:dev .`.

### Command-line help

```console
$ dscim-cil --help
Usage: dscim-cil [OPTIONS] COMMAND [ARGS]...

  Command-line interface to the dscim SCC library.

Options:
  --log-level TEXT  [default: INFO]
  --plain           Unadorned text output.
  -h, --help        Show this message and exit.

Commands:
  combine      Merge coastal and AMEL coefficients per the combine block.
  constraints  List the cross-option validity rules.
  defaults     Show every option's effective value and where it came from.
  explain      Show the full catalogue record for OPTION_NAME (and given...
  options      List the catalogued dscim option surface.
  plan         Show the whole pipeline for CONFIG_PATH as ordered,...
  reduce       Collapse the batch dimension per the reduce block.
  run          Expand the sweep and execute menu runs.
  scc          Compose SCCs from the uncollapsed run outputs per the scc...
  stages       Explain the pipeline: stages, data flow, and dimension...
  sum-sectors  Build the aggregate sectors declared in the aggregates block.
  validate     Validate CONFIG_PATH and report every problem found.
```

`run` takes the most options:

```console
$ dscim-cil run --help
Usage: dscim-cil run [OPTIONS] CONFIG_PATH

  Expand the sweep and execute menu runs.

  Selector flags narrow the config's sweep. In a config without a sweep block
  they supply the sweep axes; the config file is still required for the data
  paths, sectors and menu options.

Options:
  -c, --conf KEY=VALUE
  --allow-unsupported
  --dry-run
  --verbose             Per-run detail in dry-run output.
  --runs TEXT           Comma-separated 1-based run numbers for per-run
                        detail.
  --resume              Skip runs whose outputs all exist.
  --sector TEXT         Keep only these sectors.
  --pulse-year INTEGER  Keep only these pulse years.
  --recipe TEXT         Keep only these recipes.
  --discounting TEXT    Keep only these discounting types.
  --mask TEXT           Keep only these ECS masks ('unmasked' for none).
  --eta FLOAT           Select one eta/rho pair.
  --rho FLOAT           Select one eta/rho pair.
  -h, --help            Show this message and exit.
```

Options can also be set through environment variables named
`DSCIM_CIL_`, then the command, then the option: `DSCIM_CIL_RUN_ETA=2.0`
is `dscim-cil run --eta 2.0`.
<!-- --8<-- [end:examples] -->

## Development

```shell
uv sync --group tests
just validate      # format, lint, test
just serve-docs    # build and serve the documentation locally
```

Unit tests run without dscim installed; the integration suite is marked
`integration` and skipped unless dscim is importable.
