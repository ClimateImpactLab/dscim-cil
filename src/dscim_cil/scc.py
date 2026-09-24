"""Compose SCCs from uncollapsed run outputs.

The SCC is the year-summed product of uncollapsed marginal damages and
discount factors, deflated and collapsed over the uncertainty
dimension. ``scc.damages_from`` and ``scc.discounting_from`` may point
at different result roots, e.g. territorial-US damages against global
discounting. Needs xarray but not dscim.
"""

import os

import xarray as xr

from dscim_cil.config import Run, expand_sweep, save_path_for

__all__ = ["compose"]


def _only_var(dataset: xr.Dataset) -> xr.DataArray:
    names = list(dataset.data_vars)
    return dataset[names[0]]


def _run_file(root: str, config: dict, run: Run, artifact: str) -> str:
    base = save_path_for({**config, "paths": {"results": root}}, run)
    stem = f"{run.recipe}_{run.discounting}_eta{run.eta}_rho{run.rho}"
    return os.path.join(base, f"{stem}_{artifact}.nc4")


def _collapse_dim(data: xr.DataArray) -> str | None:
    for candidate in ("runid", "simulation"):
        if candidate in data.dims:
            return candidate
    return None


def compose(config: dict, runs: list[Run] | None = None) -> list[str]:
    """Compose, deflate, and collapse SCCs for every run.

    Returns one status line per run, naming the file written. Raises
    FileNotFoundError when a run output is missing and ValueError when
    the collapse cannot be applied to the data.
    """
    scc_config = config["scc"]
    if runs is None:
        runs = expand_sweep(config)
    results = config["paths"]["results"]
    damages_root = scc_config.get("damages_from") or results
    discounting_root = scc_config.get("discounting_from") or results
    deflator = scc_config.get("deflator", 1.0)
    collapse = scc_config.get("collapse", "none")
    output_root = scc_config["output"]

    lines = []
    for run in runs:
        damages_file = _run_file(
            damages_root, config, run, "uncollapsed_marginal_damages"
        )
        factors_file = _run_file(
            discounting_root, config, run, "uncollapsed_discount_factors"
        )
        for path in (damages_file, factors_file):
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"{path} is missing; run `dscim-cil run` (with "
                    f"uncollapsed_marginal_damages and "
                    f"uncollapsed_discount_factors in save_files) first"
                )
        damages = _only_var(xr.open_dataset(damages_file))
        factors = _only_var(xr.open_dataset(factors_file))
        scc = (damages * factors).sum("year") * deflator

        if collapse == "mean":
            dim = _collapse_dim(scc)
            if dim is None:
                raise ValueError(
                    f"scc.collapse mean found no uncertainty dimension "
                    f"(runid or simulation) in {damages_file}; dims: "
                    f"{list(scc.dims)}"
                )
            scc = scc.mean(dim)
        elif collapse == "certainty_equivalent":
            scc = _certainty_equivalent(config, run, scc)

        base = save_path_for({**config, "paths": {"results": output_root}}, run)
        os.makedirs(base, exist_ok=True)
        stem = f"{run.recipe}_{run.discounting}_eta{run.eta}_rho{run.rho}"
        target = os.path.join(base, f"{stem}_scghg.nc4")
        scc.to_dataset(name="scghg").to_netcdf(target)
        lines.append(f"completed: {target}")
    return lines


def _certainty_equivalent(config: dict, run: Run, scc: xr.DataArray) -> xr.DataArray:
    """Collapse runid with the consumption-adjusted mean.

    Weights each draw by ``(gcnp / pop) ** -eta`` at the pulse year,
    normalized to mean one, then averages
    (dscim-facts-epa scghg_utils.py:352-357).
    """
    if "runid" not in scc.dims:
        raise ValueError(
            "scc.collapse certainty_equivalent follows the EPA rff formula "
            "and needs a runid dimension; use collapse: mean for "
            "simulation-based runs"
        )
    gcnp_file = _run_file(
        config["paths"]["results"], config, run, "global_consumption_no_pulse"
    )
    if not os.path.exists(gcnp_file):
        raise FileNotFoundError(
            f"{gcnp_file} is missing; certainty_equivalent needs "
            f"global_consumption_no_pulse in menu.save_files"
        )
    gcnp = _only_var(xr.open_dataset(gcnp_file))

    econ_path = config["econ"]["path"]
    econ = (
        xr.open_zarr(econ_path)
        if econ_path.endswith("arr")
        else xr.open_dataset(econ_path)
    )
    pop = econ["pop"].sel(year=run.pulse_year).sum("region")

    consumption_pc = (gcnp / pop).sel(year=run.pulse_year)
    weight = consumption_pc ** (-run.eta)
    adjustment = weight / weight.mean("runid")
    return (adjustment * scc).mean("runid")
