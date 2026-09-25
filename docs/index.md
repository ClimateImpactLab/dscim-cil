# dscim-cil

A command-line interface to [dscim](https://github.com/ClimateImpactLab/dscim),
the Climate Impact Lab's social cost of carbon library. It configures,
validates, and drives dscim; it does not reimplement any science.

It drives both of dscim's run modes from one YAML config:

- **EPA/RFF**: 10,000 probabilistic draws over a `runid` dimension,
  precomputed damage functions. This is the pipeline behind EPA's 2023
  SC-GHG report.
- **Discrete SSP/RCP**: enumerated scenarios, damage functions fitted
  during the run.

Values that select the scientific result (eta, rho, recipe,
discounting, formula, pulse years) must be set explicitly; dscim's
defaults for them are shown by `explain` but never applied silently.
Every option dscim accepts is catalogued with a status, a reason, and a
source citation; see the [options reference](options.md).

## Where to start

- [Installation](installation.md): the `run` extra and the container.
- [Commands](commands.md): every command with its real output.
- [The config file](config.md): the schema, both modes, and sweeps.
- [The pipeline](pipeline.md): the stages and what each collapses.
- [Reproducing the EPA numbers](epa.md): the published SC-CO2 values
  from the public input library.

No data is needed to explore the tool:

```shell
dscim-cil stages                      # the pipeline and its dimension collapses
dscim-cil options                     # the full option surface
dscim-cil explain fair_aggregation    # one option in detail
dscim-cil constraints                 # cross-option validity rules
dscim-cil defaults                    # dscim's defaults and what you must set
```

[examples/demo.ipynb](https://github.com/ClimateImpactLab/dscim-cil/blob/master/examples/demo.ipynb)
runs a walkthrough on generated fixtures, and
[examples/coverage.ipynb](https://github.com/ClimateImpactLab/dscim-cil/blob/master/examples/coverage.ipynb)
exercises the supported option surface.

## dscim versions

dscim-cil targets dscim `main`, pinned to the commit in the `run`
extra. Every run writes a `*_run_metadata.yaml` recording the dscim
version and commit that produced it.
