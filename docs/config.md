# The config file

One YAML schema covers both run modes; `mode: ssp | rff` is required
and every cross-field rule is checked against it. The full annotated
examples below are
[examples/ssp.yaml](https://github.com/ClimateImpactLab/dscim-cil/blob/master/examples/ssp.yaml)
and
[examples/rff.yaml](https://github.com/ClimateImpactLab/dscim-cil/blob/master/examples/rff.yaml);
[examples/minimal.yaml](https://github.com/ClimateImpactLab/dscim-cil/blob/master/examples/minimal.yaml)
is the smallest useful starting point.

## Precedence

Values merge in this order, later winning:

1. dscim's defaults (never for result-selecting values, which must be
   explicit),
2. the YAML config,
3. command flags (`--recipe`, `--discounting`),
4. `-c KEY=VALUE` overrides, dotted keys, values parsed as YAML
   scalars so lists and nulls work: `-c sweep.pulse_years=[2020]`.

`run --dry-run` and `defaults CONFIG` show every effective value with
its origin, and each run's `*_run_metadata.yaml` records the same
provenance.

## The blocks

| Block | What it holds |
|---|---|
| `climate` | The FaIR and fitting-stage climate files, gases, gas conversions, ECS mask. Keys are dscim `Climate` parameters. |
| `econ` | The socioeconomics file (`EconVars`). |
| `paths` | `results` (save root) and, in ssp mode, `reduced_damages_library`. |
| `aggregates` | Aggregate sectors and their members, consumed by `sum-sectors`. |
| `sectors` | One entry per sector; keys are the sector names. A fit sector carries `sector_path`, `histclim`, `delta`, `formula`; a coefficient-only sector carries `formula` and `damage_function_path`, and `run` loads its coefficients instead of fitting. |
| `menu` | dscim `MainRecipe` options; anything omitted uses dscim main's default. |
| `sweep` | The run axes, expanded by `run` (next section). |
| `reduce` | Reductions and recipes for the `reduce` command. |
| `combine` | Target and source sectors for the `combine` command. |
| `scc` | Deflator, collapse, output root, and optional cross-run roots for the `scc` command. |

dscim's `reduce_damages` and `sum_AMEL` read the config file
themselves, so the `sectors` and `paths` keys use their names
unchanged: the file you validate is the file dscim consumes, with no
translation in between.

## Sweeps

The `sweep` block holds the six axes of dscim's `run_ssps` product:

```yaml
sweep:
  sectors: [AMEL_m0, coastal_v0.20]
  pulse_years: [2020]
  menu_pairs:
    - {recipe: adding_up, discounting: euler_ramsey}
    - {recipe: risk_aversion, discounting: euler_ramsey}
    - {recipe: equity, discounting: euler_ramsey}
  eta_rho: [[2.0, 0.0001]]
  masks: [null]
  fair_dims: [[simulation]]
```

`run` executes the product of all axes. `menu_pairs` are explicit
(recipe, discounting) pairs, never a cross product, because production
never wants the full cross. In rff mode the `masks` and `fair_dims`
axes are a validation error: dscim's `run_rff` has no such parameters.

Narrowing a sweep from the command line is an override:

```shell
dscim-cil run config.yml -c sweep.pulse_years=[2020] --recipe adding_up
```

## Discrete SSP/RCP mode

```yaml
mode: ssp

climate:
  gases: [CO2_Fossil]
  gmst_path: /data/climate/GMTanom_all_temp_2001_2010_smooth.csv
  gmsl_path: /data/climate/coastal_gmsl_v0.20.zarr
  gmst_fair_path: /data/climate/ar6_fair162_control_pulse.nc
  gmsl_fair_path: /data/climate/gmsl_pulse.zarr
  damages_pulse_conversion_path: /data/climate/conversion_v5.02.nc4
  ecs_mask_path: /data/climate/parameter_filters_truncate_ECS_v4.0.nc
  emission_scenarios: [ssp245, ssp370]

econ:
  path: /data/econ/integration-econ-bc39.zarr

paths:
  reduced_damages_library: /results/reduced_damages
  results: /results/AR6_ssp

# Aggregate sectors built by `dscim-cil sum-sectors` (dscim sum_AMEL):
# the named sector sums its members' delta/histclim.
aggregates:
  AMEL_m0: [agriculture, mortality_v0, energy, labor]

sectors:
  agriculture:
    sector_path: /data/sectors/agriculture.zarr
    histclim: histclim
    delta: delta
    formula: "damages ~ -1 + anomaly + np.power(anomaly, 2)"
  labor:
    sector_path: /data/sectors/labor.zarr
    histclim: histclim_rebased
    delta: delta_rebased
    formula: "damages ~ -1 + anomaly + np.power(anomaly, 2)"
  AMEL_m0:
    sector_path: /data/sectors/AMEL_m0.zarr
    histclim: summed_histclim
    delta: summed_delta
    formula: "damages ~ -1 + anomaly + np.power(anomaly, 2)"
  coastal_v0.20:
    sector_path: /data/sectors/coastal_v0.20.zarr
    histclim: histclim
    delta: delta
    formula: "damages ~ -1 + gmsl + np.power(gmsl, 2)"
  # Coefficient-only sector: no sector_path/histclim/delta. The presence
  # of damage_function_path makes `run` load coefficients instead of
  # fitting; it is written by `dscim-cil combine`.
  CAMEL_m0_c0.20:
    formula: "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)"
    damage_function_path: /results/AR6_ssp/CAMEL_m0_c0.20/2020/unmasked

# MainRecipe options; anything omitted uses dscim main's default.
menu:
  fit_type: ols
  discrete_discounting: false
  fair_aggregation: [ce, median, mean, gwr_mean, median_params]
  weitzman_parameter: [0.1, 0.5]
  subset_dict: {ssp: [SSP2, SSP3, SSP4]}
  ext_method: global_c_ratio
  ext_subset_start_year: 2085
  ext_subset_end_year: 2099
  ext_end_year: 2300

sweep:
  sectors: [AMEL_m0, coastal_v0.20]
  pulse_years: [2020]
  menu_pairs:
    - {recipe: adding_up, discounting: euler_ramsey}
    - {recipe: risk_aversion, discounting: euler_ramsey}
    - {recipe: equity, discounting: euler_ramsey}
  eta_rho: [[2.0, 0.0001]]
  masks: [null]
  fair_dims: [[simulation]]

# Consumed by `dscim-cil reduce`. equity is not listed: it reads
# the risk_aversion reduced damages.
reduce:
  reductions: [cc, no_cc]
  recipes: [adding_up, risk_aversion]
```

## EPA/RFF mode

```yaml
mode: rff

climate:
  gases: [CO2_Fossil, CH4, N2O]
  gmst_fair_path: /inputs/climate/gmst_pulse.nc4
  gmsl_fair_path: /inputs/climate/gmsl_pulse.nc4
  # gmst_path/gmsl_path feed damage-function fitting, which never runs
  # in rff mode; empty strings are accepted here only.
  gmst_path: ""
  gmsl_path: ""
  # Conversion factors inline; the netCDF dscim reads is generated at
  # {paths.results}/gas_conversions.nc4. A damages_pulse_conversion_path
  # to an existing file works instead.
  gas_conversions:
    CO2_Fossil: 2.72916487e-10
    CH4: 2.5e-08
    N2O: 6.36480131e-07
  ecs_mask_path: null
  # Must be null: runid-shaped FaIR files have no rcp dimension.
  emission_scenarios: null

econ:
  # Explicit file (dscim-facts-epa hardcodes the filename; here it is
  # config). Swap in rff_USA_socioeconomics.nc4 for territorial-US
  # damages.
  path: /inputs/econ/rff_global_socioeconomics.nc4

paths:
  results: /results/rff

sectors:
  # Every rff sector must carry damage_function_path: ce_path is None in
  # rff runs, so coefficients cannot be fitted, only loaded. The file
  # name encodes recipe/discounting/eta/rho; nothing cross-checks the
  # file contents against those values.
  CAMEL_m1_c0.20:
    formula: "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)"
    damage_function_path: /inputs/damage_functions/CAMEL_m1_c0.20

menu:
  # Empty list: skip the collapsed-SCC computation inside dscim and keep
  # the uncollapsed outputs; `dscim-cil scc` composes SCCs from them.
  # global_consumption_no_pulse feeds the certainty_equivalent collapse.
  fair_aggregation: []
  weitzman_parameter: [0.5]
  save_files: [uncollapsed_sccs, uncollapsed_marginal_damages,
               uncollapsed_discount_factors, global_consumption_no_pulse]

sweep:
  sectors: [CAMEL_m1_c0.20]
  pulse_years: [2020, 2030]
  menu_pairs:
    - {recipe: risk_aversion, discounting: euler_ramsey}
  eta_rho:
    - [1.421158116, 0.00461878399]
  # masks: / fair_dims: axes are a validation error in rff mode.

# Consumed by `dscim-cil scc`: compose SCCs from the uncollapsed
# outputs, deflate, and collapse across runid. damages_from and
# discounting_from may point at a different results root, e.g.
# territorial-US damages against global discounting.
scc:
  deflator: 1.012094        # explicit factor; e.g. 113.648/112.29 is the
                            # 2019 to 2020 USD conversion dscim-facts-epa uses
  collapse: certainty_equivalent
  output: /results/scghgs
```
