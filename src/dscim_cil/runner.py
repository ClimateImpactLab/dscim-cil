"""Execute planned runs against dscim.

Builds recipe kwargs the way dscim's drivers do (utils/menu_runs.py),
preflights input files, runs ``order_plate``, and writes
``*_run_metadata.yaml`` beside each run's outputs.
"""

import contextlib
import datetime
import importlib.metadata
import itertools
import logging
import os
import re
import tempfile
import warnings

import dscim.menu.baseline
import dscim.menu.equity
import dscim.menu.risk_aversion
import numpy as np
import pandas as pd
import xarray as xr
import yaml
from dscim.menu.main_recipe import MainRecipe
from dscim.menu.simple_storage import Climate, EconVars

from dscim_cil.config import (
    Run,
    _coefficient_file,
    config_provenance,
    epa_coefficient_file,
    expand_sweep,
    resolved_config,
    run_outputs,
    save_path_for,
)

__all__ = [
    "TESTED_DSCIM_COMMIT",
    "PreflightError",
    "build_kwargs",
    "combine_all",
    "execute",
    "preflight",
    "reduce_all",
    "sum_sectors",
]

# The dscim main commit the test suite runs against.
TESTED_DSCIM_COMMIT = "6a1f4d7e"

logger = logging.getLogger(__name__)

MENU = {
    "adding_up": dscim.menu.baseline.Baseline,
    "risk_aversion": dscim.menu.risk_aversion.RiskAversionRecipe,
    "equity": dscim.menu.equity.EquityRecipe,
}


def _warn_if_untested(installed_version: str) -> None:
    commit = _dscim_commit(installed_version)
    tested = TESTED_DSCIM_COMMIT
    if commit == "unknown" or not (
        commit.startswith(tested) or tested.startswith(commit)
    ):
        warnings.warn(
            f"installed dscim {installed_version} is not the version "
            f"dscim-cil is tested against (main @ {tested}); runs will "
            f"proceed and run metadata records the actual version",
            stacklevel=2,
        )


_MENU_PASSTHROUGH = (
    "fit_type",
    "discrete_discounting",
    "fair_aggregation",
    "weitzman_parameter",
    "ext_method",
    "ext_subset_start_year",
    "ext_subset_end_year",
    "ext_end_year",
    "clip_gmsl",
    "scenario_dimensions",
    "save_files",
    "filename_suffix",
    "full_uncertainty_quantiles",
    "quantreg_quantiles",
    "quantreg_weights",
)

_DEPENDENCIES = ("dscim", "xarray", "numpy", "pandas", "dask", "zarr", "statsmodels")


class PreflightError(Exception):
    """Input-file check failure; ``errors`` lists every message."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def _open_econ(path: str) -> xr.Dataset:
    # EconVars dispatches on the path suffix the same way
    # (simple_storage.py econ_vars: ``path[-3:] == "arr"``).
    if path.endswith("arr"):
        return xr.open_zarr(path)
    return xr.open_dataset(path)


def preflight(config: dict, runs: list[Run]) -> None:
    """Check input files before any compute.

    Raises PreflightError listing every failure: econ variables and
    year range for the declared mode, pulse_year and gas coordinates in
    the FaIR file, FaIR coverage of base_period through ext_end_year
    (an uncovered base period yields all-NaN results with no error),
    GMST coverage of the fit window, discounting membership in the
    installed dscim's DISCOUNT_TYPES, and reduced-damage naming.
    """
    errors: list[str] = []
    mode = config["mode"]

    econ_path = config["econ"]["path"]
    try:
        econ = _open_econ(econ_path)
    except (OSError, ValueError) as error:
        raise PreflightError([f"cannot open econ file {econ_path}: {error}"]) from error
    for variable in ("gdp", "pop"):
        if variable not in econ.data_vars:
            errors.append(
                f"econ file {econ_path} lacks variable {variable!r}; EconVars "
                f"requires gdp and pop (simple_storage.py econ_vars)"
            )
    has_2300 = 2300 in econ.year
    if mode == "rff":
        if "runid" not in econ.dims:
            errors.append(
                f"mode: rff but econ file {econ_path} has no runid dimension "
                f"(rff uncertainty is indexed by runid)"
            )
        if not has_2300:
            errors.append(
                f"mode: rff but econ years end before 2300 in {econ_path}; "
                f"dscim only skips extrapolation when 2300 is present "
                f"(main_recipe.py global_consumption)"
            )
    elif has_2300:
        errors.append(
            f"mode: ssp but econ file {econ_path} extends to 2300, which "
            f"dscim treats as rff data and skips extrapolation "
            f"(main_recipe.py global_consumption); declare mode: rff or "
            f"supply ssp-range socioeconomics"
        )

    fair_path = config["climate"]["gmst_fair_path"]
    try:
        fair = xr.open_dataset(fair_path)
    except (OSError, ValueError) as error:
        raise PreflightError([f"cannot open FaIR file {fair_path}: {error}"]) from error
    wanted_years = sorted({run.pulse_year for run in runs})
    if "pulse_year" in fair.dims:
        available = set(np.asarray(fair.pulse_year.values).tolist())
        for year in wanted_years:
            if year not in available:
                errors.append(
                    f"pulse year {year} is not a pulse_year coordinate of "
                    f"{fair_path} (available: {sorted(available)}); "
                    f"Climate.anomalies selects on it"
                )
    if "gas" in fair.dims:
        available_gases = {str(g) for g in fair.gas.values}
        for gas in config["climate"].get("gases") or []:
            if gas not in available_gases:
                errors.append(
                    f"gas {gas!r} is not a gas coordinate of {fair_path} "
                    f"(available: {sorted(available_gases)})"
                )

    menu = config.get("menu", {})
    base_period = config["climate"].get("base_period") or (2001, 2010)
    horizon = menu.get("ext_end_year", 2300)
    fair_years = (int(fair.year.min()), int(fair.year.max()))
    if fair_years[0] > base_period[0] or fair_years[1] < horizon:
        errors.append(
            f"FaIR file {fair_path} covers years "
            f"{fair_years[0]}-{fair_years[1]} but "
            f"{base_period[0]}-{horizon} is required: temperatures are "
            f"rebased against the {base_period[0]}-{base_period[1]} mean "
            f"(an uncovered base period yields all-NaN results with no "
            f"error) and discounting integrates to {horizon}"
        )

    fit_runs = [
        run
        for run in runs
        if "damage_function_path" not in config["sectors"][run.sector]
    ]
    if mode == "ssp" and fit_runs:
        gmst_path = config["climate"].get("gmst_path")
        fit_start = min(run.pulse_year for run in fit_runs) - 2
        fit_end = menu.get("ext_subset_end_year", 2099)
        try:
            gmst_years = pd.read_csv(gmst_path)["year"]
        except (OSError, ValueError, KeyError) as error:
            errors.append(f"cannot read years from GMST csv {gmst_path}: {error}")
        else:
            span = (int(gmst_years.min()), int(gmst_years.max()))
            if span[0] > fit_start or span[1] < fit_end:
                errors.append(
                    f"GMST csv {gmst_path} covers years {span[0]}-{span[1]} "
                    f"but the damage-function fit needs {fit_start}-{fit_end} "
                    f"(pulse year minus 2 through ext_subset_end_year)"
                )

    coefficient_runs = [
        run for run in runs if "damage_function_path" in config["sectors"][run.sector]
    ]
    for run in coefficient_runs:
        directory = config["sectors"][run.sector]["damage_function_path"]
        dscim_file = _coefficient_file(directory, run)
        if os.path.exists(dscim_file):
            continue
        epa_file = epa_coefficient_file(directory, run)
        if os.path.exists(epa_file):
            errors.append(
                f"{directory} holds {os.path.basename(epa_file)} but dscim "
                f"main reads full-precision names and will look for "
                f"{os.path.basename(dscim_file)}; EPA's published library "
                f"uses rounded _dfc.nc4 names. Rename the files (or teach "
                f"dscim to read both) before running"
            )
        else:
            errors.append(
                f"no coefficient file for {run.sector} "
                f"{run.recipe}/{run.discounting} eta={run.eta} rho={run.rho}: "
                f"tried {os.path.basename(dscim_file)} and the EPA name "
                f"{os.path.basename(epa_file)} in {directory}"
            )

    for run in runs:
        if run.discounting not in MainRecipe.DISCOUNT_TYPES:
            errors.append(
                f"discounting {run.discounting!r} is not implemented by the "
                f"installed dscim "
                f"({importlib.metadata.version('dscim')}); its "
                f"DISCOUNT_TYPES: {list(MainRecipe.DISCOUNT_TYPES)}"
            )

    if mode == "ssp":
        library = config.get("paths", {}).get("reduced_damages_library", "")
        for run in fit_runs:
            if run.recipe != "adding_up":
                continue
            sector_dir = os.path.join(library, run.sector)
            plain = os.path.join(sector_dir, "adding_up_cc.zarr")
            suffixed = os.path.join(sector_dir, f"adding_up_cc_eta{run.eta}.zarr")
            if not os.path.exists(plain) and os.path.exists(suffixed):
                errors.append(
                    f"{sector_dir} holds eta-suffixed adding_up zarrs "
                    f"({os.path.basename(suffixed)}), the convention of "
                    f"dscim's harmonize branch; the installed dscim reads "
                    f"adding_up_cc.zarr (simple_storage.py:387); re-reduce "
                    f"with this dscim or rename the files"
                )

    if errors:
        raise PreflightError(errors)


def build_kwargs(config: dict, run: Run) -> dict:
    """Build the recipe constructor kwargs for one run.

    Mirrors ``run_ssps`` (utils/menu_runs.py:77-99) and ``run_rff``
    (:157-171). ``subset_dict`` defaults to an empty mapping because
    ``StackedDamages.cut`` iterates it unguarded.
    """
    climate_config = dict(config["climate"])
    menu = config.get("menu", {})
    block = config["sectors"][run.sector]
    mode = config["mode"]

    factors = climate_config.pop("gas_conversions", None)
    if factors is not None:
        climate_config["damages_pulse_conversion_path"] = _write_gas_conversions(
            factors, config["paths"]["results"]
        )
    climate_kwargs = dict(climate_config, pulse_year=run.pulse_year)
    if mode == "ssp":
        climate_kwargs["ecs_mask_name"] = run.mask
    else:
        climate_kwargs["ecs_mask_path"] = None

    kwargs: dict = {
        "econ_vars": EconVars(path_econ=config["econ"]["path"]),
        "climate_vars": Climate(**climate_kwargs),
        "formula": block["formula"],
        "discounting_type": run.discounting,
        "sector": run.sector,
        "save_path": save_path_for(config, run),
        "eta": run.eta,
        "rho": run.rho,
        "subset_dict": menu.get("subset_dict") or {},
    }
    if mode == "ssp":
        kwargs["fair_dims"] = list(run.fair_dims)

    if "damage_function_path" in block:
        kwargs["ce_path"] = None
        kwargs["damage_function_path"] = block["damage_function_path"]
    else:
        kwargs["ce_path"] = os.path.join(
            config["paths"]["reduced_damages_library"], run.sector
        )

    for key in _MENU_PASSTHROUGH:
        if key in menu and key != "subset_dict":
            kwargs[key] = menu[key]
    return kwargs


def _write_gas_conversions(factors: dict, results_root: str) -> str:
    """Write the conversion netCDF dscim reads from inline factors.

    The file lives beside the run outputs so it can be inspected after
    the run.
    """
    gases = list(factors)
    ds = xr.Dataset(
        {"conversion": (("gas",), np.array([factors[g] for g in gases], dtype=float))},
        coords={"gas": gases},
    )
    target = os.path.join(results_root, "gas_conversions.nc4")
    os.makedirs(results_root, exist_ok=True)
    ds.to_netcdf(target)
    return target


def _dscim_commit(version: str) -> str:
    match = re.search(r"\+g([0-9a-f]+)", version)
    return match.group(1) if match else "unknown"


def _versions() -> dict:
    versions = {}
    for name in _DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return versions


def _write_metadata(
    config: dict,
    run: Run,
    *,
    invocation: str,
    started: str,
    finished: str,
    outputs: list[str],
    sources: dict[str, str] | None = None,
) -> str:
    dscim_version = _versions().get("dscim", "not installed")
    record = {
        "run": {
            "sector": run.sector,
            "pulse_year": run.pulse_year,
            "recipe": run.recipe,
            "discounting": run.discounting,
            "eta": run.eta,
            "rho": run.rho,
            "mask": run.mask,
            "fair_dims": list(run.fair_dims),
        },
        "resolved_config": resolved_config(config),
        "provenance": config_provenance(config, sources=sources),
        "started": started,
        "finished": finished,
        "invocation": invocation,
        "dscim_cil_version": _versions().get("dscim-cil", "not installed"),
        "dscim_version": dscim_version,
        "dscim_commit": _dscim_commit(dscim_version),
        "dependencies": _versions(),
        "outputs": [path for path in outputs if os.path.exists(path)],
    }
    stem = f"{run.recipe}_{run.discounting}_eta{run.eta}_rho{run.rho}"
    target = os.path.join(save_path_for(config, run), f"{stem}_run_metadata.yaml")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as stream:
        yaml.safe_dump(record, stream, sort_keys=False)
    return target


def execute(
    config: dict,
    runs: list[Run] | None = None,
    *,
    resume: bool = False,
    invocation: str = "",
    sources: dict[str, str] | None = None,
) -> list[str]:
    """Execute runs and write metadata beside their outputs.

    With ``resume``, runs whose declared outputs all exist are skipped.
    Returns one status line per run.
    """
    if runs is None:
        runs = expand_sweep(config)
    preflight(config, runs)

    order = config.get("order", "scc")
    lines = []
    for run in runs:
        outputs = run_outputs(config, run)
        label = (
            f"{run.sector} {run.pulse_year} {run.recipe}/{run.discounting} "
            f"eta={run.eta} rho={run.rho}"
        )
        if resume and outputs and all(os.path.exists(p) for p in outputs):
            lines.append(f"skipped (outputs exist): {label}")
            continue
        started = datetime.datetime.now(datetime.UTC).isoformat()
        kwargs = build_kwargs(config, run)
        os.makedirs(kwargs["save_path"], exist_ok=True)
        menu_item = MENU[run.recipe](**kwargs)
        logger.info("running %s", label)
        menu_item.order_plate(order)
        finished = datetime.datetime.now(datetime.UTC).isoformat()
        metadata = _write_metadata(
            config,
            run,
            invocation=invocation,
            started=started,
            finished=finished,
            outputs=outputs,
            sources=sources,
        )
        lines.append(f"completed: {label} (metadata: {metadata})")
    return lines


def _config_file(config: dict) -> str:
    """Write the merged config to a file.

    ``sum_AMEL`` and ``reduce_damages`` take a config path and re-read
    it from disk, so overrides must be written out to reach them.
    """
    descriptor, name = tempfile.mkstemp(suffix=".yaml", prefix="dscim-cil-")
    with os.fdopen(descriptor, "w") as handle:
        yaml.safe_dump(config, handle)
    return name


def sum_sectors(config: dict) -> list[str]:
    """Build every aggregate sector declared in the aggregates block."""
    from dscim.preprocessing.preprocessing import sum_AMEL

    aggregates = config.get("aggregates") or {}
    if not aggregates:
        return ["nothing to do: config has no aggregates block"]
    config_path = _config_file(config)
    lines = []
    for name, members in aggregates.items():
        sum_AMEL(sectors=list(members), config=config_path, AMEL=name)
        target = config["sectors"][name]["sector_path"]
        lines.append(f"completed: {name} from {', '.join(members)} -> {target}")
    return lines


def reduce_all(config: dict) -> list[str]:
    """Run reduce_damages for the swept fit sectors.

    adding_up takes ``eta=None`` (dscim asserts it,
    preprocessing.py:85-88); risk_aversion runs once per swept eta.
    """
    from dscim.preprocessing.preprocessing import reduce_damages

    reduce_block = config.get("reduce") or {}
    if not reduce_block:
        return ["nothing to do: config has no reduce block"]
    config_path = _config_file(config)
    socioec = config["econ"]["path"]
    if "gdppc" not in _open_econ(socioec).data_vars:
        raise PreflightError(
            [
                (
                    f"econ file {socioec} has no gdppc variable; "
                    f"reduce_damages reads a precomputed, bottom-coded "
                    f"gdppc from the socioeconomics file (preprocessing.py "
                    f"ce_from_chunk), unlike the menu runs which use gdp "
                    f"and pop"
                )
            ]
        )
    sectors = [
        name
        for name in config["sweep"]["sectors"]
        if "damage_function_path" not in config["sectors"][name]
    ]
    etas = sorted({pair[0] for pair in config["sweep"]["eta_rho"]})
    library = config["paths"]["reduced_damages_library"]

    lines = []
    for sector, reduction, recipe in itertools.product(
        sectors, reduce_block.get("reductions", []), reduce_block.get("recipes", [])
    ):
        recipe_etas = [None] if recipe == "adding_up" else etas
        for eta in recipe_etas:
            reduce_damages(
                recipe=recipe,
                reduction=reduction,
                eta=eta,
                sector=sector,
                config=config_path,
                socioec=socioec,
            )
            suffix = "" if eta is None else f"_eta{eta}"
            lines.append(
                f"completed: {library}/{sector}/{recipe}_{reduction}{suffix}.zarr"
            )
    return lines


def combine_all(config: dict) -> list[str]:
    """Merge coastal and AMEL coefficients per the combine block.

    dscim never merges the fitted-values files: combine_CAMEL_coefs
    rebinds its ``fit`` parameter before testing it
    (midprocessing.py), so only coefficients are combined.
    """
    from dscim.preprocessing.midprocessing import combine_CAMEL_coefs

    combine = config["combine"]
    sweep = config["sweep"]
    results = config["paths"]["results"]
    lines = []
    for pair, eta_rho, pulse_year, mask in itertools.product(
        sweep["menu_pairs"],
        sweep["eta_rho"],
        sweep["pulse_years"],
        sweep.get("masks", [None]),
    ):
        combine_CAMEL_coefs(
            recipe=pair["recipe"],
            disc=pair["discounting"],
            eta=eta_rho[0],
            rho=eta_rho[1],
            CAMEL=combine["target"],
            coastal=combine["coastal"],
            AMEL=combine["amel"],
            input_dir=results,
            mask=mask or "unmasked",
            pulse_year=pulse_year,
        )
        lines.append(
            f"completed: {combine['target']} {pair['recipe']}/"
            f"{pair['discounting']} eta={eta_rho[0]} rho={eta_rho[1]} "
            f"pulse_year={pulse_year}"
        )
    return lines


with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    _warn_if_untested(importlib.metadata.version("dscim"))
