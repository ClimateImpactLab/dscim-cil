"""Config validation and sweep expansion tests. No xarray, no dscim."""

import pytest

from dscim_cil.config import (
    ConfigError,
    apply_overrides,
    apply_selectors,
    expand_sweep,
    plan_steps,
    render_summary,
    resolved_config,
    run_inputs,
    run_outputs,
    save_path_for,
    validate_config,
)


def ssp_config() -> dict:
    return {
        "mode": "ssp",
        "climate": {
            "gases": ["CO2_Fossil"],
            "gmst_path": "/c/gmst.csv",
            "gmsl_path": "/c/gmsl.zarr",
            "gmst_fair_path": "/c/fair.nc",
            "gmsl_fair_path": "/c/fair_gmsl.zarr",
            "damages_pulse_conversion_path": "/c/conversion.nc4",
            "emission_scenarios": ["ssp245", "ssp370"],
        },
        "econ": {"path": "/e/econ.zarr"},
        "paths": {
            "reduced_damages_library": "/r/reduced",
            "results": "/r/results",
        },
        "sectors": {
            "coastal_v0.20": {
                "sector_path": "/d/coastal.zarr",
                "histclim": "histclim",
                "delta": "delta",
                "formula": "damages ~ -1 + gmsl + np.power(gmsl, 2)",
            },
            "AMEL_m0": {
                "sector_path": "/d/amel.zarr",
                "histclim": "summed_histclim",
                "delta": "summed_delta",
                "formula": "damages ~ -1 + anomaly + np.power(anomaly, 2)",
            },
        },
        "menu": {"fit_type": "ols"},
        "sweep": {
            "sectors": ["AMEL_m0", "coastal_v0.20"],
            "pulse_years": [2020],
            "menu_pairs": [
                {"recipe": "adding_up", "discounting": "euler_ramsey"},
                {"recipe": "risk_aversion", "discounting": "euler_ramsey"},
            ],
            "eta_rho": [[2.0, 0.0001]],
            "masks": [None],
            "fair_dims": [["simulation"]],
        },
        "reduce": {"reductions": ["cc", "no_cc"], "recipes": ["adding_up"]},
    }


def rff_config() -> dict:
    return {
        "mode": "rff",
        "climate": {
            "gases": ["CO2_Fossil"],
            "gmst_path": "",
            "gmsl_path": "",
            "gmst_fair_path": "/i/gmst_pulse.nc4",
            "gmsl_fair_path": "/i/gmsl_pulse.nc4",
            "damages_pulse_conversion_path": "/i/conversion.nc4",
            "emission_scenarios": None,
        },
        "econ": {"path": "/i/rff_global_socioeconomics.nc4"},
        "paths": {"results": "/r/rff"},
        "sectors": {
            "CAMEL_m1_c0.20": {
                "formula": (
                    "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + "
                    "np.power(gmsl, 2)"
                ),
                "damage_function_path": "/i/dfs/CAMEL_m1_c0.20",
            }
        },
        "menu": {
            "fair_aggregation": [],
            "save_files": ["uncollapsed_sccs"],
        },
        "sweep": {
            "sectors": ["CAMEL_m1_c0.20"],
            "pulse_years": [2020, 2030],
            "menu_pairs": [{"recipe": "risk_aversion", "discounting": "euler_ramsey"}],
            "eta_rho": [[1.421158116, 0.00461878399]],
        },
    }


def errors_of(config: dict, **kwargs) -> str:
    with pytest.raises(ConfigError) as excinfo:
        validate_config(config, **kwargs)
    return "\n".join(excinfo.value.errors)


def test_valid_configs_pass():
    assert validate_config(ssp_config()) == []
    assert validate_config(rff_config()) == []


def test_override_precedence_yaml_then_conf():
    config = apply_overrides(ssp_config(), overrides=["sweep.pulse_years=[2030]"])
    assert config["sweep"]["pulse_years"] == [2030]
    assert ssp_config()["sweep"]["pulse_years"] == [2020]


def test_override_parses_yaml_scalars():
    config = apply_overrides(
        ssp_config(), overrides=["climate.ecs_mask_path=null", "menu.clip_gmsl=true"]
    )
    assert config["climate"]["ecs_mask_path"] is None
    assert config["menu"]["clip_gmsl"] is True


def test_override_requires_key_value_shape():
    with pytest.raises(ConfigError, match="KEY=VALUE"):
        apply_overrides(ssp_config(), overrides=["no-equals-sign"])


def test_mode_is_required_and_explicit():
    config = ssp_config()
    del config["mode"]
    assert "2300" in errors_of(config)


def test_unknown_top_level_key_suggests():
    config = ssp_config()
    config["sweeps"] = config.pop("sweep")
    assert "did you mean 'sweep'" in errors_of(config)


def test_malformed_formula_names_whitelist_and_suggests():
    config = ssp_config()
    config["sectors"]["AMEL_m0"]["formula"] = (
        "damages ~ -1 anomaly + np.power(anomaly, 2)"  # real case: missing '+'
    )
    message = errors_of(config)
    assert "12 formulas" in message
    assert "did you mean" in message


def test_constant_gwr_blocked_with_reason_and_citation():
    config = ssp_config()
    config["sweep"]["menu_pairs"] = [
        {"recipe": "adding_up", "discounting": "constant_gwr"}
    ]
    message = errors_of(config)
    assert "UnboundLocalError" in message
    assert "--allow-unsupported" in message


def test_allow_unsupported_downgrades_to_warning():
    config = ssp_config()
    config["sweep"]["menu_pairs"] = [
        {"recipe": "adding_up", "discounting": "constant_gwr"}
    ]
    warnings = validate_config(config, allow_unsupported=True)
    assert any("constant_gwr" in w for w in warnings)


def test_quantreg_blocked_but_allowed_with_flag():
    config = ssp_config()
    config["menu"]["fit_type"] = "quantreg"
    assert "risk_aversion" in errors_of(config)
    assert validate_config(config, allow_unsupported=True)


def test_uncollapsed_is_not_a_fair_aggregation_member():
    config = ssp_config()
    config["menu"]["fair_aggregation"] = ["uncollapsed"]
    message = errors_of(config)
    assert "scc" in message
    assert "NotImplementedError" in message


def test_median_params_requires_simulation_fair_dims():
    config = ssp_config()
    config["menu"]["fair_aggregation"] = ["median_params"]
    config["sweep"]["fair_dims"] = [["simulation"], ["simulation", "rcp"]]
    assert "median_params" in errors_of(config)


def test_clip_gmsl_requires_gmsl_quadratic_formula():
    config = ssp_config()
    config["menu"]["clip_gmsl"] = True
    assert "clip_gmsl" in errors_of(config)  # AMEL_m0 formula is anomaly-only


def test_equity_cannot_be_reduced():
    config = ssp_config()
    config["reduce"]["recipes"] = ["equity"]
    assert "risk_aversion" in errors_of(config)


def test_rff_requires_null_emission_scenarios():
    config = rff_config()
    config["climate"]["emission_scenarios"] = ["ssp245"]
    assert "emission_scenarios" in errors_of(config)


def test_rff_requires_coefficients_per_sector():
    config = rff_config()
    del config["sectors"]["CAMEL_m1_c0.20"]["damage_function_path"]
    message = errors_of(config)
    assert "damage_function_path" in message
    assert "ce_path" in message


def test_rff_rejects_mask_and_fair_dims_axes():
    config = rff_config()
    config["sweep"]["masks"] = [None]
    assert "rff" in errors_of(config)


def test_rff_rejects_reduce_block():
    config = rff_config()
    config["reduce"] = {"reductions": ["cc"], "recipes": ["adding_up"]}
    assert "reduce" in errors_of(config)


def test_removed_regional_surface_is_a_known_gap_error():
    config = ssp_config()
    config["menu"]["geography"] = "ir"
    assert "generalize_df_fit" in errors_of(config)


def test_sweep_expansion_count_and_axes():
    config = ssp_config()
    config["sweep"]["masks"] = [None, "truncate_at_ecs995symmetric_passing_mask"]
    runs = expand_sweep(config)
    # 2 sectors x 1 pulse year x 2 pairs x 1 eta_rho x 2 masks x 1 fair_dims
    assert len(runs) == 8
    masks = {run.mask for run in runs}
    assert masks == {None, "truncate_at_ecs995symmetric_passing_mask"}


def test_masked_sweep_is_unsupported_but_overridable():
    config = ssp_config()
    config["sweep"]["masks"] = [None, "truncate_at_ecs995symmetric_passing_mask"]
    message = errors_of(config)
    assert "Dataset.update" in message
    warnings = validate_config(config, allow_unsupported=True)
    assert any("mask" in w for w in warnings)


def test_rff_expansion_has_no_mask_axis():
    runs = expand_sweep(rff_config())
    assert len(runs) == 2  # 2 pulse years
    assert all(run.mask is None for run in runs)


def test_save_path_mask_and_fair_dims_layout():
    config = ssp_config()
    config["sweep"]["masks"] = [None, "truncate_at_ecs995symmetric_passing_mask"]
    config["sweep"]["fair_dims"] = [["simulation", "rcp"]]
    runs = expand_sweep(config)
    masked = next(run for run in runs if run.mask)
    path = save_path_for(config, masked)
    assert path.endswith("truncate_at_ecs995symmetric_passing_mask/fair_collapsed_rcp")
    assert "/AMEL_m0/2020/" in path or "/coastal_v0.20/2020/" in path


def test_reduced_input_naming_matches_dscim_main():
    config = ssp_config()
    runs = expand_sweep(config)
    adding_up = next(run for run in runs if run.recipe == "adding_up")
    risky = next(run for run in runs if run.recipe == "risk_aversion")
    adding_inputs = "\n".join(i.path for i in run_inputs(config, adding_up))
    risky_inputs = "\n".join(i.path for i in run_inputs(config, risky))
    assert "adding_up_cc.zarr" in adding_inputs  # unsuffixed on main
    assert "risk_aversion_cc_eta2.0.zarr" in risky_inputs


def test_reduced_inputs_name_their_producer():
    config = ssp_config()
    run = expand_sweep(config)[0]
    producers = {i.path: i.producer for i in run_inputs(config, run)}
    reduced = [p for p in producers if p.endswith(".zarr") and "reduced" in p]
    assert reduced
    assert all(producers[p] == "reduce" for p in reduced)
    climate = [p for p in producers if "fair" in p or "gmst" in p]
    assert all(producers[p] == "" for p in climate)


def test_gmsl_inputs_only_for_gmsl_sectors():
    config = ssp_config()
    runs = expand_sweep(config)
    amel = next(r for r in runs if r.sector == "AMEL_m0")
    coastal = next(r for r in runs if r.sector == "coastal_v0.20")
    amel_paths = "\n".join(i.path for i in run_inputs(config, amel))
    coastal_paths = "\n".join(i.path for i in run_inputs(config, coastal))
    assert "gmsl" not in amel_paths  # anomaly-only formula
    assert "fair_gmsl.zarr" in coastal_paths
    assert "/c/gmsl.zarr" in coastal_paths


def test_rff_inputs_include_coefficient_file_marked_external():
    config = rff_config()
    run = expand_sweep(config)[0]
    inputs = run_inputs(config, run)
    coefficient = next(i for i in inputs if "damage_function_coefficients" in i.path)
    assert (
        "risk_aversion_euler_ramsey_eta1.421158116_rho0.00461878399"
        "_damage_function_coefficients.nc4" in coefficient.path
    )
    assert coefficient.producer == ""  # precomputed, external in rff


def test_outputs_follow_save_decorator_naming():
    config = rff_config()
    run = expand_sweep(config)[0]
    outputs = run_outputs(config, run)
    assert len(outputs) == 1
    assert outputs[0].endswith(
        "risk_aversion_euler_ramsey_eta1.421158116_rho0.00461878399"
        "_uncollapsed_sccs.nc4"
    )


def test_points_artifact_is_csv():
    config = ssp_config()
    config["menu"]["save_files"] = ["damage_function_points", "scc"]
    run = expand_sweep(config)[0]
    extensions = {path.rsplit(".", 1)[1] for path in run_outputs(config, run)}
    assert extensions == {"csv", "nc4"}


def test_selectors_filter_configured_sweep():
    config = apply_selectors(ssp_config(), sectors=("AMEL_m0",), recipes=("adding_up",))
    sweep = config["sweep"]
    assert sweep["sectors"] == ["AMEL_m0"]
    assert sweep["menu_pairs"] == [
        {"recipe": "adding_up", "discounting": "euler_ramsey"}
    ]


def test_selectors_outside_sweep_error():
    with pytest.raises(ConfigError, match="matches nothing"):
        apply_selectors(ssp_config(), sectors=("nonexistent",))


def test_selectors_define_missing_sweep_axes():
    config = ssp_config()
    del config["sweep"]
    config = apply_selectors(
        config,
        sectors=("AMEL_m0",),
        pulse_years=(2020,),
        recipes=("adding_up",),
        discountings=("euler_ramsey",),
        eta=2.0,
        rho=0.0001,
    )
    assert validate_config(config) == []
    assert len(expand_sweep(config)) == 1


def test_selectors_eta_requires_rho():
    with pytest.raises(ConfigError, match="together"):
        apply_selectors(ssp_config(), eta=2.0)


def test_selectors_mask_unmasked_maps_to_none():
    config = apply_selectors(ssp_config(), masks=("unmasked",))
    assert config["sweep"]["masks"] == [None]


def test_resolved_config_fills_only_non_scientific_defaults():
    resolved = resolved_config(ssp_config())
    menu = resolved["menu"]
    assert menu["ext_method"] == "global_c_ratio"
    assert menu["weitzman_parameter"] == [0.1, 0.5]
    assert menu["discrete_discounting"] is False
    # scientific selections are never filled
    assert "eta" not in menu
    assert "rho" not in menu
    assert "discounting_type" not in menu
    assert resolved["climate"]["base_period"] == [2001, 2010]


def test_render_summary_groups_missing_by_producer():
    config = ssp_config()
    runs = expand_sweep(config)
    report = render_summary(config, runs)
    assert f"runs: {len(runs)}" in report
    assert "external: provide these files" in report
    assert "produced by `dscim-cil reduce CONFIG`" in report
    assert f"blocked runs: {len(runs)} of {len(runs)}" in report
    assert "--verbose" in report


def test_plan_steps_order_and_producers():
    config = ssp_config()
    config["aggregates"] = {"AMEL_m0": ["coastal_v0.20"]}
    config["sectors"]["CAMEL_x"] = {
        "formula": (
            "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)"
        ),
        "damage_function_path": "/r/results/CAMEL_x/2020/unmasked",
    }
    config["sweep"]["sectors"].append("CAMEL_x")
    config["combine"] = {
        "target": "CAMEL_x",
        "coastal": "coastal_v0.20",
        "amel": "AMEL_m0",
    }
    assert validate_config(config) == []
    steps = plan_steps(config)
    names = [s.name for s in steps]
    assert names == ["sum-sectors", "reduce", "run", "combine", "run"]
    combine_step = steps[3]
    assert all(i.producer == "run" for i in combine_step.inputs)
    coefficient_run = steps[4]
    target_inputs = [i for i in coefficient_run.inputs if "coefficients" in i.kind]
    assert all(i.producer == "combine" for i in target_inputs)
    assert all("blocked-by-" in s.status() for s in steps)


def test_combine_block_validation():
    config = ssp_config()
    config["combine"] = {
        "target": "AMEL_m0",
        "coastal": "coastal_v0.20",
        "amel": "AMEL_m0",
    }
    assert "coefficient-only" in errors_of(config)


def test_combine_rejected_in_rff():
    config = rff_config()
    config["combine"] = {
        "target": "CAMEL_m1_c0.20",
        "coastal": "CAMEL_m1_c0.20",
        "amel": "CAMEL_m1_c0.20",
    }
    assert "rff" in errors_of(config)


def test_settings_summary_separates_config_from_default():
    from dscim_cil.config import settings_summary

    report = settings_summary(ssp_config())
    assert "settings:" in report
    eta_line = next(
        line for line in report.splitlines() if line.strip().startswith("eta ")
    )
    assert "(config)" in eta_line
    fit_line = next(
        line for line in report.splitlines() if line.strip().startswith("fit_type")
    )
    assert "(config)" in fit_line  # ssp_config sets fit_type explicitly
    ext_line = next(
        line for line in report.splitlines() if line.strip().startswith("ext_method")
    )
    assert "(default)" in ext_line


def test_settings_summary_marks_flag_sources():
    from dscim_cil.config import settings_summary

    config = apply_selectors(ssp_config(), sectors=("AMEL_m0",))
    report = settings_summary(config, sources={"sweep.sectors": "flag"})
    sector_line = next(
        line for line in report.splitlines() if line.strip().startswith("sector ")
    )
    assert "(flag)" in sector_line


def test_effective_settings_without_config_shows_requirements():
    from dscim_cil.config import effective_settings

    rows = {name: (value, origin) for name, value, origin in effective_settings(None)}
    assert rows["eta"] == (1.421158116, "required: you must set this")
    assert rows["fit_type"][1] == "default"
    assert rows["scc_quantiles"][1] == "dead"
    assert rows["geography"][1] == "removed"


def test_config_provenance_covers_defaults():
    from dscim_cil.config import config_provenance

    provenance = config_provenance(ssp_config())
    assert provenance["ext_method"] == "default"
    assert provenance["eta"] == "config"
    assert provenance["weitzman_parameter"] == "default"


def test_scc_validation_rules():
    config = rff_config()
    config["scc"] = {"output": "/o", "collapse": "mean", "deflator": 1.0}
    message = errors_of(config)  # save_files lacks the uncollapsed pair
    assert "uncollapsed_marginal_damages" in message

    config = rff_config()
    config["menu"]["save_files"] = [
        "uncollapsed_marginal_damages",
        "uncollapsed_discount_factors",
    ]
    config["scc"] = {"output": "/o", "collapse": "certainty_equivalent"}
    message = errors_of(config)
    assert "global_consumption_no_pulse" in message

    config = rff_config()
    config["menu"]["save_files"] = [
        "uncollapsed_marginal_damages",
        "uncollapsed_discount_factors",
    ]
    config["scc"] = {"output": "/o", "collapse": "mean", "inputs": "/x"}
    assert "unknown scc key" in errors_of(config)


def test_gas_conversions_replaces_conversion_file():
    config = rff_config()
    del config["climate"]["damages_pulse_conversion_path"]
    config["climate"]["gas_conversions"] = {"CO2_Fossil": 2.72916487e-10}
    assert validate_config(config) == []


def test_gas_conversions_and_file_are_exclusive():
    config = rff_config()
    config["climate"]["gas_conversions"] = {"CO2_Fossil": 1e-10}
    assert "exactly one" in errors_of(config)
    del config["climate"]["damages_pulse_conversion_path"]
    del config["climate"]["gas_conversions"]
    assert "exactly one" in errors_of(config)


def test_gas_conversions_must_cover_selected_gases():
    config = rff_config()
    del config["climate"]["damages_pulse_conversion_path"]
    config["climate"]["gas_conversions"] = {"CH4": 2.5e-08}
    message = errors_of(config)
    assert "CO2_Fossil" in message
    config["climate"]["gas_conversions"] = {"CO2_Fossil": -1.0}
    assert "positive" in errors_of(config)
