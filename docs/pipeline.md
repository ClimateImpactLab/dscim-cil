# The pipeline

`dscim-cil stages` explains the pipeline without touching any data:
each stage, the dscim function it wraps, what it reads and writes, and
which dimensions it collapses, with the source citations. Its output,
verbatim:

```console
$ dscim-cil stages
1. sum-sectors (modes: ssp)
   Sum member sectors' delta and histclim into an aggregate sector zarr (e.g. AMEL from agriculture+mortality+energy+labor).
   wraps: dscim.preprocessing.preprocessing.sum_AMEL
   consumes:
     - member sector damages zarrs (sectors.<name>.sector_path)
   produces:
     - aggregate sector damages zarr (its sector_path)
   dimensions:
     - no collapse: sums variables across sectors at identical dimensions (preprocessing.py sum_AMEL)
2. reduce (modes: ssp)
   Collapse the batch dimension of sector damages against socioeconomics, producing the reduced-damage zarrs runs consume.
   wraps: dscim.preprocessing.preprocessing.reduce_damages
   consumes:
     - sector damages zarrs (batch chunked at 15)
     - econ zarr (external)
   produces:
     - reduced zarrs: adding_up_{cc,no_cc}.zarr and risk_aversion_{cc,no_cc}_eta{eta}.zarr per sector
   dimensions:
     - batch: mean for adding_up, certainty equivalent at eta for risk_aversion (preprocessing.py ce_from_chunk)
3. run (modes: ssp,rff)
   Execute menu runs: fit damage functions (or load precomputed coefficients), apply FaIR, discount, and write SCC artifacts.
   wraps: dscim MENU_OPTIONS[recipe](**kwargs).order_plate(order)
   consumes:
     - reduced zarrs (sectors without damage_function_path; ssp only)
     - damage-function coefficient nc4s (sectors with damage_function_path; all rff sectors)
     - climate files: gmst/gmsl fitting inputs, FaIR control/pulse, pulse conversion (external)
     - econ zarr or rff socioeconomics nc4 (external)
   produces:
     - per-run artifacts named {recipe}_{discounting}_eta{eta}_rho{rho}_{artifact} under the save path
   dimensions:
     - ssp and model: collapsed when discounting contains gwr (pooled damage-function fit, pop.mean(['model','ssp']); main_recipe.py collapsed_pop and damage_function_calculation)
     - fair_dims (default [simulation]): collapsed by the FaIR aggregations ce/mean/median (main_recipe.py marginal_damages)
     - discrate: a new dimension added by constant discounting, one entry per CONST_DISC_RATES value (main_recipe.py discounted_damages)
     - rff mode: runid (10,000 draws) replaces gcm/rcp/ssp/model as the uncertainty dimensions; the ssp/model collapse happened upstream in the emulator weights (utils/rff.py weight_df; utils/menu_runs.py run_rff)
4. combine (modes: ssp)
   Merge coastal and AMEL damage-function coefficients into the combined (CAMEL) sector's coefficient files.
   wraps: dscim.preprocessing.midprocessing.combine_CAMEL_coefs
   consumes:
     - coastal and AMEL coefficient nc4s written by run (fit sectors)
   produces:
     - combined-sector coefficient (and optionally fit) nc4s
   dimensions:
     - no collapse: concatenates coefficient variables from the two sources (midprocessing.py combine_CAMEL_coefs)
5. scc (modes: ssp,rff)
   Compose SCCs from the uncollapsed run outputs: sum marginal damages times discount factors over years, deflate, and collapse the uncertainty dimension.
   consumes:
     - uncollapsed_marginal_damages and uncollapsed_discount_factors nc4s written by run
   produces:
     - SCC files under scc.output
   dimensions:
     - year: summed out by the present-value integration (dscim-facts-epa scghg_utils.py:335-337)
     - runid (rff) or the fair dims (ssp): collapsed per scc.collapse: mean, certainty_equivalent (adjustment factor (gcnp/pop)^(-eta) normalized at the pulse year, scghg_utils.py:352-357), or none
```

The production order in ssp mode is `sum-sectors`, `reduce`, `run` on
the fit sectors, `combine`, then `run` on the combined sector; `plan
CONFIG` lays this out for a specific config with each step marked
ready or blocked. In rff mode only `run` and `scc` exist: the
coefficients are precomputed inputs.
