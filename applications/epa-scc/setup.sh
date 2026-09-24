#!/bin/sh
# Download the inputs for the EPA SC-CO2 run and prepare the coefficient
# files. Everything lands under one data directory, outside the
# repository. Set EPA_SCC_DATA to choose it.
set -eu

data="${EPA_SCC_DATA:-$HOME/dscim-epa-scc}"
here="$(cd "$(dirname "$0")" && pwd)"

echo "Data directory: $data"
mkdir -p "$data"
cd "$data"

if [ ! -d dscim-facts-epa ]; then
    echo "Cloning dscim-facts-epa into $data/dscim-facts-epa"
    git clone https://github.com/ClimateImpactLab/dscim-facts-epa.git
fi

if [ ! -d dscim-facts-epa/input ]; then
    echo "Downloading the input library (about 6 GB) with dscim-facts-epa's"
    echo "scripts/directory_setup.py. It fetches a zip from the Climate Impact"
    echo "Lab's public bucket and unpacks it to dscim-facts-epa/input."
    (cd dscim-facts-epa && python scripts/directory_setup.py)
else
    echo "dscim-facts-epa/input already exists, skipping the download"
fi

echo ""
echo "Preparing coefficient files in dfc_library/CAMEL_m1_c0.20."
echo "dscim reads a coefficient file whose name embeds eta and rho exactly as"
echo "the run requests them, for example:"
echo "  risk_aversion_euler_ramsey_eta1.016010255_rho9.149608e-05_damage_function_coefficients.nc4"
echo "The EPA library ships the same files under rounded names ending in"
echo "_dfc.nc4; the rounding is done inside dscim-facts-epa's own driver"
echo "(scghg_utils.py), which is not used here. Each link below gives a"
echo "shipped file the full-precision name dscim will look for. The files"
echo "themselves are not modified."

mkdir -p dfc_library/CAMEL_m1_c0.20

link_coefficients() {
    full="risk_aversion_euler_ramsey_eta${1}_rho${2}_damage_function_coefficients.nc4"
    rounded="risk_aversion_euler_ramsey_eta${3}_rho${4}_dfc.nc4"
    echo "  linking $full"
    echo "       to $rounded"
    ln -sf "../../dscim-facts-epa/input/damage_functions/CAMEL_m1_c0.20/$rounded" \
        "dfc_library/CAMEL_m1_c0.20/$full"
}

link_coefficients 1.016010255 9.149608e-05  1.016 0.0
link_coefficients 1.244459066 0.00197263997 1.244 0.002
link_coefficients 1.421158116 0.00461878399 1.421 0.005

cp "$here/config.yml" config.yml
echo ""
echo "Copied config.yml into $data. Its paths are relative, so run the"
echo "commands from that directory:"
echo "  cd $data"
echo "  dscim-cil validate config.yml"
echo "  dscim-cil run config.yml"
echo "  dscim-cil scc config.yml"
