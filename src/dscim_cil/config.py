"""Config loading, validation, sweep expansion, and pipeline planning.

Precedence: catalogue defaults < YAML < command flags < ``-c``
overrides.
"""

import difflib
import itertools
import os
from dataclasses import dataclass
from typing import Any

import yaml

from dscim_cil.options import (
    CATALOGUE,
    COMPATIBILITY,
    DEFAULT_SAVE_FILES,
    DISCOUNT_TYPES,
    EXTRA_SAVE_FILES,
    FAIR_AGGREGATIONS,
    FORMULAS,
    RECIPES,
    REDUCTIONS,
    REQUIRED,
)

__all__ = [
    "COMBINATION_CHECKERS",
    "ConfigError",
    "Input",
    "PlanStep",
    "Run",
    "apply_overrides",
    "apply_selectors",
    "config_provenance",
    "effective_settings",
    "expand_sweep",
    "load_config",
    "plan_steps",
    "render_plan",
    "render_summary",
    "resolved_config",
    "run_inputs",
    "run_outputs",
    "save_path_for",
    "settings_summary",
    "summary_data",
    "validate_config",
]

TOP_LEVEL_KEYS = (
    "mode",
    "climate",
    "econ",
    "paths",
    "aggregates",
    "sectors",
    "menu",
    "sweep",
    "reduce",
    "combine",
    "scc",
)

MENU_KEYS = (
    "fit_type",
    "discrete_discounting",
    "fair_aggregation",
    "weitzman_parameter",
    "subset_dict",
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

CLIMATE_KEYS = (
    "gases",
    "gas_conversions",
    "gmst_path",
    "gmsl_path",
    "gmst_fair_path",
    "gmsl_fair_path",
    "damages_pulse_conversion_path",
    "ecs_mask_path",
    "emission_scenarios",
    "base_period",
)

SAVABLE = DEFAULT_SAVE_FILES + EXTRA_SAVE_FILES

SCC_COLLAPSES = ("certainty_equivalent", "mean", "none")

EXTERNAL = ""


class ConfigError(Exception):
    """Validation failure; ``errors`` lists every message."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class Run:
    """One fully-resolved element of the sweep.

    ``mask`` and ``fair_dims`` apply in ssp mode only.
    """

    sector: str
    pulse_year: int
    recipe: str
    discounting: str
    eta: float
    rho: float
    mask: str | None = None
    fair_dims: tuple[str, ...] = ("simulation",)


@dataclass(frozen=True)
class Input:
    """One input file, with the dscim-cil command that produces it.

    ``producer`` is empty for external inputs the user supplies.
    """

    path: str
    kind: str
    producer: str = EXTERNAL


@dataclass(frozen=True)
class PlanStep:
    """One ordered step of the pipeline for a given config."""

    name: str
    title: str
    inputs: tuple[Input, ...]
    outputs: tuple[str, ...]

    def status(self) -> str:
        """Return outputs-present, ready, or blocked-by-N."""
        if self.outputs and all(os.path.exists(p) for p in self.outputs):
            return "outputs-present"
        missing = sum(1 for i in self.inputs if not os.path.exists(i.path))
        return "ready" if missing == 0 else f"blocked-by-{missing}"


def load_config(path: str) -> dict:
    """Load a YAML config file.

    Raises ConfigError if the file is missing or is not a mapping.
    """
    if not os.path.exists(path):
        raise ConfigError([f"config file not found: {path}"])
    with open(path) as stream:
        loaded = yaml.safe_load(stream)
    if not isinstance(loaded, dict):
        raise ConfigError(
            [f"config must be a YAML mapping, got {type(loaded).__name__}"]
        )
    return loaded


def apply_overrides(config: dict, *, overrides: list[str]) -> dict:
    """Apply ``KEY=VALUE`` overrides, merged last.

    Keys are dotted paths; values are parsed as YAML scalars so lists
    and nulls work (``-c sweep.pulse_years=[2020]``).
    """
    result = _deep_copy(config)
    errors = []
    for raw in overrides:
        key, sep, value = raw.partition("=")
        if not sep or not key:
            errors.append(f"override must be KEY=VALUE, got: {raw!r}")
            continue
        target = result
        parts = key.split(".")
        for part in parts[:-1]:
            node = target.setdefault(part, {})
            if not isinstance(node, dict):
                target[part] = node = {}
            target = node
        target[parts[-1]] = yaml.safe_load(value)
    if errors:
        raise ConfigError(errors)
    return result


def apply_selectors(
    config: dict,
    *,
    sectors: tuple[str, ...] = (),
    pulse_years: tuple[int, ...] = (),
    recipes: tuple[str, ...] = (),
    discountings: tuple[str, ...] = (),
    masks: tuple[str, ...] = (),
    eta: float | None = None,
    rho: float | None = None,
) -> dict:
    """Narrow (or, where absent, define) the config's sweep from flags.

    A selector filters an axis the config sweeps (selecting outside it
    is an error) and defines an axis the config omits. The mask value
    ``unmasked`` selects the no-mask run; eta and rho must come
    together.
    """
    result = _deep_copy(config)
    sweep = result.setdefault("sweep", {})
    errors: list[str] = []

    def narrow(axis: str, wanted: list) -> None:
        if not wanted:
            return
        if axis in sweep:
            kept = [v for v in sweep[axis] if v in wanted]
            if not kept:
                errors.append(
                    f"--{axis.replace('_', '-')} selection {wanted} matches "
                    f"nothing in the configured sweep {sweep[axis]}"
                )
            else:
                sweep[axis] = kept
        else:
            sweep[axis] = wanted

    narrow("sectors", list(sectors))
    narrow("pulse_years", list(pulse_years))
    narrow(
        "masks",
        [None if m == "unmasked" else m for m in masks],
    )

    if recipes or discountings:
        pairs = sweep.get("menu_pairs")
        if pairs:
            kept = [
                p
                for p in pairs
                if (not recipes or p.get("recipe") in recipes)
                and (not discountings or p.get("discounting") in discountings)
            ]
            if not kept:
                errors.append(
                    f"--recipe/--discounting selection matches no configured "
                    f"menu pair in {pairs}"
                )
            else:
                sweep["menu_pairs"] = kept
        elif recipes and discountings:
            sweep["menu_pairs"] = [
                {"recipe": r, "discounting": d}
                for r, d in itertools.product(recipes, discountings)
            ]
        else:
            errors.append(
                "a config without sweep.menu_pairs needs both --recipe and "
                "--discounting to define the pair"
            )

    if (eta is None) != (rho is None):
        errors.append("--eta and --rho must be given together")
    elif eta is not None:
        pairs = sweep.get("eta_rho")
        if pairs:
            kept = [p for p in pairs if p[0] == eta and p[1] == rho]
            if not kept:
                errors.append(
                    f"--eta/--rho [{eta}, {rho}] is not in the configured sweep {pairs}"
                )
            else:
                sweep["eta_rho"] = kept
        else:
            sweep["eta_rho"] = [[eta, rho]]

    if errors:
        raise ConfigError(errors)
    return result


def _deep_copy(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _deep_copy(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_deep_copy(v) for v in node]
    return node


def _suggest(name: str, candidates: tuple[str, ...] | list[str]) -> str:
    close = difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)
    return f" (did you mean {close[0]!r}?)" if close else ""


def _unsupported(
    errors: list[str], warnings: list[str], *, allow: bool, message: str
) -> None:
    if allow:
        warnings.append(f"proceeding despite unsupported setting: {message}")
    else:
        errors.append(message + " Pass --allow-unsupported to proceed anyway.")


# Compatibility checkers, one per options.COMPATIBILITY entry, keyed
# alike. Each returns an error string or None.


def _check_median_params_fair_dims(config: dict) -> str | None:
    aggregations = _menu(config).get("fair_aggregation", list(FAIR_AGGREGATIONS))
    if "median_params" not in aggregations:
        return None
    for dims in config.get("sweep", {}).get("fair_dims", [["simulation"]]):
        if list(dims) != ["simulation"]:
            return (
                f"fair_aggregation includes 'median_params' but sweep.fair_dims "
                f"includes {dims}: median_params requires fair_dims == "
                f"['simulation'] (main_recipe.py:47 docstring; dscim does not "
                f"enforce this and fails later)."
            )
    return None


def _check_clip_gmsl_formula(config: dict) -> str | None:
    if not _menu(config).get("clip_gmsl", False):
        return None
    allowed = (
        "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)",
        "damages ~ -1 + gmsl + np.power(gmsl, 2)",
    )
    for name in _swept_sectors(config):
        formula = config.get("sectors", {}).get(name, {}).get("formula")
        if formula not in allowed:
            return (
                f"clip_gmsl is set but sector {name!r} has formula "
                f"{formula!r}; clip_gmsl is implemented only for "
                f"{list(allowed)} (main_recipe.py:264-270)."
            )
    return None


def _check_equity_not_reduced(config: dict) -> str | None:
    recipes = config.get("reduce", {}).get("recipes", [])
    if "equity" in recipes:
        return (
            "reduce.recipes includes 'equity': reduce_damages has no equity "
            "branch (preprocessing.py ce_from_chunk); the equity recipe reads "
            "risk_aversion reduced damages; list 'risk_aversion' instead."
        )
    return None


def _check_rff_emission_scenarios(config: dict) -> str | None:
    if config.get("mode") != "rff":
        return None
    scenarios = config.get("climate", {}).get("emission_scenarios", "missing")
    if scenarios is not None:
        return (
            f"mode: rff requires climate.emission_scenarios: null, got "
            f"{scenarios!r}; runid-shaped FaIR files have no rcp dimension "
            f"to select (simple_storage.py:58)."
        )
    return None


def _check_rff_coefficients(config: dict) -> str | None:
    if config.get("mode") != "rff":
        return None
    missing = [
        name
        for name in _swept_sectors(config)
        if "damage_function_path" not in config.get("sectors", {}).get(name, {})
    ]
    if missing:
        return (
            f"mode: rff requires damage_function_path on every swept sector; "
            f"missing on {missing}. In rff runs ce_path is None so fitting is "
            f"impossible (utils/menu_runs.py:163-167)."
        )
    return None


def _check_rff_no_masks(config: dict) -> str | None:
    if config.get("mode") != "rff":
        return None
    sweep = config.get("sweep", {})
    offending = [axis for axis in ("masks", "fair_dims") if axis in sweep]
    if offending:
        return (
            f"sweep axes {offending} are not available in rff mode: run_rff "
            f"has no such parameters (utils/menu_runs.py:119-127,169-170)."
        )
    return None


def _check_ssp_gmst_path(config: dict) -> str | None:
    if config.get("mode") != "ssp":
        return None
    fitting = [
        name
        for name in _swept_sectors(config)
        if "damage_function_path" not in config.get("sectors", {}).get(name, {})
    ]
    if fitting and not config.get("climate", {}).get("gmst_path"):
        return (
            f"mode: ssp with fitted sectors {fitting} requires a non-empty "
            f"climate.gmst_path: damage points are merged with GMST "
            f"anomalies during fitting (main_recipe.py damage_function_points)."
        )
    return None


def _check_gmsl_paths(config: dict) -> str | None:
    climate = config.get("climate", {})
    for name in _swept_sectors(config):
        block = config.get("sectors", {}).get(name, {})
        formula = block.get("formula", "")
        if "gmsl" not in formula:
            continue
        if not climate.get("gmsl_fair_path"):
            return (
                f"sector {name!r} has a gmsl formula but "
                f"climate.gmsl_fair_path is unset; gmsl only becomes an "
                f"anomaly variable when it is set (simple_storage.py:54)."
            )
        needs_fit = "damage_function_path" not in block
        if config.get("mode") == "ssp" and needs_fit and not climate.get("gmsl_path"):
            return (
                f"sector {name!r} has a gmsl formula and no precomputed "
                f"coefficients, so climate.gmsl_path is required for "
                f"fitting."
            )
    return None


def _check_quantreg_lengths(config: dict) -> str | None:
    menu = _menu(config)
    quantiles = menu.get("quantreg_quantiles")
    weights = menu.get("quantreg_weights")
    if quantiles is not None and weights is not None and len(quantiles) != len(weights):
        return (
            f"quantreg_quantiles has {len(quantiles)} entries but "
            f"quantreg_weights has {len(weights)}; dscim asserts equal "
            f"lengths (main_recipe.py:241-243)."
        )
    return None


COMBINATION_CHECKERS = {
    "median-params-fair-dims": _check_median_params_fair_dims,
    "clip-gmsl-formula": _check_clip_gmsl_formula,
    "equity-not-reduced": _check_equity_not_reduced,
    "rff-emission-scenarios-null": _check_rff_emission_scenarios,
    "rff-coefficients-required": _check_rff_coefficients,
    "rff-no-masks-or-fair-dims": _check_rff_no_masks,
    "ssp-gmst-path-required": _check_ssp_gmst_path,
    "gmsl-formula-needs-gmsl-paths": _check_gmsl_paths,
    "quantreg-lengths": _check_quantreg_lengths,
}


def _menu(config: dict) -> dict:
    menu = config.get("menu", {})
    return menu if isinstance(menu, dict) else {}


def _swept_sectors(config: dict) -> list[str]:
    swept = config.get("sweep", {}).get("sectors", [])
    return list(swept) if isinstance(swept, list) else []


def _sector_uses_gmsl(config: dict, sector: str) -> bool:
    formula = config.get("sectors", {}).get(sector, {}).get("formula", "")
    return "gmsl" in formula


def validate_config(config: dict, *, allow_unsupported: bool = False) -> list[str]:
    """Validate a config; return warnings, raise ConfigError on errors.

    Covers schema, value-status, and compatibility checks; filesystem
    existence is reported by the dry-run plan instead. With
    ``allow_unsupported``, unsupported settings become warnings. The
    ConfigError carries every error found.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for key in config:
        if key not in TOP_LEVEL_KEYS:
            errors.append(
                f"unknown top-level key {key!r}{_suggest(key, TOP_LEVEL_KEYS)}; "
                f"allowed: {list(TOP_LEVEL_KEYS)}"
            )

    mode = config.get("mode")
    if mode not in ("ssp", "rff"):
        errors.append(
            f"mode is required and must be 'ssp' or 'rff', got {mode!r} "
            f"(dscim itself decides by whether econ years reach 2300, "
            f"main_recipe.py global_consumption; here the choice is explicit)"
        )
        raise ConfigError(errors)

    _validate_climate(config, errors)
    _validate_econ(config, errors)
    _validate_paths(config, errors, mode=mode)
    _validate_sectors(config, errors, mode=mode)
    _validate_menu(config, errors, warnings, allow_unsupported=allow_unsupported)
    _validate_sweep(config, errors, warnings, allow_unsupported=allow_unsupported)
    _validate_reduce(config, errors, mode=mode)
    _validate_combine(config, errors, mode=mode)
    _validate_scc(config, errors)

    for rule in COMPATIBILITY:
        if mode not in rule.modes:
            continue
        message = COMBINATION_CHECKERS[rule.key](config)
        if message:
            errors.append(message)

    if errors:
        raise ConfigError(errors)
    return warnings


def _validate_climate(config: dict, errors: list[str]) -> None:
    climate = config.get("climate")
    if not isinstance(climate, dict):
        errors.append("climate block is required and must be a mapping")
        return
    removed = ("geography", "individual_region", "country_mapping_path", "country_ISOs")
    for key in climate:
        if key in ("ecs_mask_name",):
            errors.append(
                "climate.ecs_mask_name is set per-run by the sweep.masks "
                "axis, not in the climate block"
            )
        elif key not in CLIMATE_KEYS:
            errors.append(f"unknown climate key {key!r}{_suggest(key, CLIMATE_KEYS)}")
    for key in removed:
        if key in config.get("sectors", {}) or key in climate or key in _menu(config):
            errors.append(
                f"{key!r} is not on dscim main: the regional surface exists "
                f"only on the generalize_df_fit branch"
            )
    if not climate.get("gmst_fair_path"):
        errors.append(
            "climate.gmst_fair_path is required (Climate has no default; "
            "simple_storage.py:47-59)"
        )
    has_file = bool(climate.get("damages_pulse_conversion_path"))
    factors = climate.get("gas_conversions")
    if has_file == (factors is not None):
        errors.append(
            "set exactly one of climate.damages_pulse_conversion_path and "
            "climate.gas_conversions (the conversion file is generated "
            "from the inline factors when given)"
        )
    if factors is not None:
        if not isinstance(factors, dict) or not factors:
            errors.append(
                "climate.gas_conversions must be a non-empty mapping of "
                "gas to conversion factor"
            )
        else:
            for gas, factor in factors.items():
                if not isinstance(factor, int | float) or factor <= 0:
                    errors.append(
                        f"gas_conversions[{gas!r}] must be a positive "
                        f"number, got {factor!r}"
                    )
            missing = [gas for gas in climate.get("gases") or [] if gas not in factors]
            if missing:
                errors.append(
                    f"climate.gases {missing} have no entry in "
                    f"gas_conversions; the generated conversion file must "
                    f"cover every selected gas (simple_storage.py "
                    f"conversion selects on gas)"
                )


def _validate_econ(config: dict, errors: list[str]) -> None:
    econ = config.get("econ")
    if not isinstance(econ, dict) or not econ.get("path"):
        errors.append("econ.path is required (EconVars path_econ)")


def _validate_paths(config: dict, errors: list[str], *, mode: str) -> None:
    paths = config.get("paths")
    if not isinstance(paths, dict) or not paths.get("results"):
        errors.append("paths.results is required (save_path root)")
        return
    if mode == "ssp":
        needs_reduced = any(
            "damage_function_path" not in config.get("sectors", {}).get(name, {})
            for name in _swept_sectors(config)
        )
        if (needs_reduced or config.get("reduce")) and not paths.get(
            "reduced_damages_library"
        ):
            errors.append(
                "paths.reduced_damages_library is required in ssp mode when "
                "any sector is fitted or reduce is configured "
                "(preprocessing.py reduce_damages; run ce_path)"
            )


def _validate_sectors(config: dict, errors: list[str], *, mode: str) -> None:
    sectors = config.get("sectors")
    if not isinstance(sectors, dict) or not sectors:
        errors.append("sectors block is required and must be a non-empty mapping")
        return
    for name, block in sectors.items():
        if not isinstance(block, dict):
            errors.append(f"sector {name!r} must be a mapping")
            continue
        formula = block.get("formula")
        if formula not in FORMULAS:
            errors.append(
                f"sector {name!r} formula {formula!r} is not one of dscim's "
                f"12 formulas (main_recipe.py:62-75; exact string match "
                f"including whitespace)" + _suggest(str(formula), FORMULAS)
            )
        full = all(key in block for key in ("sector_path", "histclim", "delta"))
        coefficient_only = "damage_function_path" in block
        if not full and not coefficient_only:
            errors.append(
                f"sector {name!r} must have either sector_path+histclim+delta "
                f"(fitted from reduced damages) or damage_function_path "
                f"(precomputed coefficients)"
            )


def _validate_menu(
    config: dict,
    errors: list[str],
    warnings: list[str],
    *,
    allow_unsupported: bool,
) -> None:
    menu = config.get("menu", {})
    if not isinstance(menu, dict):
        errors.append("menu block must be a mapping")
        return
    for key in menu:
        if key not in MENU_KEYS:
            errors.append(f"unknown menu key {key!r}{_suggest(key, MENU_KEYS)}")

    fit_type = menu.get("fit_type", "ols")
    entry = CATALOGUE["fit_type"].value(fit_type)
    if entry is None:
        errors.append(
            f"menu.fit_type {fit_type!r} is not accepted; dscim implements "
            f"ols and quantreg only (utils/utils.py modeler)"
        )
    elif entry.status != "supported":
        _unsupported(
            errors,
            warnings,
            allow=allow_unsupported,
            message=f"menu.fit_type {fit_type!r}: {entry.reason} [{entry.citation}]",
        )

    aggregations = menu.get("fair_aggregation")
    if aggregations is not None:
        for member in aggregations:
            entry = CATALOGUE["fair_aggregation"].value(member)
            if entry is None:
                errors.append(
                    f"fair_aggregation member {member!r} is not accepted; "
                    f"valid members: {list(FAIR_AGGREGATIONS)}"
                    + _suggest(str(member), FAIR_AGGREGATIONS)
                )
            elif entry.status != "supported":
                errors.append(
                    f"fair_aggregation member {member!r}: {entry.reason} "
                    f"[{entry.citation}]"
                )

    for weitzman in menu.get("weitzman_parameter", []):
        if not isinstance(weitzman, int | float) or weitzman <= 0:
            errors.append(
                f"weitzman_parameter entries must be positive numbers, got "
                f"{weitzman!r} (values <= 1 are consumption shares, > 1 "
                f"absolute; main_recipe.py weitzman_min)"
            )

    ext_method = menu.get("ext_method", "global_c_ratio")
    entry = CATALOGUE["ext_method"].value(ext_method)
    if entry is None or entry.status != "supported":
        errors.append(
            f"menu.ext_method {ext_method!r}: only 'global_c_ratio' is "
            f"implemented in dscim; other values fall through to "
            f"UnboundLocalError (utils/utils.py model_outputs)"
        )

    for name in menu.get("save_files", []):
        if name not in SAVABLE:
            errors.append(
                f"save_files entry {name!r} is not a savable artifact"
                f"{_suggest(name, SAVABLE)}; savable: {list(SAVABLE)}"
            )

    for key in ("full_uncertainty_quantiles", "quantreg_quantiles"):
        for quantile in menu.get(key, []):
            if not isinstance(quantile, int | float) or not 0 <= quantile <= 1:
                errors.append(
                    f"{key} entries must be within [0, 1], got {quantile!r} "
                    f"(utils/utils.py get_weights raises RuntimeError)"
                )


def _validate_sweep(
    config: dict,
    errors: list[str],
    warnings: list[str],
    *,
    allow_unsupported: bool,
) -> None:
    sweep = config.get("sweep")
    if not isinstance(sweep, dict):
        errors.append(
            "sweep block is required and must be a mapping (or supply the "
            "axes via run flags: --sector, --pulse-year, --recipe, "
            "--discounting, --eta, --rho)"
        )
        return

    sectors = sweep.get("sectors", [])
    known = tuple(config.get("sectors", {}))
    for name in sectors:
        if name not in known:
            errors.append(
                f"sweep sector {name!r} is not defined in the sectors "
                f"block{_suggest(str(name), known)}"
            )
    if not sectors:
        errors.append("sweep.sectors must list at least one sector")

    if not sweep.get("pulse_years"):
        errors.append("sweep.pulse_years must list at least one year")
    for year in sweep.get("pulse_years", []):
        if not isinstance(year, int):
            errors.append(f"sweep.pulse_years entries must be integers, got {year!r}")

    for mask in sweep.get("masks", []):
        if mask is None:
            continue
        entry = CATALOGUE["ecs_mask_name"]
        _unsupported(
            errors,
            warnings,
            allow=allow_unsupported,
            message=(f"sweep mask {mask!r}: {entry.reason} [{entry.citation}]"),
        )
        break

    pairs = sweep.get("menu_pairs", [])
    if not pairs:
        errors.append(
            "sweep.menu_pairs must list at least one {recipe, discounting} pair"
        )
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != {"recipe", "discounting"}:
            errors.append(
                f"menu_pairs entries must be mappings with exactly recipe and "
                f"discounting, got {pair!r}"
            )
            continue
        recipe = pair["recipe"]
        if CATALOGUE["recipe"].value(recipe) is None:
            errors.append(
                f"recipe {recipe!r} is not one of {list(RECIPES)}"
                + _suggest(str(recipe), RECIPES)
            )
        discounting = pair["discounting"]
        entry = CATALOGUE["discounting_type"].value(discounting)
        if entry is None:
            errors.append(
                f"discounting {discounting!r} is not one of dscim's "
                f"DISCOUNT_TYPES {list(DISCOUNT_TYPES)} (main_recipe.py:52-61)"
                + _suggest(str(discounting), DISCOUNT_TYPES)
            )
        elif entry.status != "supported":
            _unsupported(
                errors,
                warnings,
                allow=allow_unsupported,
                message=(
                    f"discounting {discounting!r}: {entry.reason} [{entry.citation}]"
                ),
            )

    for pair in sweep.get("eta_rho", []):
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or not all(isinstance(x, int | float) for x in pair)
        ):
            errors.append(
                f"eta_rho entries must be [eta, rho] number pairs, got {pair!r}"
            )
    if not sweep.get("eta_rho"):
        errors.append(
            "sweep.eta_rho must list at least one [eta, rho] pair; dscim's "
            "defaults (eta 1.421158116, rho 0.00461878399) are never applied "
            "silently"
        )


def _validate_reduce(config: dict, errors: list[str], *, mode: str) -> None:
    reduce_block = config.get("reduce")
    if reduce_block is None:
        return
    if mode == "rff":
        errors.append(
            "reduce block is not applicable in rff mode: rff runs consume "
            "precomputed coefficients and never read reduced damages "
            "(utils/menu_runs.py run_rff sets ce_path=None)"
        )
        return
    for recipe in reduce_block.get("recipes", []):
        if recipe not in ("adding_up", "risk_aversion") and recipe != "equity":
            errors.append(
                f"reduce recipe {recipe!r} is not one of ['adding_up', 'risk_aversion']"
            )
    for reduction in reduce_block.get("reductions", []):
        if reduction not in REDUCTIONS:
            errors.append(
                f"reduction {reduction!r} is not one of {list(REDUCTIONS)} "
                f"(preprocessing.py ce_from_chunk)"
            )


def _validate_combine(config: dict, errors: list[str], *, mode: str) -> None:
    combine = config.get("combine")
    if combine is None:
        return
    if mode == "rff":
        errors.append(
            "combine block is not applicable in rff mode: rff coefficients "
            "are built upstream by the emulator weights (utils/rff.py)"
        )
        return
    required = ("target", "coastal", "amel")
    if not isinstance(combine, dict) or set(combine) - set(required):
        errors.append(
            f"combine block must be a mapping with keys {list(required)} "
            f"(midprocessing.py combine_CAMEL_coefs: CAMEL, coastal, AMEL)"
        )
        return
    known = config.get("sectors", {})
    for role in required:
        name = combine.get(role)
        if name not in known:
            errors.append(
                f"combine.{role} {name!r} is not defined in the sectors block"
            )
    target = combine.get("target")
    if target in known and "damage_function_path" not in known[target]:
        errors.append(
            f"combine.target {target!r} must be a coefficient-only sector "
            f"with damage_function_path (where combine writes and run reads)"
        )


def _validate_scc(config: dict, errors: list[str]) -> None:
    scc = config.get("scc")
    if scc is None:
        return
    for key in scc:
        if key not in SCC_KEYS:
            errors.append(f"unknown scc key {key!r}{_suggest(key, SCC_KEYS)}")
    if not scc.get("output"):
        errors.append("scc.output is required (directory for composed SCCs)")
    collapse = scc.get("collapse", "none")
    if collapse not in SCC_COLLAPSES:
        errors.append(f"scc.collapse {collapse!r} is not one of {list(SCC_COLLAPSES)}")
    if collapse == "certainty_equivalent":
        save_files = _menu(config).get("save_files", list(DEFAULT_SAVE_FILES))
        if "global_consumption_no_pulse" not in save_files:
            errors.append(
                "scc.collapse certainty_equivalent needs "
                "'global_consumption_no_pulse' in menu.save_files: the "
                "adjustment factor is built from consumption per capita at "
                "the pulse year (dscim-facts-epa scghg_utils.py:352-357)"
            )
    needed = {"uncollapsed_marginal_damages", "uncollapsed_discount_factors"}
    save_files = set(_menu(config).get("save_files", list(DEFAULT_SAVE_FILES)))
    missing = needed - save_files
    if missing:
        errors.append(
            f"scc composition reads {sorted(needed)}; add {sorted(missing)} "
            f"to menu.save_files"
        )
    deflator = scc.get("deflator", 1.0)
    if not isinstance(deflator, int | float) or deflator <= 0:
        errors.append(
            f"scc.deflator must be a positive number (an explicit factor; "
            f"no built-in deflator table), got {deflator!r}"
        )


def resolved_config(config: dict) -> dict:
    """Fill non-scientific defaults.

    Options marked ``config_required`` are never filled.
    """
    result = _deep_copy(config)
    menu = result.setdefault("menu", {})
    for key in MENU_KEYS:
        entry = CATALOGUE.get(key)
        if entry is None or entry.config_required or entry.default is REQUIRED:
            continue
        default = entry.default
        if isinstance(default, tuple):
            default = list(default)
        menu.setdefault(key, default)
    climate = result.setdefault("climate", {})
    for key in ("gases", "base_period", "emission_scenarios"):
        entry = CATALOGUE.get(key)
        if entry is not None and key not in climate:
            default = entry.default
            if isinstance(default, tuple):
                default = list(default)
            climate[key] = default
    result.setdefault("order", "scc")
    return result


def expand_sweep(config: dict) -> list[Run]:
    """Expand the ``sweep:`` block into concrete runs.

    The axes mirror ``run_ssps``'s product (utils/menu_runs.py:44-46);
    rff mode has no masks or fair_dims axes.
    """
    sweep = config["sweep"]
    if config["mode"] == "rff":
        masks: list[str | None] = [None]
        fair_dims_axis: list[tuple[str, ...]] = [("simulation",)]
    else:
        masks = sweep.get("masks", [None])
        fair_dims_axis = [tuple(d) for d in sweep.get("fair_dims", [["simulation"]])]

    runs = []
    for sector, pulse_year, pair, eta_rho, mask, fair_dims in itertools.product(
        sweep["sectors"],
        sweep["pulse_years"],
        sweep["menu_pairs"],
        sweep["eta_rho"],
        masks,
        fair_dims_axis,
    ):
        runs.append(
            Run(
                sector=sector,
                pulse_year=pulse_year,
                recipe=pair["recipe"],
                discounting=pair["discounting"],
                eta=eta_rho[0],
                rho=eta_rho[1],
                mask=mask,
                fair_dims=fair_dims,
            )
        )
    return runs


def save_path_for(config: dict, run: Run) -> str:
    """Build a run's save path.

    ``{results}/{sector}/{pulse_year}/{mask}`` with ``unmasked`` for no
    mask, plus a ``fair_collapsed_*`` suffix for non-default fair_dims
    (utils/menu_runs.py:48-70).
    """
    root = config["paths"]["results"]
    path = os.path.join(root, run.sector, str(run.pulse_year), run.mask or "unmasked")
    if list(run.fair_dims) != ["simulation"]:
        extra = "_".join(d for d in run.fair_dims if d != "simulation")
        path = os.path.join(path, f"fair_collapsed_{extra}")
    return path


def _coefficient_file(directory: str, run: Run) -> str:
    stem = (
        f"{run.recipe}_{run.discounting}_eta{run.eta}_rho{run.rho}"
        f"_damage_function_coefficients.nc4"
    )
    return os.path.join(directory, stem)


def epa_coefficient_file(directory: str, run: Run) -> str:
    """The EPA library's name for the same file (scghg_utils.py:257-270)."""
    stem = (
        f"{run.recipe}_{run.discounting}"
        f"_eta{round(run.eta, 3)}_rho{round(run.rho, 3)}_dfc.nc4"
    )
    return os.path.join(directory, stem)


def run_inputs(config: dict, run: Run) -> list[Input]:
    """List a run's input files with their producers.

    gmsl inputs appear only for sectors whose formula has a gmsl term.
    Reduced-damage names follow dscim main:
    ``adding_up_{cc,no_cc}.zarr`` and
    ``risk_aversion_{cc,no_cc}_eta{eta}.zarr``
    (simple_storage.py:387,414); equity reads the risk_aversion files.
    """
    climate = config["climate"]
    uses_gmsl = _sector_uses_gmsl(config, run.sector)
    block = config["sectors"][run.sector]
    fits = "damage_function_path" not in block

    entries: list[Input] = [
        Input(climate.get("gmst_fair_path") or "", "climate (FaIR GMST)"),
        Input(config["econ"]["path"], "socioeconomics"),
    ]
    if climate.get("damages_pulse_conversion_path"):
        entries.insert(
            1,
            Input(
                climate["damages_pulse_conversion_path"],
                "climate (pulse conversion)",
            ),
        )
    if uses_gmsl:
        entries.append(
            Input(climate.get("gmsl_fair_path") or "", "climate (FaIR GMSL)")
        )
    if config["mode"] == "ssp" and fits:
        entries.append(Input(climate.get("gmst_path") or "", "climate (GMST fitting)"))
        if uses_gmsl:
            entries.append(
                Input(climate.get("gmsl_path") or "", "climate (GMSL fitting)")
            )

    if not fits:
        producer = EXTERNAL
        combine = config.get("combine")
        if (
            config["mode"] == "ssp"
            and combine is not None
            and combine.get("target") == run.sector
        ):
            producer = "combine"
        entries.append(
            Input(
                _coefficient_file(block["damage_function_path"], run),
                "damage-function coefficients",
                producer,
            )
        )
    else:
        library = os.path.join(config["paths"]["reduced_damages_library"], run.sector)
        if run.recipe == "adding_up":
            names = ["adding_up_cc.zarr", "adding_up_no_cc.zarr"]
        else:
            names = [
                f"risk_aversion_cc_eta{run.eta}.zarr",
                f"risk_aversion_no_cc_eta{run.eta}.zarr",
            ]
        entries += [
            Input(os.path.join(library, name), "reduced damages", "reduce")
            for name in names
        ]

    seen: dict[str, Input] = {}
    for entry in entries:
        if entry.path:
            seen.setdefault(entry.path, entry)
    return list(seen.values())


def run_outputs(config: dict, run: Run) -> list[str]:
    """List a run's output files.

    Names follow dscim's save decorator (decorators.py:33);
    damage_function_points is a csv, everything else nc4.
    """
    save_files = _menu(config).get("save_files", list(DEFAULT_SAVE_FILES))
    base = save_path_for(config, run)
    stem = f"{run.recipe}_{run.discounting}_eta{run.eta}_rho{run.rho}"
    outputs = []
    for artifact in save_files:
        extension = "csv" if artifact == "damage_function_points" else "nc4"
        outputs.append(os.path.join(base, f"{stem}_{artifact}.{extension}"))
    return outputs


def plan_steps(config: dict) -> list[PlanStep]:
    """Derive the ordered pipeline for this config.

    Steps appear only when the config asks for them; run splits into
    fit-sector and coefficient-sector phases.
    """
    steps: list[PlanStep] = []
    sectors = config.get("sectors", {})
    aggregates = config.get("aggregates", {}) or {}
    runs = expand_sweep(config)
    fit_runs = [r for r in runs if "damage_function_path" not in sectors[r.sector]]
    coefficient_runs = [r for r in runs if r not in fit_runs]

    if aggregates:
        for name, members in aggregates.items():
            steps.append(
                PlanStep(
                    name="sum-sectors",
                    title=f"sum-sectors: build {name} from {', '.join(members)}",
                    inputs=tuple(
                        Input(
                            sectors.get(m, {}).get("sector_path", ""),
                            "sector damages",
                        )
                        for m in members
                    ),
                    outputs=(sectors.get(name, {}).get("sector_path", ""),),
                )
            )

    reduce_block = config.get("reduce")
    if reduce_block and config["mode"] == "ssp":
        reduce_sectors = sorted({r.sector for r in fit_runs})
        library = config["paths"].get("reduced_damages_library", "")
        inputs = [
            Input(
                sectors[s].get("sector_path", ""),
                "sector damages",
                "sum-sectors" if s in aggregates else EXTERNAL,
            )
            for s in reduce_sectors
        ]
        inputs.append(Input(config["econ"]["path"], "socioeconomics"))
        outputs: list[str] = []
        etas = sorted({r.eta for r in runs})
        for sector in reduce_sectors:
            for reduction in reduce_block.get("reductions", []):
                for recipe in reduce_block.get("recipes", []):
                    if recipe == "adding_up":
                        outputs.append(
                            os.path.join(library, sector, f"adding_up_{reduction}.zarr")
                        )
                    else:
                        outputs += [
                            os.path.join(
                                library,
                                sector,
                                f"risk_aversion_{reduction}_eta{eta}.zarr",
                            )
                            for eta in etas
                        ]
        steps.append(
            PlanStep(
                name="reduce",
                title=f"reduce: collapse batch for {', '.join(reduce_sectors)}",
                inputs=tuple(inputs),
                outputs=tuple(outputs),
            )
        )

    def run_step(step_runs: list[Run], label: str) -> PlanStep:
        inputs: dict[str, Input] = {}
        outputs: dict[str, None] = {}
        for run in step_runs:
            for entry in run_inputs(config, run):
                inputs.setdefault(entry.path, entry)
            for path in run_outputs(config, run):
                outputs.setdefault(path, None)
        names = sorted({r.sector for r in step_runs})
        return PlanStep(
            name="run",
            title=f"run: {label} {', '.join(names)}",
            inputs=tuple(inputs.values()),
            outputs=tuple(outputs),
        )

    if fit_runs:
        steps.append(run_step(fit_runs, "fit and integrate"))

    combine = config.get("combine")
    if combine and config["mode"] == "ssp":
        target = combine["target"]
        directory = sectors.get(target, {}).get("damage_function_path", "")
        pairs = {(r.recipe, r.discounting, r.eta, r.rho) for r in runs}
        inputs = []
        outputs = []
        for recipe, discounting, eta, rho in sorted(pairs):
            stem = (
                f"{recipe}_{discounting}_eta{eta}_rho{rho}"
                f"_damage_function_coefficients.nc4"
            )
            for role in ("coastal", "amel"):
                source = combine[role]
                inputs.append(
                    Input(
                        os.path.join(
                            config["paths"]["results"], source, "2020", "unmasked", stem
                        ),
                        f"{role} coefficients",
                        "run",
                    )
                )
            outputs.append(os.path.join(directory, stem))
        steps.append(
            PlanStep(
                name="combine",
                title=f"combine: merge {combine['coastal']} + {combine['amel']} "
                f"into {target}",
                inputs=tuple(inputs),
                outputs=tuple(outputs),
            )
        )

    if coefficient_runs:
        steps.append(run_step(coefficient_runs, "integrate precomputed"))

    scc = config.get("scc")
    if scc:
        inputs = []
        for run in runs:
            for path in run_outputs(config, run):
                if "uncollapsed_marginal_damages" in path or (
                    "uncollapsed_discount_factors" in path
                ):
                    inputs.append(Input(path, "uncollapsed run output", "run"))
        steps.append(
            PlanStep(
                name="scc",
                title="scc: compose, deflate, and collapse SCCs",
                inputs=tuple(inputs),
                outputs=(scc.get("output", ""),),
            )
        )
    return steps


def _missing_by_producer(config: dict, runs: list[Run]) -> dict[str, list[Input]]:
    grouped: dict[str, dict[str, Input]] = {}
    for run in runs:
        for entry in run_inputs(config, run):
            if not os.path.exists(entry.path):
                grouped.setdefault(entry.producer, {}).setdefault(entry.path, entry)
    return {producer: list(paths.values()) for producer, paths in grouped.items()}


def summary_data(config: dict, runs: list[Run]) -> dict:
    """Collect the dry-run summary as plain data.

    Keys: mode, run count, axis sizes, missing inputs grouped by
    producer, output totals, and the blocked-run count.
    """
    sweep = config["sweep"]
    axes = [
        f"{len(sweep['sectors'])} sectors",
        f"{len(sweep['pulse_years'])} pulse_years",
        f"{len(sweep['menu_pairs'])} menu pairs",
        f"{len(sweep['eta_rho'])} eta_rho",
    ]
    if config["mode"] == "ssp":
        axes.append(f"{len(sweep.get('masks', [None]))} masks")
        axes.append(f"{len(sweep.get('fair_dims', [['simulation']]))} fair_dims")
    all_outputs = [p for run in runs for p in run_outputs(config, run)]
    return {
        "mode": config["mode"],
        "runs": len(runs),
        "axes": axes,
        "missing": {
            producer: sorted(entries, key=lambda e: e.path)
            for producer, entries in _missing_by_producer(config, runs).items()
        },
        "outputs": len(all_outputs),
        "outputs_existing": sum(1 for p in all_outputs if os.path.exists(p)),
        "blocked": sum(
            1
            for run in runs
            if any(not os.path.exists(i.path) for i in run_inputs(config, run))
        ),
    }


def render_summary(config: dict, runs: list[Run]) -> str:
    """Render the summary dry-run report."""
    data = summary_data(config, runs)
    lines = [
        f"mode: {data['mode']}",
        f"runs: {data['runs']}  ({' x '.join(data['axes'])})",
    ]
    if data["missing"]:
        lines.append("missing inputs:")
        for producer in sorted(data["missing"], key=lambda p: (p != EXTERNAL, p)):
            entries = data["missing"][producer]
            if producer == EXTERNAL:
                lines.append(f"  external: provide these files ({len(entries)}):")
            else:
                lines.append(
                    f"  produced by `dscim-cil {producer} CONFIG` ({len(entries)}):"
                )
            for entry in entries:
                lines.append(f"    {entry.path}  [{entry.kind}]")
    else:
        lines.append("missing inputs: none")
    lines.append(
        f"outputs: {data['outputs']} files, {data['outputs_existing']} already exist"
    )
    lines.append(f"blocked runs: {data['blocked']} of {data['runs']} (missing inputs)")
    lines.append("use --verbose or --runs N[,N...] for per-run detail")
    return "\n".join(lines)


def render_plan(
    config: dict, runs: list[Run], *, indices: list[int] | None = None
) -> str:
    """Render per-run dry-run detail; ``indices`` are 1-based."""
    lines = [f"mode: {config['mode']}", f"runs: {len(runs)}", ""]
    for index, run in enumerate(runs, start=1):
        if indices is not None and index not in indices:
            continue
        fair = ",".join(run.fair_dims)
        lines.append(
            f"[{index}] sector={run.sector} pulse_year={run.pulse_year} "
            f"recipe={run.recipe} discounting={run.discounting} "
            f"eta={run.eta} rho={run.rho} mask={run.mask or 'unmasked'} "
            f"fair_dims={fair}"
        )
        for entry in run_inputs(config, run):
            if os.path.exists(entry.path):
                tag = "ok"
            elif entry.producer:
                tag = f"MISSING -> dscim-cil {entry.producer}"
            else:
                tag = "MISSING (external)"
            lines.append(f"    in  [{tag}] {entry.path}")
        for path in run_outputs(config, run):
            tag = "exists" if os.path.exists(path) else "new"
            lines.append(f"    out [{tag}] {path}")
    return "\n".join(lines)


SCC_KEYS = ("deflator", "collapse", "output", "damages_from", "discounting_from")

# Where each catalogued option lives in a config. Sweep-axis options are
# handled separately because their values are lists of combinations.
OPTION_LOCATIONS = {
    **{key: ("menu", key) for key in MENU_KEYS},
    **{key: ("climate", key) for key in CLIMATE_KEYS},
    "path_econ": ("econ", "path"),
    "order": (None, "order"),
    "ce_path": ("paths", "reduced_damages_library"),
    "damage_function_path": ("sectors", None),
    "reduction": ("reduce", "reductions"),
}

SWEEP_OPTIONS = {
    "sector": "sectors",
    "pulse_year": "pulse_years",
    "recipe": "menu_pairs",
    "discounting_type": "menu_pairs",
    "eta": "eta_rho",
    "rho": "eta_rho",
    "ecs_mask_name": "masks",
    "fair_dims": "fair_dims",
}

SUMMARY_OPTIONS = (
    "eta",
    "rho",
    "recipe",
    "discounting_type",
    "sector",
    "pulse_year",
    "fit_type",
    "fair_aggregation",
    "weitzman_parameter",
    "discrete_discounting",
    "ext_method",
    "gases",
)


def _sweep_value(config: dict, name: str) -> object:
    sweep = config.get("sweep", {})
    axis = SWEEP_OPTIONS[name]
    values = sweep.get(axis)
    if values is None:
        return None
    if name == "eta":
        pairs = [p[0] for p in values]
    elif name == "rho":
        pairs = [p[1] for p in values]
    elif name == "recipe":
        pairs = [p["recipe"] for p in values]
    elif name == "discounting_type":
        pairs = [p["discounting"] for p in values]
    elif name == "ecs_mask_name":
        pairs = [v or "unmasked" for v in values]
    else:
        pairs = list(values)
    unique = []
    for value in pairs:
        if value not in unique:
            unique.append(value)
    return unique[0] if len(unique) == 1 else unique


def effective_settings(
    config: dict | None, *, sources: dict[str, str] | None = None
) -> list[tuple[str, object, str]]:
    """Resolve every catalogued option to (name, value, origin).

    Origins: config, flag, override, default, required, or the option's
    status for dead and removed entries. ``config`` may be None for
    dscim's defaults alone.
    """
    sources = sources or {}
    rows: list[tuple[str, object, str]] = []
    for name, entry in sorted(CATALOGUE.items()):
        if entry.status in ("dead", "removed"):
            rows.append((name, entry.default, entry.status))
            continue
        if name == "formula":
            formulas = sorted(
                {
                    block.get("formula")
                    for block in (config or {}).get("sectors", {}).values()
                    if isinstance(block, dict) and block.get("formula")
                }
            )
            if formulas:
                value = formulas[0] if len(formulas) == 1 else formulas
                rows.append((name, value, "config"))
            else:
                rows.append((name, entry.default, "required: you must set this"))
            continue
        if name in SWEEP_OPTIONS:
            axis = SWEEP_OPTIONS[name]
            value = _sweep_value(config, name) if config else None
            if value is None:
                rows.append((name, entry.default, "required: you must set this"))
            else:
                rows.append((name, value, sources.get(f"sweep.{axis}", "config")))
            continue
        section, key = OPTION_LOCATIONS.get(name, (None, None))
        if key is None:
            if entry.config_required or entry.default is REQUIRED:
                rows.append((name, entry.default, "required: you must set this"))
            else:
                rows.append((name, entry.default, "default"))
            continue
        block = config if section is None else (config or {}).get(section, {})
        if config is not None and isinstance(block, dict) and key in block:
            dotted = key if section is None else f"{section}.{key}"
            rows.append((name, block[key], sources.get(dotted, "config")))
        elif entry.config_required or entry.default is REQUIRED:
            rows.append((name, entry.default, "required: you must set this"))
        else:
            default = entry.default
            if isinstance(default, tuple):
                default = list(default)
            rows.append((name, default, "default"))
    return rows


def settings_summary(
    config: dict, *, sources: dict[str, str] | None = None, verbose: bool = False
) -> str:
    """Render the values a run will use, with their origins.

    The short form covers the result-selecting settings; verbose covers
    every catalogued option.
    """
    rows = effective_settings(config, sources=sources)
    if not verbose:
        rows = [row for row in rows if row[0] in SUMMARY_OPTIONS]
    lines = ["settings:"]
    for name, value, origin in rows:
        rendered = repr(value) if not isinstance(value, str) else value
        lines.append(f"  {name:26} {rendered:38} ({origin})")
    return "\n".join(lines)


def config_provenance(
    config: dict, *, sources: dict[str, str] | None = None
) -> dict[str, str]:
    """Map every resolved option name to where its value came from."""
    return {
        name: origin for name, _, origin in effective_settings(config, sources=sources)
    }
