"""Catalogue of the dscim option surface.

Every option dscim accepts, with its default, the pipeline stages that
consume it, its status, and a source citation into dscim main @
6a1f4d7e (cited as ``path:line``).
"""

from dataclasses import dataclass

__all__ = [
    "CATALOGUE",
    "COMPATIBILITY",
    "CONST_DISC_RATES",
    "DEFAULT_SAVE_FILES",
    "DISCOUNT_TYPES",
    "EXTRA_SAVE_FILES",
    "FAIR_AGGREGATIONS",
    "FORMULAS",
    "KNOWN_ECS_MASKS",
    "MODES",
    "PIPELINE",
    "RECIPES",
    "REDUCTIONS",
    "REQUIRED",
    "STATUSES",
    "Combination",
    "Option",
    "Stage",
    "Value",
    "option",
]


class _Required:
    """Sentinel for options with no default in dscim."""

    def __repr__(self) -> str:
        return "required"


REQUIRED = _Required()

STATUSES = ("supported", "unsupported", "dead", "removed")

MODES = ("ssp", "rff")

# Verbatim from dscim main @ 6a1f4d7e, src/dscim/menu/main_recipe.py:62-75.
FORMULAS = (
    "damages ~ -1 + np.power(anomaly, 2)",
    "damages ~ gmsl + np.power(gmsl, 2)",
    "damages ~ -1 + gmsl + np.power(gmsl, 2)",
    "damages ~ -1 + gmsl",
    "damages ~ anomaly + np.power(anomaly, 2)",
    "damages ~ -1 + anomaly + np.power(anomaly, 2)",
    "damages ~ -1 + gmsl + anomaly + np.power(anomaly, 2)",
    "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)",
    (
        "damages ~ -1 + anomaly * gmsl + anomaly * np.power(gmsl, 2) + gmsl * "
        "np.power(anomaly, 2) + np.power(anomaly, 2) * np.power(gmsl, 2)"
    ),
    "damages ~ anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)",
    (
        "damages ~ -1 + anomaly:gmsl + anomaly:np.power(gmsl, 2) + "
        "gmsl:np.power(anomaly, 2) + np.power(anomaly, 2):np.power(gmsl, 2)"
    ),
    "damages ~ -1 + gmsl:anomaly + gmsl:np.power(anomaly, 2)",
)

# Verbatim from main_recipe.py:52-61.
DISCOUNT_TYPES = (
    "constant",
    "constant_model_collapsed",
    "constant_gwr",
    "naive_ramsey",
    "euler_ramsey",
    "naive_gwr",
    "gwr_gwr",
    "euler_gwr",
)

# Verbatim from main_recipe.py:51.
CONST_DISC_RATES = (0.01, 0.015, 0.02, 0.025, 0.03, 0.05)

# Verbatim from main_recipe.py:183-196 (the default save_files list).
DEFAULT_SAVE_FILES = (
    "damage_function_points",
    "damage_function_coefficients",
    "damage_function_fit",
    "marginal_damages",
    "discount_factors",
    "uncollapsed_sccs",
    "scc",
    "uncollapsed_discount_factors",
    "uncollapsed_marginal_damages",
    "global_consumption",
    "global_consumption_no_pulse",
)

# Savable names absent from the default list: each is a @save-decorated
# member of MainRecipe (main_recipe.py: ce_fair_pulse/ce_fair_no_pulse/
# global_consumption_pulse/stat_uncertainty_iqr/full_uncertainty_iqr).
EXTRA_SAVE_FILES = (
    "ce_fair_pulse",
    "ce_fair_no_pulse",
    "global_consumption_pulse",
    "stat_uncertainty_iqr",
    "full_uncertainty_iqr",
)

# main_recipe.py:118-119 default; "median" is consumed separately at the
# SCC step and "uncollapsed" is not a valid member (see the value entry).
FAIR_AGGREGATIONS = ("ce", "mean", "gwr_mean", "median", "median_params")

# src/dscim/__init__.py:21-25 (MENU_OPTIONS registry).
RECIPES = ("adding_up", "risk_aversion", "equity")

REDUCTIONS = ("cc", "no_cc")

# The mask axis is an open set (any variable name in the mask file);
# these five are the names used in production
# (dscim-research main/run_integration_result.py:183-190).
KNOWN_ECS_MASKS = (
    "truncate_at_ecs995symmetric_passing_mask",
    "truncate_at_ecs990symmetric_passing_mask",
    "truncate_at_ecs950symmetric_passing_mask",
    "truncate_at_ecs830symmetric_passing_mask",
    "truncate_at_ecs750symmetric_passing_mask",
)


@dataclass(frozen=True)
class Value:
    """One accepted value of an option, with its own status.

    Parameters
    ----------
    value :
        The literal value as it appears in config or dscim source.
    status :
        One of ``STATUSES``.
    reason :
        Why the value has its status; required when not ``supported``.
    citation :
        Source location backing the reason.
    restriction :
        Why the restriction exists: ``library`` (a dscim limitation),
        ``data`` (a consequence of precomputed inputs), or
        ``specification`` (a policy choice). Empty for supported values.
    """

    value: object
    status: str = "supported"
    reason: str = ""
    citation: str = ""
    restriction: str = ""


@dataclass(frozen=True)
class Option:
    """One option dscim accepts.

    Parameters
    ----------
    name :
        Config-facing name; matches the dscim parameter name.
    summary :
        One-sentence description.
    stages :
        Pipeline stages that consume the option: subset of
        ``("reduce", "fit", "fair", "discount", "output", "climate",
        "econ", "combine")``.
    default :
        dscim main's default, or ``REQUIRED``.
    citation :
        Where the parameter and its default live in dscim main.
    status :
        One of ``STATUSES``; non-supported statuses need ``reason``.
    reason :
        Why the option has its status.
    restriction :
        Why the restriction exists: ``library``, ``data``, or
        ``specification``.
    modes :
        Run modes in which the option applies.
    values :
        Enumerated accepted values when the set is closed.
    open_set :
        True when ``values`` documents known values but others are legal.
    config_required :
        True when the value must appear in config; dscim's default is
        recorded in ``default`` for reference only.
    """

    name: str
    summary: str
    stages: tuple[str, ...]
    default: object
    citation: str
    status: str = "supported"
    reason: str = ""
    restriction: str = ""
    modes: tuple[str, ...] = MODES
    values: tuple[Value, ...] = ()
    open_set: bool = False
    config_required: bool = False

    def value(self, raw: object) -> Value | None:
        """Return the catalogued entry for ``raw``, or None."""
        for entry in self.values:
            if entry.value == raw:
                return entry
        return None


@dataclass(frozen=True)
class Combination:
    """A cross-option validity rule.

    Parameters
    ----------
    key :
        Stable identifier linking this rule to its checker.
    options :
        Option names involved.
    kind :
        ``"requires"`` or ``"forbidden"``.
    description :
        The rule as one sentence; rendered by ``dscim-cil compat``.
    citation :
        Source backing the rule.
    modes :
        Run modes the rule applies to.
    """

    key: str
    options: tuple[str, ...]
    kind: str
    description: str
    citation: str
    modes: tuple[str, ...] = MODES


@dataclass(frozen=True)
class Stage:
    """One pipeline stage: a dscim-cil command with its data flow.

    Parameters
    ----------
    name :
        The command name.
    summary :
        What the stage does, in one sentence.
    consumes :
        Input kinds the stage reads.
    produces :
        Output kinds the stage writes.
    collapses :
        Dimension transformations the stage performs, with source
        citations.
    modes :
        Run modes in which the stage exists.
    library_call :
        The dscim function(s) the stage wraps, if any.
    """

    name: str
    summary: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]
    collapses: tuple[str, ...]
    modes: tuple[str, ...] = MODES
    library_call: str = ""


PIPELINE: tuple[Stage, ...] = (
    Stage(
        name="sum-sectors",
        summary="Sum member sectors' delta and histclim into an aggregate "
        "sector zarr (e.g. AMEL from agriculture+mortality+energy+labor).",
        consumes=("member sector damages zarrs (sectors.<name>.sector_path)",),
        produces=("aggregate sector damages zarr (its sector_path)",),
        collapses=(
            (
                "no collapse: sums variables across sectors at identical dimensions "
                "(preprocessing.py sum_AMEL)"
            ),
        ),
        modes=("ssp",),
        library_call="dscim.preprocessing.preprocessing.sum_AMEL",
    ),
    Stage(
        name="reduce",
        summary="Collapse the batch dimension of sector damages against "
        "socioeconomics, producing the reduced-damage zarrs runs consume.",
        consumes=(
            "sector damages zarrs (batch chunked at 15)",
            "econ zarr (external)",
        ),
        produces=(
            (
                "reduced zarrs: adding_up_{cc,no_cc}.zarr and "
                "risk_aversion_{cc,no_cc}_eta{eta}.zarr per sector"
            ),
        ),
        collapses=(
            (
                "batch: mean for adding_up, certainty equivalent at eta for "
                "risk_aversion (preprocessing.py ce_from_chunk)"
            ),
        ),
        modes=("ssp",),
        library_call="dscim.preprocessing.preprocessing.reduce_damages",
    ),
    Stage(
        name="run",
        summary="Execute menu runs: fit damage functions (or load "
        "precomputed coefficients), apply FaIR, discount, and write SCC "
        "artifacts.",
        consumes=(
            "reduced zarrs (sectors without damage_function_path; ssp only)",
            (
                "damage-function coefficient nc4s (sectors with "
                "damage_function_path; all rff sectors)"
            ),
            (
                "climate files: gmst/gmsl fitting inputs, FaIR control/pulse, "
                "pulse conversion (external)"
            ),
            "econ zarr or rff socioeconomics nc4 (external)",
        ),
        produces=(
            (
                "per-run artifacts named "
                "{recipe}_{discounting}_eta{eta}_rho{rho}_{artifact} under "
                "the save path"
            ),
        ),
        collapses=(
            (
                "ssp and model: collapsed when discounting contains gwr "
                "(pooled damage-function fit, pop.mean(['model','ssp']); "
                "main_recipe.py collapsed_pop and damage_function_calculation)"
            ),
            (
                "fair_dims (default [simulation]): collapsed by the FaIR "
                "aggregations ce/mean/median (main_recipe.py marginal_damages)"
            ),
            (
                "discrate: a new dimension added by constant discounting, one "
                "entry per CONST_DISC_RATES value (main_recipe.py discounted_damages)"
            ),
            (
                "rff mode: runid (10,000 draws) replaces "
                "gcm/rcp/ssp/model as the uncertainty dimensions; the "
                "ssp/model collapse happened upstream in the emulator weights "
                "(utils/rff.py weight_df; utils/menu_runs.py run_rff)"
            ),
        ),
        library_call="dscim MENU_OPTIONS[recipe](**kwargs).order_plate(order)",
    ),
    Stage(
        name="combine",
        summary="Merge coastal and AMEL damage-function coefficients into "
        "the combined (CAMEL) sector's coefficient files.",
        consumes=("coastal and AMEL coefficient nc4s written by run (fit sectors)",),
        produces=("combined-sector coefficient (and optionally fit) nc4s",),
        collapses=(
            (
                "no collapse: concatenates coefficient variables from the two "
                "sources (midprocessing.py combine_CAMEL_coefs)"
            ),
        ),
        modes=("ssp",),
        library_call="dscim.preprocessing.midprocessing.combine_CAMEL_coefs",
    ),
    Stage(
        name="scc",
        summary="Compose SCCs from the uncollapsed run outputs: sum "
        "marginal damages times discount factors over years, deflate, "
        "and collapse the uncertainty dimension.",
        consumes=(
            (
                "uncollapsed_marginal_damages and uncollapsed_discount_factors "
                "nc4s written by run"
            ),
        ),
        produces=("SCC files under scc.output",),
        collapses=(
            (
                "year: summed out by the present-value integration "
                "(dscim-facts-epa scghg_utils.py:335-337)"
            ),
            (
                "runid (rff) or the fair dims (ssp): collapsed per "
                "scc.collapse: mean, certainty_equivalent (adjustment factor "
                "(gcnp/pop)^(-eta) normalized at the pulse year, "
                "scghg_utils.py:352-357), or none"
            ),
        ),
    ),
)


def _v(value: object, **kwargs: str) -> Value:
    return Value(value, **kwargs)


_OPTIONS = (
    # ------------------------------------------------------------------
    # Menu (MainRecipe.__init__, main_recipe.py:77-110)
    # ------------------------------------------------------------------
    Option(
        "sector",
        "Sector name; a free string keying the config sectors block. Names "
        "containing 'agriculture' drop the ACCESS1-0/rcp85 combination and "
        "names containing 'coastal' change reduce chunking.",
        ("reduce", "fit"),
        REQUIRED,
        "main_recipe.py:81; substring behavior main_recipe.py "
        "(agriculture filter) and preprocessing.py:100 (coastal)",
        config_required=True,
    ),
    Option(
        "formula",
        "Damage-function formula; must match one of dscim's 12 strings "
        "exactly (whitespace included) because downstream dispatch is "
        "whole-string equality.",
        ("fit", "fair"),
        REQUIRED,
        "main_recipe.py:82; whitelist main_recipe.py:62-75; assert "
        "main_recipe.py:249-251",
        values=tuple(_v(f) for f in FORMULAS),
        config_required=True,
    ),
    Option(
        "recipe",
        "Menu recipe selecting the aggregation of damages over uncertainty.",
        ("reduce", "fit", "fair", "discount"),
        REQUIRED,
        "src/dscim/__init__.py:21-25 (MENU_OPTIONS)",
        values=(
            _v("adding_up"),
            _v("risk_aversion"),
            _v("equity"),
        ),
        config_required=True,
    ),
    Option(
        "discounting_type",
        "Discounting scheme; also controls damage-function fit grouping "
        "and population collapse.",
        ("fit", "discount"),
        None,
        "main_recipe.py:88 (default None); accepted set main_recipe.py:"
        "52-61; assert main_recipe.py:245-247",
        values=(
            _v("constant"),
            _v("constant_model_collapsed"),
            _v(
                "constant_gwr",
                status="unsupported",
                reason=(
                    "Listed in DISCOUNT_TYPES but its non-constant "
                    "discount-factor path has no branch in "
                    "calculate_stream_discount_factors and raises "
                    "UnboundLocalError; never used in any production repo "
                    "or in dscim's own test matrix."
                ),
                citation=(
                    "main_recipe.py:52-61; calculate_stream_discount_factors has no "
                    "constant_gwr branch; dscim's tests/conftest.py "
                    "discount_types fixture omits it"
                ),
                restriction="library",
            ),
            _v("naive_ramsey"),
            _v("euler_ramsey"),
            _v("naive_gwr"),
            _v("gwr_gwr"),
            _v("euler_gwr"),
        ),
        config_required=True,
    ),
    Option(
        "fit_type",
        "Damage-function estimation type.",
        ("fit",),
        "ols",
        "main_recipe.py:87; dispatch utils/utils.py (modeler)",
        values=(
            _v("ols"),
            _v(
                "quantreg",
                status="unsupported",
                reason=(
                    "dscim asserts it is incompatible with risk_aversion "
                    "reduction; it emits a different artifact set "
                    "(full_uncertainty_iqr/stat_uncertainty_iqr instead of "
                    "the standard SCC outputs) and requires batch-keeping "
                    "reduced damages, a storage layout incompatible with "
                    "the reduced files the run stage otherwise consumes. "
                    "Production used it only for the labor and agriculture "
                    "papers, never for CAMEL."
                ),
                citation=(
                    "preprocessing.py:85-92 (risk_aversion assert); "
                    "main_recipe.py order_plate quantreg branch"
                ),
                restriction="specification",
            ),
        ),
    ),
    Option(
        "eta",
        "Utility-function curvature; consumed by CE reduction, Weitzman "
        "bottom-coding, and discount factors. eta == 1 switches to log "
        "utility.",
        ("reduce", "fair", "discount"),
        1.421158116,
        "main_recipe.py:86",
        config_required=True,
    ),
    Option(
        "rho",
        "Pure rate of time preference; consumed only by Ramsey/GWR "
        "discount factors, yet embedded in every output filename.",
        ("discount",),
        0.00461878399,
        "main_recipe.py:85; filename decorators.py:33",
        config_required=True,
    ),
    Option(
        "ext_method",
        "Extrapolation method for the damage function beyond the fit window.",
        ("fit",),
        "global_c_ratio",
        "main_recipe.py:89; implementation utils/utils.py (model_outputs)",
        values=(
            _v("global_c_ratio"),
            _v(
                "time_trends",
                status="removed",
                reason=(
                    "Appears in one archived production config from an "
                    "older dscim era; current dscim implements only "
                    "global_c_ratio and any other value falls through to "
                    "UnboundLocalError."
                ),
                citation=(
                    "utils/utils.py model_outputs (global_c_ratio only); "
                    "dscim-research configs/archive/hybrid_mortality_config.yaml:15"
                ),
                restriction="library",
            ),
        ),
    ),
    Option(
        "ext_subset_start_year",
        "First year of the extrapolation-basis window.",
        ("fit",),
        2085,
        "main_recipe.py:90",
    ),
    Option(
        "ext_subset_end_year",
        "Last year of the fit range and extrapolation-basis window.",
        ("fit",),
        2099,
        "main_recipe.py:91",
    ),
    Option(
        "ext_end_year",
        "Extrapolation and discounting horizon.",
        ("fit", "discount"),
        2300,
        "main_recipe.py:92",
    ),
    Option(
        "subset_dict",
        "Dimension subsets applied when cutting damages; keys absent from "
        "the data are silently ignored.",
        ("reduce", "fit"),
        None,
        "main_recipe.py:93; simple_storage.py (cut)",
    ),
    Option(
        "ce_path",
        "Directory of reduced-damage zarrs; derived by dscim-cil from "
        "paths.reduced_damages_library and the sector, not set directly.",
        ("fit",),
        None,
        "main_recipe.py:94; consumers simple_storage.py:387,414",
        modes=("ssp",),
    ),
    Option(
        "damage_function_path",
        "Directory of precomputed damage-function coefficients; presence "
        "makes the run skip fitting. Required for every sector in rff "
        "mode.",
        ("fit",),
        None,
        "main_recipe.py:95; loaders main_recipe.py "
        "(damage_function_coefficients); rff requirement "
        "utils/menu_runs.py:163-167",
    ),
    Option(
        "clip_gmsl",
        "Clip FaIR GMSL at the damage function's local maximum; only "
        "implemented for the two gmsl-quadratic formulas.",
        ("fair",),
        False,
        "main_recipe.py:96; assert main_recipe.py:264-270",
    ),
    Option(
        "gdppc_bottom_code",
        "Floor applied to per-capita GDP.",
        ("reduce",),
        39.39265060424805,
        "main_recipe.py:97",
    ),
    Option(
        "scc_quantiles",
        "Stored on the recipe but read by nothing.",
        (),
        (0.05, 0.17, 0.25, 0.5, 0.75, 0.83, 0.95),
        "main_recipe.py:98,112-113",
        status="dead",
        reason="Assigned in __init__ and never used anywhere in dscim.",
        restriction="library",
    ),
    Option(
        "scenario_dimensions",
        "Dimensions to group damage-function fits by; discrete-SSP "
        "production always leaves this None (single fit).",
        ("fit",),
        None,
        "main_recipe.py:99; left None in every discrete-SSP production config",
    ),
    Option(
        "weitzman_parameter",
        "Bottom-coding thresholds; each value <= 1 is a share of "
        "no-climate-change global consumption, > 1 an absolute value. "
        "Values become string coordinates in outputs.",
        ("fair",),
        (0.1, 0.5),
        "main_recipe.py:100,115-116; semantics main_recipe.py (weitzman_min)",
    ),
    Option(
        "fair_aggregation",
        "How to collapse FaIR uncertainty into SCCs. An empty list skips "
        "the collapsed-SCC computation and leaves the uncollapsed trio.",
        ("fair", "discount"),
        FAIR_AGGREGATIONS,
        "main_recipe.py:101,118-119; dispatch main_recipe.py (marginal_damages)",
        values=(
            _v("ce"),
            _v("mean"),
            _v("gwr_mean"),
            _v("median"),
            _v("median_params"),
            _v(
                "uncollapsed",
                status="unsupported",
                reason=(
                    "Not a valid member: marginal_damages has no branch "
                    "for it and raises NotImplementedError, which breaks "
                    "calculate_scc. The uncollapsed pipeline is reached "
                    "by fair_aggregation: [] plus the dscim-cil scc "
                    "command, which composes SCCs from the uncollapsed "
                    "outputs."
                ),
                citation=(
                    "main_recipe.py marginal_damages (no uncollapsed branch) "
                    "and order_plate"
                ),
                restriction="library",
            ),
        ),
    ),
    Option(
        "filename_suffix",
        "Suffix appended to every saved artifact filename.",
        ("output",),
        "",
        "main_recipe.py:102; decorators.py:33",
    ),
    Option(
        "discrete_discounting",
        "Discrete rather than continuous discounting.",
        ("discount",),
        False,
        "main_recipe.py:103",
    ),
    Option(
        "quantreg_quantiles",
        "Quantiles for quantile-regression fits; only meaningful under "
        "fit_type quantreg.",
        ("fit",),
        (
            0.05,
            0.1,
            0.15,
            0.2,
            0.25,
            0.3,
            0.35,
            0.4,
            0.45,
            0.5,
            0.55,
            0.6,
            0.65,
            0.7,
            0.75,
            0.8,
            0.85,
            0.9,
            0.95,
        ),
        "main_recipe.py:104,121-142",
        status="unsupported",
        reason="Consumed only by quantile-regression fits; carries the "
        "same restrictions as fit_type: quantreg (see that option).",
        restriction="specification",
    ),
    Option(
        "quantreg_weights",
        "Accepted and length-checked against quantreg_quantiles, then "
        "never used: downstream weights are recomputed by get_weights().",
        (),
        (
            0.075,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.075,
        ),
        "main_recipe.py:105,144-165; assert main_recipe.py:241-243; "
        "utils/utils.py get_weights",
        status="dead",
        reason="Only consumed by a length assertion; real weights come "
        "from utils.get_weights.",
        restriction="library",
    ),
    Option(
        "full_uncertainty_quantiles",
        "Quantiles for the quantreg IQR outputs.",
        ("output",),
        (0.01, 0.05, 0.17, 0.25, 0.5, 0.75, 0.83, 0.95, 0.99),
        "main_recipe.py:106,167-178",
        status="unsupported",
        reason="Consumed only by the quantile-regression IQR outputs "
        "(full_uncertainty_iqr/stat_uncertainty_iqr); carries the same "
        "restrictions as fit_type: quantreg (see that option).",
        restriction="specification",
    ),
    Option(
        "extrap_formula",
        "Stored and never read by current dscim; was a live config key in "
        "the 96k-era production configs.",
        (),
        None,
        "main_recipe.py:107; last configured in dscim-research "
        "configs/archive/96k_config.yaml:23",
        status="dead",
        reason="Assigned in __init__ and never used; the feature it "
        "configured was removed from dscim.",
        restriction="library",
    ),
    Option(
        "fair_dims",
        "Dimensions collapsed by the FaIR CE/mean/median aggregations; "
        "production sweeps four sets. Non-default sets add a "
        "fair_collapsed_* segment to the save path.",
        ("fair", "discount"),
        ("simulation",),
        "main_recipe.py:108,180-181; path rule utils/menu_runs.py:65-70",
    ),
    Option(
        "save_files",
        "Artifact names to write; membership gates saving.",
        ("output",),
        DEFAULT_SAVE_FILES,
        "main_recipe.py:109,183-196; gate decorators.py:29",
        values=tuple(_v(n) for n in DEFAULT_SAVE_FILES + EXTRA_SAVE_FILES),
    ),
    Option(
        "order",
        "Menu course to execute.",
        ("output",),
        "scc",
        "order_plate courses main_recipe.py:280",
        values=(_v("scc"), _v("damage_function")),
    ),
    # ------------------------------------------------------------------
    # Climate (simple_storage.py:47-59)
    # ------------------------------------------------------------------
    Option(
        "gmst_path",
        "GMST anomalies CSV used when fitting damage functions.",
        ("fit",),
        REQUIRED,
        "simple_storage.py:49",
        modes=("ssp",),
    ),
    Option(
        "gmsl_path",
        "GMSL zarr used when fitting damage functions for gmsl formulas.",
        ("fit",),
        REQUIRED,
        "simple_storage.py:50",
        modes=("ssp",),
    ),
    Option(
        "gmst_fair_path",
        "FaIR temperature control/pulse file.",
        ("fair",),
        REQUIRED,
        "simple_storage.py:51",
    ),
    Option(
        "gmsl_fair_path",
        "FaIR GMSL control/pulse file; when set, gmsl joins the anomaly variables.",
        ("fair",),
        None,
        "simple_storage.py:54",
    ),
    Option(
        "damages_pulse_conversion_path",
        "Per-gas pulse-to-tonne conversion file.",
        ("fair",),
        REQUIRED,
        "simple_storage.py:52",
    ),
    Option(
        "pulse_year",
        "Year of the emissions pulse; must exist as a coordinate in the FaIR files.",
        ("fair", "discount"),
        REQUIRED,
        "simple_storage.py:53; selection in Climate.anomalies",
        config_required=True,
    ),
    Option(
        "ecs_mask_path",
        "File of boolean masks over FaIR simulations.",
        ("fair",),
        None,
        "simple_storage.py:55",
        modes=("ssp",),
    ),
    Option(
        "ecs_mask_name",
        "Mask variable to apply; both path and name must be set for "
        "masking to occur. Open set; five names are used in production.",
        ("fair",),
        None,
        "simple_storage.py:56; application in Climate.anomalies; "
        "production names from dscim-research "
        "main/run_integration_result.py:183-190",
        status="unsupported",
        reason="Climate.anomalies assigns the result of Dataset.update, "
        "which returns None on current xarray, so every masked run "
        "crashes with TypeError before computing anything; masking "
        "worked only with the older xarray where update returned the "
        "dataset.",
        restriction="library",
        modes=("ssp",),
        values=tuple(_v(m) for m in KNOWN_ECS_MASKS),
        open_set=True,
    ),
    Option(
        "base_period",
        "GMST rebasing window.",
        ("fair",),
        (2001, 2010),
        "simple_storage.py:57",
    ),
    Option(
        "emission_scenarios",
        "RCP/SSP scenarios to select from the FaIR files; must be null "
        "for runid-shaped (RFF) files.",
        ("fair",),
        ("ssp119", "ssp126", "ssp245", "ssp460", "ssp370", "ssp585"),
        "simple_storage.py:58 (default expansion :61-69)",
    ),
    Option(
        "gases",
        "Gas labels to select; must match the FaIR file's gas coordinate exactly.",
        ("fair",),
        ("CO2_Fossil", "CH4", "N2O"),
        "simple_storage.py:59,70-71",
    ),
    Option(
        "gas_conversions",
        "Pulse-to-tonne conversion factors per gas, given inline instead "
        "of a conversion netCDF. The file dscim reads is generated from "
        "these values at {paths.results}/gas_conversions.nc4. Exactly one "
        "of gas_conversions and damages_pulse_conversion_path must be "
        "set.",
        ("fair",),
        None,
        "consumed via simple_storage.py conversion; inline factors follow "
        "dscim-facts-epa (scghg_utils.py gas_conversions)",
    ),
    # ------------------------------------------------------------------
    # Econ (simple_storage.py EconVars)
    # ------------------------------------------------------------------
    Option(
        "path_econ",
        "Socioeconomics file (gdp and pop variables); config key "
        "econ.path. Years to 2300 plus a runid dimension are what dscim "
        "duck-types as RFF data.",
        ("econ",),
        REQUIRED,
        "simple_storage.py (EconVars); rff detection in "
        "main_recipe.py global_consumption",
    ),
    # ------------------------------------------------------------------
    # Reduce (preprocessing.py:74-92)
    # ------------------------------------------------------------------
    Option(
        "reduction",
        "Which counterfactual to reduce.",
        ("reduce",),
        REQUIRED,
        "preprocessing.py (reduce_damages); accepted set in ce_from_chunk",
        modes=("ssp",),
        values=(_v("cc"), _v("no_cc")),
    ),
    Option(
        "zero",
        "Zero out histclim in the no_cc reduction.",
        ("reduce",),
        False,
        "preprocessing.py:81 (reduce_damages signature)",
        modes=("ssp",),
    ),
    Option(
        "quantreg",
        "Keep the batch dimension through reduction for quantile regression.",
        ("reduce",),
        False,
        "preprocessing.py:83; adding_up-only behavior in ce_from_chunk; "
        "risk_aversion assert preprocessing.py:91-92",
        status="unsupported",
        reason="Only affects the adding_up branch (risk_aversion asserts "
        "against it) and keeps batch in the reduced output, a layout "
        "consumed only by quantile-regression fits (see fit_type: "
        "quantreg).",
        restriction="specification",
        modes=("ssp",),
    ),
    # ------------------------------------------------------------------
    # Combine (midprocessing.py:7-19)
    # ------------------------------------------------------------------
    Option(
        "combine_fit",
        "Also merge the fitted-values files when combining CAMEL "
        "coefficients (midprocessing parameter name: fit).",
        ("combine",),
        True,
        "midprocessing.py:18; rebinding midprocessing.py (coefs, fit = {}, {})",
        status="dead",
        reason="combine_CAMEL_coefs rebinds fit to an empty dict before "
        "testing it (`coefs, fit = {}, {}` then `if fit:`), so the "
        "fitted-values merge does not run for any argument value.",
        restriction="library",
        modes=("ssp",),
    ),
    # ------------------------------------------------------------------
    # Removed surface (not on dscim main)
    # ------------------------------------------------------------------
    Option(
        "geography",
        "Regional aggregation level (ir/country/globe).",
        ("fit",),
        None,
        "absent from main (MainRecipe.__init__ main_recipe.py:77-110); "
        "exists on generalize_df_fit and the harmonize branch",
        status="removed",
        reason="Absent from dscim main's MainRecipe; the regional surface "
        "exists only on the generalize_df_fit and harmonize branches.",
        restriction="specification",
    ),
    Option(
        "individual_region",
        "Single-region subsetting used by the regional-SCC SLURM fan-out.",
        ("fit",),
        None,
        "absent from main; consumed on generalize_df_fit "
        "(regional-scc data/SCCs/3_ir_sccs.py)",
        status="removed",
        reason="Not on dscim main.",
        restriction="specification",
    ),
    Option(
        "country_mapping_path",
        "ISO mapping CSV for country aggregation (named country_ISOs on "
        "generalize_df_fit).",
        ("fit",),
        None,
        "absent from main; named country_ISOs on generalize_df_fit",
        status="removed",
        reason="Not on dscim main.",
        restriction="specification",
    ),
)

CATALOGUE: dict[str, Option] = {opt.name: opt for opt in _OPTIONS}

COMPATIBILITY: tuple[Combination, ...] = (
    Combination(
        key="median-params-fair-dims",
        options=("fair_aggregation", "fair_dims"),
        kind="requires",
        description=(
            "fair_aggregation containing median_params requires fair_dims "
            "to be exactly [simulation]; dscim documents this and does not "
            "enforce it."
        ),
        citation="main_recipe.py:47 (docstring); no matching assert in __init__",
    ),
    Combination(
        key="clip-gmsl-formula",
        options=("clip_gmsl", "formula"),
        kind="requires",
        description=(
            "clip_gmsl requires the formula to be one of the two "
            "gmsl-quadratic formulas."
        ),
        citation="main_recipe.py:264-270 (assert)",
    ),
    Combination(
        key="equity-not-reduced",
        options=("recipe",),
        kind="forbidden",
        description=(
            "reduce.recipes may not include equity: reduce_damages has no "
            "equity branch, and the equity recipe reads risk_aversion "
            "reduced damages. Add risk_aversion to reduce.recipes instead."
        ),
        citation="preprocessing.py (ce_from_chunk has adding_up and "
        "risk_aversion branches only); equity.py reads risk_aversion CEs",
        modes=("ssp",),
    ),
    Combination(
        key="rff-emission-scenarios-null",
        options=("emission_scenarios",),
        kind="requires",
        description=(
            "rff mode requires climate.emission_scenarios to be null so "
            "the rcp selection is skipped on runid-shaped FaIR files."
        ),
        citation="simple_storage.py:58 docstring",
        modes=("rff",),
    ),
    Combination(
        key="rff-coefficients-required",
        options=("damage_function_path",),
        kind="requires",
        description=(
            "rff mode requires damage_function_path on every swept "
            "sector: ce_path is None in rff runs, so fitting is "
            "impossible and coefficients must be precomputed."
        ),
        citation="utils/menu_runs.py:163-167 (run_rff)",
        modes=("rff",),
    ),
    Combination(
        key="rff-no-masks-or-fair-dims",
        options=("ecs_mask_name", "fair_dims"),
        kind="forbidden",
        description=(
            "sweep.masks and sweep.fair_dims are not available in rff "
            "mode; run_rff has no such parameters and forces the mask "
            "off."
        ),
        citation="utils/menu_runs.py:119-127,169-170",
        modes=("rff",),
    ),
    Combination(
        key="ssp-gmst-path-required",
        options=("gmst_path",),
        kind="requires",
        description=(
            "ssp mode requires a non-empty climate.gmst_path: damage "
            "points are merged with the GMST anomalies during fitting."
        ),
        citation="main_recipe.py damage_function_points (gmst merge)",
        modes=("ssp",),
    ),
    Combination(
        key="gmsl-formula-needs-gmsl-paths",
        options=("formula", "gmsl_path", "gmsl_fair_path"),
        kind="requires",
        description=(
            "a swept sector whose formula contains gmsl requires "
            "climate.gmsl_path (ssp fitting) and climate.gmsl_fair_path."
        ),
        citation="main_recipe.py (gmsl merge keyed on slr/gmsl columns); "
        "simple_storage.py:54 (anomaly_vars gate)",
    ),
    Combination(
        key="quantreg-lengths",
        options=("quantreg_quantiles", "quantreg_weights"),
        kind="requires",
        description=(
            "quantreg_quantiles and quantreg_weights must have equal "
            "length (dscim asserts this even though the weights are "
            "otherwise unused)."
        ),
        citation="main_recipe.py:241-243",
    ),
)


def option(name: str) -> Option:
    """Look up a catalogued option by name."""
    return CATALOGUE[name]
