# Concepts

The terms the rest of the documentation uses, in plain words.

## Run modes

SSP mode
:   Runs over an enumerated set of scenarios: SSP socioeconomic paths,
    RCP emissions paths, climate models, and the FaIR simulations. The
    damage function is fitted during the run, unless a sector supplies
    precomputed coefficients. Supports ECS masks and `fair_dims`.

RFF mode
:   Runs over 10,000 probabilistic draws, indexed by a `runid`
    dimension, from the RFF socioeconomic projections. The draws replace
    the scenario dimensions. Damage-function coefficients must be
    precomputed, so nothing is fitted. There are no masks and no
    `fair_dims`, and the economics file runs to 2300. This is the mode
    behind EPA's published figures.

Set `mode: ssp` or `mode: rff` in the config; it is required.

## Sweeps

Sweep
:   The set of runs a `run` command expands from the `sweep` block of a
    config: the product of the six axes below. `--dry-run` shows the
    expansion without computing it.

Sweep axes
:   Six lists. `sectors`: which sectors to run. `pulse_years`: which
    emission years. `menu_pairs`: explicit recipe and discounting pairs,
    never a cross product. `eta_rho`: pairs of the two discounting
    parameters. `masks`: ECS masks, SSP mode only. `fair_dims`: which
    FaIR dimensions to collapse, SSP mode only.

Selector flags
:   `--sector`, `--pulse-year`, `--recipe`, `--discounting`, `--mask`,
    `--eta` and `--rho` narrow the sweep of a config, or define the axes
    of a config that has no sweep block.

## Recipes

Recipe
:   How damages are aggregated over uncertainty before the damage
    function is fitted. The `recipe` option takes `adding_up`,
    `risk_aversion`, or `equity`.

`adding_up`
:   Takes the mean over the batch dimension of the sector damages.

`risk_aversion`
:   Takes the certainty equivalent at `eta` over the batch dimension, so
    bad outcomes weigh more than a plain mean gives them.

`equity`
:   Reads the `risk_aversion` reduced damages, which hold consumption
    per person for each region (`reduce` has no `equity` branch). It
    takes the population-weighted certainty equivalent of that
    consumption across regions at `eta`, once with climate change and
    once without, and multiplies the difference by total population
    (dscim `menu/equity.py:14-35,59-73`). `risk_aversion` instead
    multiplies each region's difference by that region's population and
    sums them (`menu/risk_aversion.py:46-56`). Regions missing from the
    reduced damages are filled with their consumption without climate
    change, and `gwr` discounting adds `ssp` and `model` to the
    dimensions the certainty equivalent runs over.

Batch
:   The dimension of repeated damage draws in a sector's damage file.
    `reduce` collapses it; dscim requires it chunked at 15.

## Discounting

Discounting type
:   How future damages are converted to present value. `constant`,
    `constant_model_collapsed`, `naive_ramsey`, `euler_ramsey`,
    `naive_gwr`, `euler_gwr` and `gwr_gwr` are supported. The `gwr`
    types collapse the `ssp` and `model` dimensions.

eta
:   The curvature of the utility function: how fast the value of an
    extra unit of consumption falls as consumption rises. It is used by
    the `risk_aversion` reduction and by Ramsey discount factors.

rho
:   The pure rate of time preference: how much a future year is valued
    less than the present, apart from growth. It is used only by Ramsey
    and GWR discount factors, but it appears in every output file name.

Ramsey calibrations
:   EPA publishes three `eta` and `rho` pairs, labelled by the discount
    rate each is set to produce: 1.5% (`1.016010255`, `9.149608e-05`),
    2.0% (`1.244459066`, `0.00197263997`) and 2.5% (`1.421158116`,
    `0.00461878399`). A lower rate values the future more and gives a
    larger SCC.

## Climate and timing

Pulse year
:   The year in which the extra emission pulse is added. The SCC is the
    present value of the damages that pulse causes. The year must exist
    as a coordinate in the FaIR files.

FaIR
:   The climate model whose temperature and sea level projections the
    runs use. The files hold a control run and a pulse run for each
    pulse year.

ECS mask
:   A filter on the climate sensitivity of FaIR simulations. The option
    is catalogued as unsupported because masked runs crash inside dscim.

## Sectors

Sector
:   One category of climate damage with its own damage file: for
    example agriculture, mortality, energy, labor or coastal. Sector
    names are free strings in the config.

AMEL
:   The sum of agriculture, mortality, energy and labor. `sum-sectors`
    builds it from the member sectors' damage files.

CAMEL
:   AMEL plus coastal: the combined estimate across all five sectors.
    `combine` builds it by merging the coastal and AMEL damage-function
    coefficients. The version numbers in a name such as `CAMEL_m1_c0.20`
    are the mortality and coastal versions.

Damage function
:   A fitted curve from temperature, or sea level, to damages. The
    `formula` of a sector says which terms it has. Its coefficients are
    saved as `damage_function_coefficients` files.

Coefficient-only sector
:   A sector with a `damage_function_path` and no damage file. `run`
    loads its coefficients instead of fitting them. All RFF sectors are
    of this kind.

## Results

Uncollapsed outputs
:   The marginal damages and discount factors for every draw, saved
    before they are combined into an SCC. The `scc` command composes
    SCCs from them.

Certainty equivalent
:   The SCC reported by EPA. Each draw is weighted by
    `(consumption per capita at the pulse year) ** -eta`, scaled so the
    weights average one, and the weighted draws are averaged. Draws
    with high consumption get less weight than a plain mean gives them,
    and damages are larger in those draws, so the certainty equivalent
    comes out lower than the plain mean: by about 0.5% for pulse year
    2020, widening to about 30% for 2080 in the EPA run. Set it with
    `scc.collapse: certainty_equivalent`; it needs a `runid` dimension
    and `global_consumption_no_pulse` in `menu.save_files`.

Deflator
:   A factor that converts the SCC between price years. EPA's draws are
    in 2019 dollars, and `113.648 / 112.29` converts them to 2020
    dollars. It is explicit in the config; there is no built-in table.

Run metadata
:   The `*_run_metadata.yaml` beside every run's outputs: the resolved
    settings, where each came from, and the dscim version.

## The pipeline

The five commands that build an SCC, in the order they run:

`sum-sectors`
:   Adds the member sectors into an aggregate such as AMEL. SSP mode.

`reduce`
:   Collapses the batch dimension of each sector's damages against
    socioeconomics, once per recipe and eta. SSP mode.

`run`
:   Fits the damage function, or loads its coefficients, applies it to
    the FaIR projections, discounts, and writes the SCC files.

`combine`
:   Merges the coastal and AMEL coefficients into the CAMEL sector.
    SSP mode. A second `run` then uses the combined coefficients.

`scc`
:   Composes SCCs from the uncollapsed outputs of `run`, applies the
    deflator, and collapses the uncertainty dimension.

`dscim-cil stages` prints the same pipeline with what each stage reads,
writes, and collapses; see [the pipeline](pipeline.md).
