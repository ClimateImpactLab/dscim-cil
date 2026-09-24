# EPA SC-CO2

The social cost of CO2 from the EPA/RFF pipeline: sector CAMEL_m1_c0.20
(the combined agriculture, coastal, energy, labor, and mortality
estimate, global scope) with the risk_aversion recipe and euler_ramsey
discounting, over seven pulse years (2020 to 2080 by decade) and EPA's
three published Ramsey calibrations (1.5%, 2.0%, 2.5%). 21 runs.
Inputs are dscim-facts-epa's published library.

## Requirements

- dscim-cil installed with the `run` extra (`uv pip install ".[run]"`).
- About 6 GB of disk for the input library, plus the run outputs.
- Roughly fifteen minutes of compute for the 21 runs.
- setup.sh needs git and a python that can import requests, tqdm, and
  yaml (directory_setup.py uses them).

## Setup

setup.sh puts everything under one data directory, outside the
repository. The default is `$HOME/dscim-epa-scc`; set EPA_SCC_DATA to
change it.

```shell
EPA_SCC_DATA=/somewhere/big ./setup.sh
```

It clones dscim-facts-epa, downloads the input library with that repo's
scripts/directory_setup.py, prepares the coefficient files (next
section), and copies config.yml into the data directory.

## The coefficient files

dscim reads damage-function coefficients from a file whose name embeds
eta and rho exactly as the run requests them, for example
`risk_aversion_euler_ramsey_eta1.016010255_rho9.149608e-05_damage_function_coefficients.nc4`.
The EPA library ships the same files under rounded names ending in
`_dfc.nc4`, such as `risk_aversion_euler_ramsey_eta1.016_rho0.0_dfc.nc4`;
the rounding is done inside dscim-facts-epa's own driver
(scghg_utils.py:257-270), which is not used here. setup.sh links each
shipped file to its full-precision name in dfc_library/CAMEL_m1_c0.20
and prints every link it makes. The files themselves are not modified.
If the links are missing, `dscim-cil validate` reports this exact
mismatch.

## Run

From the data directory, so the config's relative paths resolve:

```shell
cd "${EPA_SCC_DATA:-$HOME/dscim-epa-scc}"
dscim-cil validate config.yml
dscim-cil run config.yml
dscim-cil scc config.yml
```

`run` writes the uncollapsed outputs under results/. `scc` composes
them into one SC-CO2 per pulse year and discount rate under
results/scghgs, applying the 2019 to 2020 USD deflator
(113.648 / 112.29) and the certainty-equivalent collapse.

## Checking the numbers

expected.csv holds the certainty equivalents, in 2020 USD per metric
ton of CO2. Print yours from the data directory:

```shell
python -c 'import pathlib, xarray as xr
for p in sorted(pathlib.Path("results/scghgs").rglob("*_scghg.nc4")):
    print(p, float(xr.open_dataset(p)["scghg"].squeeze()))'
```

These values match dscim-facts-epa's own script for the same settings, and the 2030 values (386.8, 232.9,
140.1) round to the 390 / 230 / 140 published in EPA's 2023 SC-GHG
report (Table 3.1.1).
