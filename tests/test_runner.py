"""Integration tests: runner vs direct dscim calls on tiny fixtures.

Skipped when dscim is not installed.
"""

import os
import pathlib

import pytest

dscim = pytest.importorskip("dscim")
xr = pytest.importorskip("xarray")

import dask
import fixture_factory
import numpy as np
import yaml

from dscim_cil import runner
from dscim_cil.config import expand_sweep, run_outputs, validate_config

dask.config.set(scheduler="single-threaded")

pytestmark = pytest.mark.integration

RECIPES = ("adding_up", "risk_aversion", "equity")
DISCOUNTINGS = ("euler_ramsey", "constant", "naive_gwr")


@pytest.fixture(scope="module")
def ssp_setup(tmp_path_factory):
    root = tmp_path_factory.mktemp("ssp_fixtures")
    config = fixture_factory.ssp_fixture_config(root, etas=(2.0,))
    assert validate_config(config) == []
    return config


def _single_run_config(config: dict, recipe: str, discounting: str) -> dict:
    narrowed = yaml.safe_load(yaml.safe_dump(config))
    narrowed["sweep"]["menu_pairs"] = [{"recipe": recipe, "discounting": discounting}]
    return narrowed


# Dimensions along which a healthy SCC should not be constant, checked
# whenever the output actually carries them with more than one entry.
VARYING_DIMS = ("rcp", "ssp", "model", "fair_aggregation", "discrate", "runid")


def _assert_not_degenerate(data, *, varying=VARYING_DIMS):
    """Require finite, non-zero, non-constant values that vary along
    the given dimensions."""
    values = np.asarray(data.values, dtype=float)
    assert np.isfinite(values).all(), "non-finite values in result"
    assert (values != 0).any(), "result is identically zero"
    if values.size > 1:
        assert float(values.std()) > 0, "result is a single repeated value"
    for dim in varying:
        if data.sizes.get(dim, 1) > 1:
            spread = float(data.std(dim).max())
            assert spread > 0, f"no variation across {dim}"


def _assert_scc_equivalence(config):
    runs = expand_sweep(config)
    assert len(runs) == 1
    run = runs[0]

    lines = runner.execute(config, runs, invocation="test")
    assert lines and lines[0].startswith("completed")

    scc_file = next(p for p in run_outputs(config, run) if p.endswith("_scc.nc4"))
    written = xr.open_dataset(scc_file)
    _assert_not_degenerate(written["scc"])

    direct_kwargs = runner.build_kwargs(config, run)
    direct_kwargs["save_path"] = None
    direct = runner.MENU[run.recipe](**direct_kwargs).calculate_scc
    if isinstance(direct, xr.DataArray):
        direct = direct.to_dataset(name="scc")

    xr.testing.assert_allclose(
        written[["scc"]], direct[["scc"]].transpose(*written["scc"].dims)
    )


@pytest.mark.parametrize("recipe", RECIPES)
@pytest.mark.parametrize("discounting", DISCOUNTINGS)
def test_runner_matches_direct_menu_call(ssp_setup, recipe, discounting):
    _assert_scc_equivalence(_single_run_config(ssp_setup, recipe, discounting))


EXTRA_DISCOUNTINGS = (
    "naive_ramsey",
    "constant_model_collapsed",
    "euler_gwr",
    "gwr_gwr",
)


@pytest.mark.parametrize("discounting", EXTRA_DISCOUNTINGS)
def test_additional_discountings_match_direct_call(ssp_setup, discounting):
    _assert_scc_equivalence(_single_run_config(ssp_setup, "adding_up", discounting))


def test_all_fair_aggregations_match_direct_call(ssp_setup):
    config = _single_run_config(ssp_setup, "adding_up", "euler_ramsey")
    config["menu"]["fair_aggregation"] = [
        "ce",
        "mean",
        "gwr_mean",
        "median",
        "median_params",
    ]
    _assert_scc_equivalence(config)


@pytest.mark.xfail(
    strict=True,
    raises=TypeError,
    reason="dscim Climate.anomalies assigns Dataset.update's return value, "
    "which is None on current xarray; delete this xfail and the "
    "ecs_mask_name unsupported status when fixed upstream",
)
def test_ecs_mask_crashes_in_dscim(ssp_setup, tmp_path):
    config = _single_run_config(ssp_setup, "adding_up", "euler_ramsey")
    config["climate"]["ecs_mask_path"] = fixture_factory.write_ecs_mask(tmp_path)
    config["sweep"]["masks"] = ["keep_first"]
    runner.execute(config, expand_sweep(config), invocation="test")


def test_fair_dims_collapse_matches_direct_call(ssp_setup):
    config = _single_run_config(ssp_setup, "adding_up", "euler_ramsey")
    config["menu"]["fair_aggregation"] = ["ce", "mean", "median"]
    config["sweep"]["fair_dims"] = [["simulation", "rcp"]]
    assert validate_config(config) == []
    _assert_scc_equivalence(config)
    run = expand_sweep(config)[0]
    assert "fair_collapsed_rcp" in run_outputs(config, run)[0]


@pytest.mark.full_matrix
@pytest.mark.skipif(
    not os.environ.get("DSCIM_CIL_FULL_MATRIX"),
    reason="set DSCIM_CIL_FULL_MATRIX=1 to run the full recipe x discounting cross",
)
@pytest.mark.parametrize("recipe", ("risk_aversion", "equity"))
@pytest.mark.parametrize("discounting", EXTRA_DISCOUNTINGS)
def test_full_matrix_matches_direct_call(ssp_setup, recipe, discounting):
    _assert_scc_equivalence(_single_run_config(ssp_setup, recipe, discounting))


def test_rff_run_produces_uncollapsed_outputs(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    assert validate_config(config) == []
    runs = expand_sweep(config)
    lines = runner.execute(config, runs, invocation="test")
    assert all(line.startswith("completed") for line in lines)
    for run in runs:
        for path in run_outputs(config, run):
            data = xr.open_dataset(path)
            for variable in data.data_vars:
                _assert_not_degenerate(data[variable])
        outputs = run_outputs(config, run)
        sccs = xr.open_dataset(next(p for p in outputs if "uncollapsed_sccs" in p))
        assert "runid" in sccs.dims
        _assert_not_degenerate(next(iter(sccs.data_vars.values())), varying=("runid",))


def test_resume_skips_completed_runs(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    runs = expand_sweep(config)
    first = runner.execute(config, runs, invocation="test")
    assert first[0].startswith("completed")
    second = runner.execute(config, runs, resume=True, invocation="test")
    assert second[0].startswith("skipped")
    third = runner.execute(config, runs, resume=False, invocation="test")
    assert third[0].startswith("completed")


def test_metadata_records_dscim_commit_and_resolved_config(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    runs = expand_sweep(config)
    lines = runner.execute(config, runs, invocation="dscim-cil run conf.yml")
    metadata_path = lines[0].split("metadata: ")[1].rstrip(")")
    with open(metadata_path) as stream:
        record = yaml.safe_load(stream)

    assert record["dscim_commit"] != "unknown"
    assert record["dscim_version"].startswith("0.")
    assert record["invocation"] == "dscim-cil run conf.yml"
    assert record["run"]["recipe"] == "risk_aversion"
    # resolved config makes non-scientific defaults explicit ...
    assert record["resolved_config"]["menu"]["ext_method"] == "global_c_ratio"
    assert record["resolved_config"]["menu"]["discrete_discounting"] is False
    # ... but never fills scientific selections
    assert "eta" not in record["resolved_config"]["menu"]
    assert record["started"] <= record["finished"]
    assert record["outputs"]
    assert record["dependencies"]["xarray"] != "not installed"


def test_preflight_rejects_wrong_pulse_year(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    config["sweep"]["pulse_years"] = [2035]
    runs = expand_sweep(config)
    with pytest.raises(runner.PreflightError, match="2035"):
        runner.preflight(config, runs)


def test_preflight_rejects_wrong_gas(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    config["climate"]["gases"] = ["CH4"]
    runs = expand_sweep(config)
    with pytest.raises(runner.PreflightError, match="CH4"):
        runner.preflight(config, runs)


def test_preflight_rejects_mode_econ_mismatch(tmp_path):
    ssp_dir = tmp_path / "ssp"
    ssp_dir.mkdir()
    config = fixture_factory.ssp_fixture_config(ssp_dir, etas=(2.0,))
    config["econ"]["path"] = str(fixture_factory.write_rff_econ(tmp_path))
    runs = expand_sweep(config)
    with pytest.raises(runner.PreflightError, match="treats as rff"):
        runner.preflight(config, runs)


def test_preflight_rejects_fair_missing_base_period(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    config["climate"]["gmst_fair_path"] = fixture_factory.write_short_fair(tmp_path)
    runs = expand_sweep(config)
    with pytest.raises(runner.PreflightError, match="2001"):
        runner.preflight(config, runs)


def test_preflight_rejects_short_gmst_csv(tmp_path):
    config = fixture_factory.ssp_fixture_config(tmp_path, etas=(2.0,))
    truncated = tmp_path / "short_gmst.csv"
    truncated.write_text("gcm,rcp,year,temp\ng1,rcp45,2050,1.0\n")
    config["climate"]["gmst_path"] = str(truncated)
    runs = expand_sweep(config)
    with pytest.raises(runner.PreflightError, match="2018"):
        runner.preflight(config, runs)


def test_preflight_rejects_uninstalled_discounting(tmp_path):
    from dscim_cil.config import Run

    config = fixture_factory.rff_fixture_config(tmp_path)
    fake = Run(
        sector="CAMEL_test",
        pulse_year=2020,
        recipe="risk_aversion",
        discounting="not_a_type",
        eta=2.0,
        rho=0.0001,
    )
    with pytest.raises(runner.PreflightError, match="not implemented by the installed"):
        runner.preflight(config, [fake])


def test_preflight_names_suffixed_adding_up_convention(tmp_path):
    config = fixture_factory.ssp_fixture_config(tmp_path, etas=(2.0,))
    library = tmp_path / "other_convention" / "labor"
    library.mkdir(parents=True)
    (library / "adding_up_cc_eta2.0.zarr").mkdir()
    config["paths"]["reduced_damages_library"] = str(tmp_path / "other_convention")
    runs = expand_sweep(config)
    with pytest.raises(runner.PreflightError, match="harmonize"):
        runner.preflight(config, runs)


def test_version_warning_fires_only_for_untested_versions(recwarn):
    import warnings as warnings_module

    with warnings_module.catch_warnings(record=True) as caught:
        warnings_module.simplefilter("always")
        runner._warn_if_untested("0.5.0")
    assert any("not the version" in str(w.message) for w in caught)

    with warnings_module.catch_warnings(record=True) as caught:
        warnings_module.simplefilter("always")
        runner._warn_if_untested(f"0.7.1.dev31+g{runner.TESTED_DSCIM_COMMIT}5")
    assert not caught


def test_metadata_records_provenance(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    runs = expand_sweep(config)
    lines = runner.execute(
        config, runs, invocation="t", sources={"sweep.sectors": "flag"}
    )
    metadata_path = lines[0].split("metadata: ")[1].rstrip(")")
    with open(metadata_path) as stream:
        record = yaml.safe_load(stream)
    assert record["provenance"]["ext_method"] == "default"
    assert record["provenance"]["sector"] == "flag"
    assert record["provenance"]["eta"] == "config"


def test_sum_sectors_builds_aggregate(tmp_path):
    config = fixture_factory.ssp_fixture_config(tmp_path, etas=(2.0,))
    fixture_factory.write_batch_damages(tmp_path)
    target = str(tmp_path / "AMEL_test.zarr")
    config["aggregates"] = {"AMEL_test": ["labor"]}
    config["sectors"]["AMEL_test"] = {
        "sector_path": target,
        "histclim": "summed_histclim",
        "delta": "summed_delta",
        "formula": "damages ~ -1 + anomaly + np.power(anomaly, 2)",
    }
    assert validate_config(config) == []
    lines = runner.sum_sectors(config)
    assert lines[0].startswith("completed")
    summed = xr.open_zarr(target)
    assert "summed_delta" in summed and "summed_histclim" in summed
    _assert_not_degenerate(summed["summed_delta"], varying=())


def test_reduce_all_writes_both_conventions(tmp_path):
    config = fixture_factory.ssp_fixture_config(tmp_path, etas=(2.0,))
    fixture_factory.write_batch_damages(tmp_path)
    fresh = tmp_path / "fresh_reduced"
    config["paths"]["reduced_damages_library"] = str(fresh)
    config["reduce"] = {
        "reductions": ["cc"],
        "recipes": ["adding_up", "risk_aversion"],
    }
    assert validate_config(config) == []
    lines = runner.reduce_all(config)
    assert all(line.startswith("completed") for line in lines)
    sector_dir = pathlib.Path(fresh) / "labor"
    assert (sector_dir / "adding_up_cc.zarr").exists()  # eta=None, unsuffixed
    assert (sector_dir / "risk_aversion_cc_eta2.0.zarr").exists()
    cc = xr.open_zarr(str(sector_dir / "adding_up_cc.zarr"))["cc"]
    _assert_not_degenerate(cc, varying=())
    no_cc_path = sector_dir.parent / "labor" / "adding_up_no_cc.zarr"
    runner.reduce_all(
        {**config, "reduce": {"reductions": ["no_cc"], "recipes": ["adding_up"]}}
    )
    no_cc = xr.open_zarr(str(no_cc_path))["no_cc"]
    # equal cc and no_cc reductions mean zero damages downstream
    assert float(abs(cc - no_cc).max()) > 0


def test_combine_merges_coefficient_files(tmp_path):
    config = fixture_factory.ssp_fixture_config(tmp_path, etas=(2.0,))
    results = config["paths"]["results"]
    for name, variables in (
        ("amel_x", {"anomaly": 1.0e5, "np.power(anomaly, 2)": 2.0e4}),
        ("coastal_x", {"gmsl": 5.0e4, "np.power(gmsl, 2)": 1.0e4}),
    ):
        config["sectors"][name] = {
            "sector_path": "/unused",
            "histclim": "histclim",
            "delta": "delta",
            "formula": "damages ~ -1 + anomaly + np.power(anomaly, 2)"
            if name == "amel_x"
            else "damages ~ -1 + gmsl + np.power(gmsl, 2)",
        }
        fixture_factory.write_ssp_coefficients(
            results,
            sector=name,
            recipe="adding_up",
            discounting="euler_ramsey",
            eta=2.0,
            rho=0.0001,
            variables=variables,
        )
    target_dir = f"{results}/CAMEL_x/2020/unmasked"
    config["sectors"]["CAMEL_x"] = {
        "formula": (
            "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)"
        ),
        "damage_function_path": target_dir,
    }
    config["combine"] = {"target": "CAMEL_x", "coastal": "coastal_x", "amel": "amel_x"}
    assert validate_config(config) == []
    lines = runner.combine_all(config)
    assert lines[0].startswith("completed")
    combined = xr.open_dataset(
        f"{target_dir}/adding_up_euler_ramsey_eta2.0_rho0.0001"
        f"_damage_function_coefficients.nc4"
    )
    assert {"anomaly", "np.power(anomaly, 2)", "gmsl", "np.power(gmsl, 2)"} <= set(
        combined.data_vars
    )
    for variable in combined.data_vars:
        _assert_not_degenerate(combined[variable], varying=())


@pytest.fixture(scope="module")
def rff_with_outputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("rff_scc")
    config = fixture_factory.rff_fixture_config(root)
    config["menu"]["save_files"] = [
        "uncollapsed_sccs",
        "uncollapsed_marginal_damages",
        "uncollapsed_discount_factors",
        "global_consumption_no_pulse",
    ]
    runner.execute(config, invocation="t")
    return config


def test_scc_compose_mean(rff_with_outputs):
    from dscim_cil import scc as composer

    config = yaml.safe_load(yaml.safe_dump(rff_with_outputs))
    config["scc"] = {
        "deflator": 2.0,
        "collapse": "mean",
        "output": config["paths"]["results"] + "_scghg_mean",
    }
    assert validate_config(config) == []
    lines = composer.compose(config)
    assert lines and all(line.startswith("completed") for line in lines)
    written = xr.open_dataset(lines[0].split("completed: ")[1])
    assert "runid" not in written.dims
    _assert_not_degenerate(written["scghg"], varying=())


def test_scc_compose_certainty_equivalent_and_cross_root(rff_with_outputs):
    from dscim_cil import scc as composer

    config = yaml.safe_load(yaml.safe_dump(rff_with_outputs))
    config["scc"] = {
        "deflator": 1.012094,
        "collapse": "certainty_equivalent",
        "output": config["paths"]["results"] + "_scghg_ce",
        "damages_from": config["paths"]["results"],
        "discounting_from": config["paths"]["results"],
    }
    assert validate_config(config) == []
    lines = composer.compose(config)
    written = xr.open_dataset(lines[0].split("completed: ")[1])
    assert "runid" not in written.dims
    _assert_not_degenerate(written["scghg"], varying=())


def test_gas_conversions_match_conversion_file(tmp_path):
    with_file = fixture_factory.rff_fixture_config(tmp_path)
    runner.execute(with_file, invocation="test")

    inline_dir = tmp_path / "inline"
    inline_dir.mkdir()
    inline = fixture_factory.rff_fixture_config(inline_dir)
    del inline["climate"]["damages_pulse_conversion_path"]
    inline["climate"]["gas_conversions"] = {"CO2_Fossil": 0.5}
    assert validate_config(inline) == []
    runner.execute(inline, invocation="test")

    generated = pathlib.Path(inline["paths"]["results"]) / "gas_conversions.nc4"
    assert generated.exists()

    name = "risk_aversion_euler_ramsey_eta2.0_rho0.0001_uncollapsed_sccs.nc4"
    tail = pathlib.Path("CAMEL_test") / "2020" / "unmasked" / name
    from_file = xr.open_dataset(pathlib.Path(with_file["paths"]["results"]) / tail)
    from_inline = xr.open_dataset(pathlib.Path(inline["paths"]["results"]) / tail)
    xr.testing.assert_allclose(from_file, from_inline)


def _rff_epa_named_config(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    directory = pathlib.Path(config["sectors"]["CAMEL_test"]["damage_function_path"])
    for stale in directory.iterdir():
        stale.unlink()
    fixture_factory.write_rff_coefficients(
        tmp_path,
        recipe="risk_aversion",
        discounting="euler_ramsey",
        eta=2.0,
        rho=0.0001,
        naming="epa",
    )
    return config


def test_epa_named_coefficients_are_detected_not_used(tmp_path):
    config = _rff_epa_named_config(tmp_path)
    with pytest.raises(runner.PreflightError, match="rounded _dfc"):
        runner.preflight(config, expand_sweep(config))


def test_missing_coefficients_name_both_conventions(tmp_path):
    config = fixture_factory.rff_fixture_config(tmp_path)
    directory = pathlib.Path(config["sectors"]["CAMEL_test"]["damage_function_path"])
    for stale in directory.iterdir():
        stale.unlink()
    with pytest.raises(runner.PreflightError, match=r"_dfc\.nc4"):
        runner.preflight(config, expand_sweep(config))
