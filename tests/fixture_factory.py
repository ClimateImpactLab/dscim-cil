"""Tiny synthetic dscim inputs for integration tests.

Follows dscim's own inline ``xr.Dataset`` fixture pattern: CE zarrs in
main's naming conventions, a 15-batch damages zarr chunked batch=15, an
econ zarr, a GMST csv, a FaIR nc, and rff-shaped variants with runid
and coefficient files carrying patsy-term variable names.

Damages are constructed as exact quadratics in the GMST anomaly so OLS
damage-function fits are well conditioned.
"""

import numpy as np
import pandas as pd
import xarray as xr

REGIONS = ["r1", "r2"]
SSPS = ["SSP2", "SSP3"]
MODELS = ["m1", "m2"]
GCMS = ["g1", "g2"]
RCPS = ["rcp45", "rcp85"]
GASES = ["CO2_Fossil"]
PULSE_YEAR = 2020
ECON_YEARS = np.arange(2010, 2100)
# FaIR files must span Climate's base_period (2001, 2010): temperatures
# are rebased against that window's mean (simple_storage.py
# gmst_anomalies), and an empty slice makes every anomaly NaN.
FAIR_YEARS = np.arange(2001, 2301)
ANOMALY_BASE = {
    ("g1", "rcp45"): 1.0,
    ("g1", "rcp85"): 2.0,
    ("g2", "rcp45"): 1.5,
    ("g2", "rcp85"): 3.0,
}
DAMAGE_COEF = 10.0
RUNIDS = [1, 2, 3]


def _anomaly(gcm: str, rcp: str, years: np.ndarray) -> np.ndarray:
    return ANOMALY_BASE[(gcm, rcp)] * (1.0 + 0.01 * (years - 2010))


# Distinct values per ssp and model; identical slices could not show
# a collapse or mix-up of those dimensions.
def _ssp_model_factor() -> "np.ndarray":
    ssp_factor = 1.0 + 0.10 * np.arange(len(SSPS))
    model_factor = 1.0 + 0.05 * np.arange(len(MODELS))
    return ssp_factor[:, None] * model_factor[None, :]


def write_econ(path) -> str:
    """Write the SSP econ zarr (gdp, pop over ssp/region/model/year)."""
    shape = (len(SSPS), len(REGIONS), len(MODELS), len(ECON_YEARS))
    growth = 1.02 ** (ECON_YEARS - 2010)
    factor = _ssp_model_factor()[:, None, :, None]
    gdp = np.broadcast_to(5.0e7 * growth, shape) * factor
    pop = np.full(shape, 1.0e3)
    ds = xr.Dataset(
        {
            "gdp": (("ssp", "region", "model", "year"), gdp),
            "pop": (("ssp", "region", "model", "year"), pop),
            # reduce_damages reads a precomputed, bottom-coded gdppc from
            # the socioeconomics file (production zarrs carry one).
            "gdppc": (("ssp", "region", "model", "year"), gdp / pop),
        },
        coords={
            "ssp": SSPS,
            "region": REGIONS,
            "model": MODELS,
            "year": ECON_YEARS,
        },
    )
    target = str(path / "econ.zarr")
    ds.to_zarr(target, mode="w")
    return target


def _consumption(years: np.ndarray) -> np.ndarray:
    return 5.0e4 * 1.02 ** (years - 2010)


def write_ce_zarrs(path, *, etas: tuple[float, ...]) -> str:
    """Write reduced-damage CE zarrs in both main naming conventions.

    ``adding_up_{cc,no_cc}.zarr`` (unsuffixed) and
    ``risk_aversion_{cc,no_cc}_eta{eta}.zarr`` per
    simple_storage.py:387,414 on dscim main.
    """
    dims = ("ssp", "region", "model", "year", "gcm", "rcp")
    coords = {
        "ssp": SSPS,
        "region": REGIONS,
        "model": MODELS,
        "year": ECON_YEARS,
        "gcm": GCMS,
        "rcp": RCPS,
    }
    shape = tuple(len(coords[d]) for d in dims)
    factor = _ssp_model_factor()[:, None, :, None, None, None]
    no_cc = (
        np.broadcast_to(
            _consumption(ECON_YEARS)[None, None, None, :, None, None], shape
        )
        * factor
    )
    cc = no_cc.copy()
    for gi, gcm in enumerate(GCMS):
        for ri, rcp in enumerate(RCPS):
            damage = DAMAGE_COEF * _anomaly(gcm, rcp, ECON_YEARS) ** 2
            cc[..., gi, ri] -= damage[None, None, None, :]

    library = path / "reduced"
    for sector_dir in (library / "labor",):
        sector_dir.mkdir(parents=True, exist_ok=True)
        for name, variable, data in (
            ("adding_up_cc.zarr", "cc", cc),
            ("adding_up_no_cc.zarr", "no_cc", no_cc),
        ):
            xr.Dataset({variable: (dims, data)}, coords=coords).to_zarr(
                str(sector_dir / name), mode="w"
            )
        for eta in etas:
            for reduction, data in (("cc", cc), ("no_cc", no_cc)):
                xr.Dataset({reduction: (dims, data)}, coords=coords).to_zarr(
                    str(sector_dir / f"risk_aversion_{reduction}_eta{eta}.zarr"),
                    mode="w",
                )
    return str(library)


def write_batch_damages(path) -> str:
    """Write a 15-batch sector damages zarr chunked batch=15.

    The batch chunksize-15 requirement is asserted by reduce_damages
    (preprocessing.py:96-98).
    """
    batches = [f"batch{i}" for i in range(15)]
    dims = ("batch", "ssp", "region", "model", "year", "gcm", "rcp")
    coords = {
        "batch": batches,
        "ssp": SSPS,
        "region": REGIONS,
        "model": MODELS,
        "year": ECON_YEARS,
        "gcm": GCMS,
        "rcp": RCPS,
    }
    shape = tuple(len(coords[d]) for d in dims)
    rng = np.random.default_rng(7)
    delta = np.abs(rng.normal(100.0, 5.0, shape))
    histclim = np.abs(rng.normal(90.0, 5.0, shape))
    ds = xr.Dataset(
        {"delta": (dims, delta), "histclim": (dims, histclim)},
        coords=coords,
    ).chunk({"batch": 15})
    target = str(path / "labor_damages.zarr")
    ds.to_zarr(target, mode="w")
    return target


def write_gmst_csv(path) -> str:
    """Write the fitting-stage GMST csv (gcm, rcp, year, temp)."""
    rows = []
    for gcm in GCMS:
        for rcp in RCPS:
            for year, temp in zip(
                ECON_YEARS, _anomaly(gcm, rcp, ECON_YEARS), strict=True
            ):
                rows.append((gcm, rcp, int(year), float(temp)))
    frame = pd.DataFrame(rows, columns=["gcm", "rcp", "year", "temp"])
    target = str(path / "gmst.csv")
    frame.to_csv(target, index=False)
    return target


def write_fair(path) -> str:
    """Write the FaIR temperature file (control/pulse, simulation dim)."""
    simulations = [0, 1]
    ramp = 1.0 + 2.0 * (FAIR_YEARS - 2001) / 300.0
    control = np.stack(
        [
            np.stack([ramp * (1.0 + 0.2 * ri + 0.05 * si) for si in simulations])
            for ri in range(len(RCPS))
        ]
    )[:, :, None, :]
    control = np.broadcast_to(
        control, (len(RCPS), len(simulations), len(GASES), len(FAIR_YEARS))
    )
    # The pulse starts at the pulse year; a constant offset over all
    # years would be removed exactly by the base-period rebasing.
    pulse = control + 0.01 * (FAIR_YEARS >= PULSE_YEAR)
    ds = xr.Dataset(
        {
            "control_temperature": (("rcp", "simulation", "gas", "year"), control),
            "pulse_temperature": (
                ("rcp", "simulation", "gas", "year", "pulse_year"),
                pulse[..., None],
            ),
            "medianparams_control_temperature": (
                ("rcp", "gas", "year"),
                control[:, 0, :, :],
            ),
            "medianparams_pulse_temperature": (
                ("rcp", "gas", "year", "pulse_year"),
                pulse[:, 0, :, :, None],
            ),
        },
        coords={
            "rcp": RCPS,
            "simulation": simulations,
            "gas": GASES,
            "year": FAIR_YEARS,
            "pulse_year": [PULSE_YEAR],
        },
    )
    target = str(path / "fair.nc")
    ds.to_netcdf(target)
    return target


def write_conversion(path) -> str:
    """Write the per-gas pulse conversion file.

    A factor of exactly 1.0 would make a dropped conversion invisible.
    """
    ds = xr.Dataset(
        {"conversion": (("gas",), np.full(len(GASES), 0.5))},
        coords={"gas": GASES},
    )
    target = str(path / "conversion.nc")
    ds.to_netcdf(target)
    return target


def write_rff_econ(path) -> str:
    """Write runid-shaped socioeconomics to 2300 (region 'world')."""
    years = np.arange(2020, 2301)
    shape = (1, len(RUNIDS), len(years))
    growth = 1.015 ** (years - 2020)
    gdp = np.broadcast_to(1.0e8 * growth, shape) * (
        1.0 + 0.05 * np.array(RUNIDS)[None, :, None]
    )
    pop = np.full(shape, 1.0e3)
    ds = xr.Dataset(
        {
            "gdp": (("region", "runid", "year"), gdp),
            "pop": (("region", "runid", "year"), pop),
        },
        coords={"region": ["world"], "runid": RUNIDS, "year": years},
    )
    target = str(path / "rff_econ.nc4")
    ds.to_netcdf(target)
    return target


def write_rff_fair(path) -> str:
    """Write runid-shaped FaIR temperatures (no rcp dimension)."""
    ramp = 1.0 + 2.5 * (FAIR_YEARS - 2001) / 300.0
    control = np.stack([ramp * (1.0 + 0.1 * r) for r in RUNIDS])[:, None, :]
    control = np.broadcast_to(control, (len(RUNIDS), len(GASES), len(FAIR_YEARS)))
    pulse = control + 0.01 * (FAIR_YEARS >= PULSE_YEAR)
    ds = xr.Dataset(
        {
            "control_temperature": (("runid", "gas", "year"), control),
            "pulse_temperature": (
                ("runid", "gas", "year", "pulse_year"),
                pulse[..., None],
            ),
        },
        coords={
            "runid": RUNIDS,
            "gas": GASES,
            "year": FAIR_YEARS,
            "pulse_year": [PULSE_YEAR],
        },
    )
    target = str(path / "rff_fair.nc4")
    ds.to_netcdf(target)
    return target


def write_rff_coefficients(
    path,
    *,
    recipe: str,
    discounting: str,
    eta: float,
    rho: float,
    naming: str = "dscim",
) -> str:
    """Write a damage-function coefficient nc4 with patsy-term variables.

    Variable names are the literal design-matrix terms dscim indexes
    (``anomaly``, ``np.power(anomaly, 2)``), on (runid, year) as in the
    shipped EPA files.
    """
    shape = (len(RUNIDS), len(FAIR_YEARS))
    # A mild year trend keeps the coefficients' year dependence visible.
    trend = 1.0 + 0.001 * (FAIR_YEARS - PULSE_YEAR)
    linear = np.broadcast_to(1.0e5 * trend, shape)
    quadratic = np.broadcast_to(2.0e4 * trend, shape)
    ds = xr.Dataset(
        {
            "anomaly": (("runid", "year"), linear),
            "np.power(anomaly, 2)": (("runid", "year"), quadratic),
        },
        coords={"runid": RUNIDS, "year": FAIR_YEARS},
    )
    directory = path / "dfs" / "CAMEL_test"
    directory.mkdir(parents=True, exist_ok=True)
    if naming == "epa":
        name = f"{recipe}_{discounting}_eta{round(eta, 3)}_rho{round(rho, 3)}_dfc.nc4"
    else:
        name = (
            f"{recipe}_{discounting}_eta{eta}_rho{rho}_damage_function_coefficients.nc4"
        )
    ds.to_netcdf(str(directory / name))
    return str(directory)


def ssp_fixture_config(path, *, etas: tuple[float, ...] = (2.0,)) -> dict:
    """Build a complete, runnable ssp-mode config over tiny fixtures.

    Parameters
    ----------
    path :
        Directory (pathlib.Path) to populate.
    etas :
        Etas for which risk_aversion CE zarrs are written.

    Returns
    -------
    dict
        A dscim-cil config ready for validate/expand/execute.
    """
    econ = write_econ(path)
    library = write_ce_zarrs(path, etas=etas)
    gmst = write_gmst_csv(path)
    fair = write_fair(path)
    conversion = write_conversion(path)
    results = path / "results"
    return {
        "mode": "ssp",
        "climate": {
            "gases": GASES,
            "gmst_path": gmst,
            "gmsl_path": "",
            "gmst_fair_path": fair,
            "damages_pulse_conversion_path": conversion,
            "emission_scenarios": RCPS,
        },
        "econ": {"path": econ},
        "paths": {
            "reduced_damages_library": library,
            "results": str(results),
        },
        "sectors": {
            "labor": {
                "sector_path": str(path / "labor_damages.zarr"),
                "histclim": "histclim",
                "delta": "delta",
                "formula": "damages ~ -1 + anomaly + np.power(anomaly, 2)",
            }
        },
        "menu": {
            "fair_aggregation": ["ce", "mean"],
            "weitzman_parameter": [0.1],
            "subset_dict": {"ssp": SSPS},
            "save_files": ["scc", "uncollapsed_sccs"],
        },
        "sweep": {
            "sectors": ["labor"],
            "pulse_years": [PULSE_YEAR],
            "menu_pairs": [{"recipe": "adding_up", "discounting": "euler_ramsey"}],
            "eta_rho": [[etas[0], 0.0001]],
        },
    }


def rff_fixture_config(
    path,
    *,
    recipe: str = "risk_aversion",
    discounting: str = "euler_ramsey",
    eta: float = 2.0,
    rho: float = 0.0001,
) -> dict:
    """Build a complete, runnable rff-mode config over tiny fixtures."""
    econ = write_rff_econ(path)
    fair = write_rff_fair(path)
    conversion = write_conversion(path)
    coefficients = write_rff_coefficients(
        path, recipe=recipe, discounting=discounting, eta=eta, rho=rho
    )
    return {
        "mode": "rff",
        "climate": {
            "gases": GASES,
            "gmst_path": "",
            "gmsl_path": "",
            "gmst_fair_path": fair,
            "damages_pulse_conversion_path": conversion,
            "emission_scenarios": None,
        },
        "econ": {"path": econ},
        "paths": {"results": str(path / "rff_results")},
        "sectors": {
            "CAMEL_test": {
                "formula": "damages ~ -1 + anomaly + np.power(anomaly, 2)",
                "damage_function_path": coefficients,
            }
        },
        "menu": {
            "fair_aggregation": [],
            "weitzman_parameter": [0.1],
            "subset_dict": {},
            "save_files": [
                "uncollapsed_sccs",
                "uncollapsed_marginal_damages",
                "uncollapsed_discount_factors",
            ],
        },
        "sweep": {
            "sectors": ["CAMEL_test"],
            "pulse_years": [PULSE_YEAR],
            "menu_pairs": [{"recipe": recipe, "discounting": discounting}],
            "eta_rho": [[eta, rho]],
        },
    }


def write_ssp_coefficients(
    results_root, *, sector, recipe, discounting, eta, rho, variables
):
    """Write a coefficient nc4 where a fit run would have saved one.

    Used to feed combine without running the fits first.
    """
    import pathlib

    directory = pathlib.Path(results_root) / sector / str(PULSE_YEAR) / "unmasked"
    directory.mkdir(parents=True, exist_ok=True)
    years = np.arange(PULSE_YEAR, 2301)
    trend = 1.0 + 0.001 * (years - PULSE_YEAR)
    ds = xr.Dataset(
        {name: (("year",), value * trend) for name, value in variables.items()},
        coords={"year": years},
    )
    target = (
        directory
        / f"{recipe}_{discounting}_eta{eta}_rho{rho}_damage_function_coefficients.nc4"
    )
    ds.to_netcdf(str(target))
    return str(target)


def write_short_fair(path) -> str:
    """Write a FaIR file that misses the base period (starts 2020).

    Reproduces the silent all-NaN trap the preflight guards against.
    """
    years = np.arange(2020, 2301)
    ramp = 1.0 + 2.5 * (years - 2020) / 280.0
    control = np.broadcast_to(
        np.stack([ramp * (1.0 + 0.1 * r) for r in RUNIDS])[:, None, :],
        (len(RUNIDS), len(GASES), len(years)),
    )
    ds = xr.Dataset(
        {
            "control_temperature": (("runid", "gas", "year"), control),
            "pulse_temperature": (
                ("runid", "gas", "year", "pulse_year"),
                (control + 0.01)[..., None],
            ),
        },
        coords={
            "runid": RUNIDS,
            "gas": GASES,
            "year": years,
            "pulse_year": [PULSE_YEAR],
        },
    )
    target = str(path / "short_fair.nc4")
    ds.to_netcdf(target)
    return target


def write_ecs_mask(path) -> str:
    """Write an ECS mask file with one variable, `keep_first`.

    Keeps the first FaIR simulation and drops the second, so applying
    the mask changes the result.
    """
    ds = xr.Dataset(
        {"keep_first": (("simulation",), np.array([True, False]))},
        coords={"simulation": [0, 1]},
    )
    target = str(path / "ecs_mask.nc4")
    ds.to_netcdf(target)
    return target
