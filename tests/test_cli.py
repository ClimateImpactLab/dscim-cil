"""CLI behavior tests via click's runner."""

import pathlib

import yaml
from click.testing import CliRunner

from dscim_cil.cli import main

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"


def invoke(*args: str, env: dict | None = None):
    return CliRunner().invoke(main, list(args), env=env)


def test_all_example_configs_validate():
    for name in ("ssp.yaml", "rff.yaml", "minimal.yaml"):
        result = invoke("validate", str(EXAMPLES / name))
        assert result.exit_code == 0, result.output
        assert "config is valid" in result.output


def test_dry_run_default_is_summary(tmp_path):
    result = invoke("run", str(EXAMPLES / "ssp.yaml"), "--dry-run")
    assert result.exit_code == 0, result.output
    assert "runs: 6" in result.output
    assert "missing inputs:" in result.output
    assert "external: provide these files" in result.output
    assert "produced by `dscim-cil reduce CONFIG`" in result.output
    assert "blocked runs:" in result.output
    # summary, not per-run detail
    assert "[1] sector=" not in result.output


def test_dry_run_verbose_gives_per_run_detail(tmp_path):
    config = yaml.safe_load((EXAMPLES / "rff.yaml").read_text())
    present = tmp_path / "gmst_pulse.nc4"
    present.touch()
    config["climate"]["gmst_fair_path"] = str(present)
    config_path = tmp_path / "conf.yaml"
    config_path.write_text(yaml.safe_dump(config))

    result = invoke("run", str(config_path), "--dry-run", "--verbose")
    assert result.exit_code == 0, result.output
    assert "[1] sector=" in result.output
    assert f"in  [ok] {present}" in result.output
    assert "MISSING (external)" in result.output
    assert "uncollapsed_sccs.nc4" in result.output


def test_dry_run_runs_selection(tmp_path):
    result = invoke("run", str(EXAMPLES / "ssp.yaml"), "--dry-run", "--runs", "2")
    assert result.exit_code == 0, result.output
    assert "[2] sector=" in result.output
    assert "[1] sector=" not in result.output


def test_dry_run_missing_reduced_names_producer():
    result = invoke("run", str(EXAMPLES / "minimal.yaml"), "--dry-run", "--verbose")
    assert result.exit_code == 0, result.output
    assert "MISSING -> dscim-cil reduce" in result.output


def test_selector_flags_narrow_sweep():
    result = invoke(
        "run",
        str(EXAMPLES / "ssp.yaml"),
        "--dry-run",
        "--sector",
        "AMEL_m0",
        "--recipe",
        "adding_up",
        "--mask",
        "unmasked",
    )
    assert result.exit_code == 0, result.output
    assert "runs: 1 " in result.output


def test_selector_outside_sweep_fails():
    result = invoke("run", str(EXAMPLES / "ssp.yaml"), "--dry-run", "--sector", "nope")
    assert result.exit_code == 1
    assert "matches nothing" in result.output


def test_run_without_dry_run_needs_dscim_or_preflight():
    result = invoke("run", str(EXAMPLES / "rff.yaml"))
    assert result.exit_code == 1
    assert "error" in result.output


def test_dry_run_surfaces_validation_errors(tmp_path):
    config = yaml.safe_load((EXAMPLES / "rff.yaml").read_text())
    config["climate"]["emission_scenarios"] = ["ssp245"]
    config_path = tmp_path / "conf.yaml"
    config_path.write_text(yaml.safe_dump(config))

    result = invoke("run", str(config_path), "--dry-run")
    assert result.exit_code == 1
    assert "emission_scenarios" in result.output


def test_conf_override_reaches_validation():
    result = invoke(
        "validate", str(EXAMPLES / "rff.yaml"), "-c", "sweep.pulse_years=[2020]"
    )
    assert result.exit_code == 0


def test_envvar_prefix_is_active():
    result = invoke(
        "run",
        str(EXAMPLES / "ssp.yaml"),
        env={"DSCIM_CIL_RUN_DRY_RUN": "1"},
    )
    assert result.exit_code == 0, result.output
    assert "runs: 6" in result.output


def test_plan_lists_ordered_steps_with_status():
    result = invoke("plan", str(EXAMPLES / "ssp.yaml"))
    assert result.exit_code == 0, result.output
    assert "1. [blocked-by-" in result.output
    assert "sum-sectors: build AMEL_m0" in result.output
    assert "reduce: collapse batch" in result.output
    assert "<- dscim-cil reduce" in result.output


def test_stages_explains_dimension_collapses():
    result = invoke("stages")
    assert result.exit_code == 0
    assert "reduce" in result.output
    assert "batch: mean for adding_up" in result.output
    assert "ssp and model: collapsed when discounting contains gwr" in result.output
    assert "main_recipe.py" in result.output
    assert "runid" in result.output


def test_options_marks_config_required():
    result = invoke("options")
    assert result.exit_code == 0
    assert "required in config" in result.output


def test_explain_shows_dscim_default_for_config_required():
    result = invoke("explain", "eta")
    assert result.exit_code == 0
    assert "required in config" in result.output
    assert "1.421158116" in result.output
    assert "never applies that silently" in result.output


def test_explain_shows_value_status_and_citation():
    result = invoke("explain", "discounting_type", "constant_gwr")
    assert result.exit_code == 0
    assert "unsupported" in result.output
    assert "UnboundLocalError" in result.output
    assert "main_recipe.py" in result.output


def test_explain_unknown_option_suggests():
    result = invoke("explain", "discounting")
    assert result.exit_code == 1
    assert "discounting_type" in result.output


def test_constraints_lists_rules_with_citations():
    result = invoke("constraints")
    assert result.exit_code == 0
    assert "median-params-fair-dims" in result.output
    assert "rff-coefficients-required" in result.output
    assert "source:" in result.output


def test_run_prints_settings_with_provenance():
    result = invoke("run", str(EXAMPLES / "minimal.yaml"), "--dry-run")
    assert result.exit_code == 0, result.output
    assert "settings:" in result.output
    assert "(config)" in result.output
    assert "(default)" in result.output  # minimal.yaml sets no menu options


def test_run_settings_mark_flag_origin():
    result = invoke(
        "run", str(EXAMPLES / "ssp.yaml"), "--dry-run", "--sector", "AMEL_m0"
    )
    assert result.exit_code == 0, result.output
    assert "(flag)" in result.output


def test_defaults_without_config_shows_dscim_defaults():
    result = invoke("defaults")
    assert result.exit_code == 0
    assert "required: you must set this" in result.output
    assert "1.421158116" in result.output
    assert "global_c_ratio" in result.output


def test_defaults_with_config_shows_origins():
    result = invoke("defaults", str(EXAMPLES / "minimal.yaml"))
    assert result.exit_code == 0, result.output
    eta_line = next(
        line for line in result.output.splitlines() if line.startswith("eta ")
    )
    assert "(config)" in eta_line
    ext_line = next(
        line for line in result.output.splitlines() if line.startswith("ext_method")
    )
    assert "(default)" in ext_line


def test_scc_command_requires_block():
    result = invoke("scc", str(EXAMPLES / "minimal.yaml"))
    assert result.exit_code == 1
    assert "no scc block" in result.output


def test_output_is_plain_when_not_a_terminal():
    # CliRunner streams are not terminals, so auto-detection gives the
    # same output as the explicit flag and the environment variable.
    default = invoke("stages")
    flagged = invoke("--plain", "stages")
    via_env = invoke("stages", env={"DSCIM_CIL_PLAIN": "1"})
    assert default.output == flagged.output == via_env.output
    assert "\x1b[" not in default.output  # no control characters


def test_rich_path_renders_stages_tree(monkeypatch):
    from dscim_cil import cli as cli_module

    monkeypatch.setattr(cli_module, "_stdout_is_terminal", lambda: True)
    result = invoke("stages")
    assert result.exit_code == 0, result.output
    assert "pipeline" in result.output
    assert "sum-sectors" in result.output
    assert "├──" in result.output  # tree guides


def test_rich_path_renders_plan_with_status_words(monkeypatch):
    from dscim_cil import cli as cli_module

    monkeypatch.setattr(cli_module, "_stdout_is_terminal", lambda: True)
    result = invoke("plan", str(EXAMPLES / "ssp.yaml"))
    assert result.exit_code == 0, result.output
    # the status words carry the state without colour
    assert "[blocked-by-" in result.output
    assert "[missing]" in result.output
