# Commands

Every command taking a config accepts `-c KEY=VALUE` overrides (dotted
keys, YAML-parsed values); options can also be set through `DSCIM_CIL_*`
environment variables. `--plain` switches off the rich rendering;
`--log-level` controls logging. All output below is real: the
catalogue commands need no data, and the pipeline commands were run on
the small generated fixtures from
[examples/demo.ipynb](https://github.com/ClimateImpactLab/dscim-cil/blob/master/examples/demo.ipynb),
with paths shortened to `/work`.

## stages

Explains the pipeline without touching any data: each stage, what it
reads and writes, and which dimensions it collapses. Its output is
reproduced on [the pipeline page](pipeline.md).

## options

Lists the catalogued dscim option surface. Each option carries a
status: `supported`, `unsupported` (accepted by dscim but broken or
restricted, with the reason), `dead` (accepted and ignored), or
`removed` (only on other dscim branches). The full list is the
[options reference](options.md); filtered by status:

```console
$ dscim-cil options --status unsupported
ecs_mask_name                    unsupported  stages=fair                     default=None
full_uncertainty_quantiles       unsupported  stages=output                   default=(0.01, 0.05, 0.17, 0.25, 0.5, 0.75, 0.83, 0.95, 0.99)
quantreg                         unsupported  stages=reduce                   default=False
quantreg_quantiles               unsupported  stages=fit                      default=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)
```

## explain

The full catalogue record for one option, or for one value of it:

```console
$ dscim-cil explain discounting_type constant_gwr
discounting_type: Discounting scheme; also controls damage-function fit grouping and population collapse.
  status: supported
  stages: fit, discount
  modes: ssp, rff
  required in config; dscim would default to None if unset, but dscim-cil never applies that silently
  source: main_recipe.py:88 (default None); accepted set main_recipe.py:52-61; assert main_recipe.py:245-247
  values:
    'constant_gwr': unsupported [library]
        Listed in DISCOUNT_TYPES but its non-constant discount-factor path has no branch in calculate_stream_discount_factors and raises UnboundLocalError; never used in any production repo or in dscim's own test matrix.
        source: main_recipe.py:52-61; calculate_stream_discount_factors has no constant_gwr branch; dscim's tests/conftest.py discount_types fixture omits it
```

## constraints

The cross-option validity rules, with citations. What it prints is
what `validate` enforces:

```console
$ dscim-cil constraints
median-params-fair-dims (requires; modes: ssp,rff)
  fair_aggregation containing median_params requires fair_dims to be exactly [simulation]; dscim documents this and does not enforce it.
  source: main_recipe.py:47 (docstring); no matching assert in __init__
clip-gmsl-formula (requires; modes: ssp,rff)
  clip_gmsl requires the formula to be one of the two gmsl-quadratic formulas.
  source: main_recipe.py:264-270 (assert)
equity-not-reduced (forbidden; modes: ssp)
  reduce.recipes may not include equity: reduce_damages has no equity branch, and the equity recipe reads risk_aversion reduced damages. Add risk_aversion to reduce.recipes instead.
  source: preprocessing.py (ce_from_chunk has adding_up and risk_aversion branches only); equity.py reads risk_aversion CEs
rff-emission-scenarios-null (requires; modes: rff)
  rff mode requires climate.emission_scenarios to be null so the rcp selection is skipped on runid-shaped FaIR files.
  source: simple_storage.py:58 docstring
rff-coefficients-required (requires; modes: rff)
  rff mode requires damage_function_path on every swept sector: ce_path is None in rff runs, so fitting is impossible and coefficients must be precomputed.
  source: utils/menu_runs.py:163-167 (run_rff)
rff-no-masks-or-fair-dims (forbidden; modes: rff)
  sweep.masks and sweep.fair_dims are not available in rff mode; run_rff has no such parameters and forces the mask off.
  source: utils/menu_runs.py:119-127,169-170
ssp-gmst-path-required (requires; modes: ssp)
  ssp mode requires a non-empty climate.gmst_path: damage points are merged with the GMST anomalies during fitting.
  source: main_recipe.py damage_function_points (gmst merge)
gmsl-formula-needs-gmsl-paths (requires; modes: ssp,rff)
  a swept sector whose formula contains gmsl requires climate.gmsl_path (ssp fitting) and climate.gmsl_fair_path.
  source: main_recipe.py (gmsl merge keyed on slr/gmsl columns); simple_storage.py:54 (anomaly_vars gate)
quantreg-lengths (requires; modes: ssp,rff)
  quantreg_quantiles and quantreg_weights must have equal length (dscim asserts this even though the weights are otherwise unused).
  source: main_recipe.py:241-243
```

## defaults

Every option's effective value and where it came from: `config`,
`flag`, `override`, `default`, `required: you must set this`, `dead`,
or `removed`. Without a config it shows dscim's own defaults and what
a config must supply; with a config, the values that would take
effect. An excerpt:

```console
$ dscim-cil defaults
base_period                  [2001, 2010]                             (default)
ce_path                      None                                     (default)
clip_gmsl                    False                                    (default)
combine_fit                  True                                     (dead)
country_mapping_path         None                                     (removed)
damages_pulse_conversion_path required                                 (required: you must set this)
discounting_type             None                                     (required: you must set this)
...
```

## validate

Checks a config and reports every problem found, not just the first.
Exit code zero means valid:

```console
$ dscim-cil validate demo.yml
config is valid
```

Validation covers the schema, the cross-field rules printed by
`constraints`, file existence for every planned run, filename
conventions, and the batch chunk size that dscim asserts deep inside a
dask graph.

## plan

The whole pipeline for a config as ordered steps, each marked ready or
blocked, with the command that produces every missing input:

```console
$ dscim-cil plan demo.yml
root: /work
1. [ready] run: fit and integrate labor
     in  [ok] fair.nc
     in  [ok] conversion.nc
     in  [ok] econ.zarr
     in  [ok] gmst.csv
     in  [ok] reduced/labor/adding_up_cc.zarr <- dscim-cil reduce
     in  [ok] reduced/labor/adding_up_no_cc.zarr <- dscim-cil reduce
     out [new] results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_scc.nc4
     out [new] results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_uncollapsed_sccs.nc4
```

## run

Expands the sweep and executes menu runs. `--dry-run` first prints the
settings the sweep will use, marking which values came from the config
and which are dscim defaults, then summarizes the expanded runs:

```console
$ dscim-cil run demo.yml --dry-run
settings:
  discounting_type           euler_ramsey                           (config)
  discrete_discounting       False                                  (default)
  eta                        2.0                                    (config)
  ext_method                 global_c_ratio                         (default)
  fair_aggregation           ['ce', 'mean']                         (config)
  fit_type                   ols                                    (default)
  gases                      ['CO2_Fossil']                         (config)
  pulse_year                 2020                                   (config)
  recipe                     adding_up                              (config)
  rho                        0.0001                                 (config)
  sector                     labor                                  (config)
  weitzman_parameter         [0.1]                                  (config)
mode: ssp
runs: 1  (1 sectors x 1 pulse_years x 1 menu pairs x 1 eta_rho x 1 masks x 1 fair_dims)
missing inputs: none
outputs: 2 files, 0 already exist
blocked runs: 0 of 1 (missing inputs)
use --verbose or --runs N[,N...] for per-run detail
```

The real run prints the same settings header, then dscim's own
progress, then one `completed` line per run pointing at the metadata
file:

```console
$ dscim-cil run demo.yml
...
Processing damage functions ...
Existing damage functions not found. Damage points will be loaded.
Adding up aggregated damages found at /work/reduced/labor/adding_up_cc.zarr, /work/reduced/labor/adding_up_no_cc.zarr. These are being loaded...
Extrapolating global consumption.
End-of-century growth rates are not capped.
Processing SCC calculation ...
Saving /work/results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_scc.nc4
Saving /work/results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_uncollapsed_sccs.nc4
Results available: /work/results/labor/2020/unmasked
completed: labor 2020 adding_up/euler_ramsey eta=2.0 rho=0.0001 (metadata: /work/results/labor/2020/unmasked/adding_up_euler_ramsey_eta2.0_rho0.0001_run_metadata.yaml)
```

`--resume` skips runs whose outputs already exist; `--recipe` and
`--discounting` narrow the sweep from the command line.

## sum-sectors

Builds the aggregate sectors declared in the `aggregates` block
(dscim's `sum_AMEL`): sums member sectors' delta and histclim into a
new sector zarr.

```console
$ dscim-cil sum-sectors config.yml
Opening labor,/work/labor_damages.zarr
Opening labor,/work/labor_damages.zarr
completed: AMEL_test from labor -> /work/AMEL_test.zarr
```

## reduce

Collapses the batch dimension per the `reduce` block (dscim's
`reduce_damages`): mean for `adding_up`, certainty equivalent at eta
for `risk_aversion`. Output names follow dscim main's two conventions,
unsuffixed for adding_up and eta-suffixed for risk_aversion:

```console
$ dscim-cil reduce config.yml
completed: /work/reduced/labor/adding_up_cc.zarr
completed: /work/reduced/labor/risk_aversion_cc_eta2.0.zarr
completed: /work/reduced/labor/adding_up_no_cc.zarr
completed: /work/reduced/labor/risk_aversion_no_cc_eta2.0.zarr
```

## combine

Merges coastal and AMEL damage-function coefficients into the combined
(CAMEL) sector's coefficient files per the `combine` block (dscim's
`combine_CAMEL_coefs`):

```console
$ dscim-cil combine config.yml
Creating adding_up euler_ramsey for CAMEL_x...
completed: CAMEL_x adding_up/euler_ramsey eta=2.0 rho=0.0001 pulse_year=2020
```

## scc

Composes SCCs from the uncollapsed outputs `run` wrote: sums marginal
damages times discount factors over years, applies the configured
deflator, and collapses the uncertainty dimension per `scc.collapse`
(`mean`, `certainty_equivalent`, or `none`):

```console
$ dscim-cil scc config.yml
completed: /work/scghgs/CAMEL_test/2020/unmasked/risk_aversion_euler_ramsey_eta2.0_rho0.0001_scghg.nc4
```

`scc.damages_from` and `scc.discounting_from` compose across runs:
marginal damages from one run, discount factors from another.
