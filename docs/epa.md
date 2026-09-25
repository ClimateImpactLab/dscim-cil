# Reproducing the EPA numbers

[applications/epa-scc](https://github.com/ClimateImpactLab/dscim-cil/tree/master/applications/epa-scc)
computes the social cost of CO2 from the EPA/RFF pipeline: sector
CAMEL_m1_c0.20 (the combined agriculture, coastal, energy, labor, and
mortality estimate, global scope) with the risk_aversion recipe and
euler_ramsey discounting, over seven pulse years (2020 to 2080 by
decade) and EPA's three published Ramsey calibrations (1.5%, 2.0%,
2.5%). 21 runs. Inputs are dscim-facts-epa's published library, about
6 GB; the 21 runs take roughly fifteen minutes.

The directory holds four files:

- `setup.sh` downloads the input library with dscim-facts-epa's own
  `directory_setup.py` and prepares the damage-function coefficient
  files under one data directory (set `EPA_SCC_DATA`; the default is
  `$HOME/dscim-epa-scc`).
- `config.yml` is the sweep config, with paths relative to that data
  directory.
- `expected.csv` holds the 21 certainty equivalents, in 2020 USD per
  metric ton of CO2.
- `README.md` walks through the run and the check.

The one preparation step that needs explaining: dscim reads
damage-function coefficients from a file whose name embeds eta and rho
exactly as the run requests them, while the EPA library ships the same
files under rounded names ending in `_dfc.nc4` (the rounding is done
inside dscim-facts-epa's own driver, scghg_utils.py:257-270, which is
not in the loop here). setup.sh links each shipped file to its
full-precision name and prints every link it makes; the files
themselves are not modified.

To run:

```shell
./applications/epa-scc/setup.sh
cd "${EPA_SCC_DATA:-$HOME/dscim-epa-scc}"
dscim-cil validate config.yml
dscim-cil run config.yml
dscim-cil scc config.yml
```

The composed values match dscim-facts-epa's own script for the same
settings, and the 2030 values (386.8, 232.9, 140.1) round to the
390 / 230 / 140 published in EPA's 2023 SC-GHG report (Table 3.1.1).
