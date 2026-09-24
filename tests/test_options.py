"""Catalogue integrity tests."""

from dscim_cil.config import COMBINATION_CHECKERS
from dscim_cil.options import (
    CATALOGUE,
    COMPATIBILITY,
    DEFAULT_SAVE_FILES,
    DISCOUNT_TYPES,
    FORMULAS,
    STATUSES,
)


def test_formulas_are_the_twelve_from_dscim_main():
    assert len(FORMULAS) == 12
    assert FORMULAS[0] == "damages ~ -1 + np.power(anomaly, 2)"
    assert FORMULAS[5] == "damages ~ -1 + anomaly + np.power(anomaly, 2)"
    assert (
        FORMULAS[7]
        == "damages ~ -1 + anomaly + np.power(anomaly, 2) + gmsl + np.power(gmsl, 2)"
    )
    assert FORMULAS[11] == "damages ~ -1 + gmsl:anomaly + gmsl:np.power(anomaly, 2)"
    assert len(set(FORMULAS)) == 12


def test_default_save_files_are_the_eleven_from_dscim_main():
    assert DEFAULT_SAVE_FILES == (
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


def test_discount_types_include_constant_gwr_as_unsupported():
    assert "constant_gwr" in DISCOUNT_TYPES
    entry = CATALOGUE["discounting_type"].value("constant_gwr")
    assert entry is not None
    assert entry.status == "unsupported"
    assert entry.reason
    assert entry.citation
    assert entry.restriction == "library"


def test_quantreg_catalogued_not_omitted():
    entry = CATALOGUE["fit_type"].value("quantreg")
    assert entry is not None
    assert entry.status == "unsupported"
    assert entry.reason
    assert entry.citation


def test_every_option_has_summary_status_citation():
    for name, option in CATALOGUE.items():
        assert option.summary, name
        assert option.citation, name
        assert option.status in STATUSES, name
        if option.status != "supported":
            assert option.reason, name
            assert option.restriction, name


def test_every_non_supported_value_has_reason_and_citation():
    for name, option in CATALOGUE.items():
        for value in option.values:
            assert value.status in STATUSES, (name, value.value)
            if value.status != "supported":
                assert value.reason, (name, value.value)
                assert value.citation, (name, value.value)
                assert value.restriction, (name, value.value)


def test_removed_surface_is_catalogued():
    for name in ("geography", "individual_region", "country_mapping_path"):
        assert CATALOGUE[name].status == "removed"


def test_every_compatibility_rule_has_a_checker_and_vice_versa():
    rule_keys = {rule.key for rule in COMPATIBILITY}
    assert rule_keys == set(COMBINATION_CHECKERS)
    assert len(rule_keys) == len(COMPATIBILITY)


def test_reasons_state_dscim_facts_not_roadmap():
    banned = ("phase", "deferred", "roadmap", "todo")
    for name, option in CATALOGUE.items():
        for text in (option.reason, option.summary):
            for word in banned:
                assert word not in text.lower(), (name, word, text)
        for value in option.values:
            for word in banned:
                assert word not in value.reason.lower(), (name, value.value, word)


def test_config_required_split():
    from dscim_cil.options import REQUIRED

    required = {name for name, opt in CATALOGUE.items() if opt.config_required}
    assert {
        "eta",
        "rho",
        "discounting_type",
        "formula",
        "recipe",
        "sector",
        "pulse_year",
    } <= required
    # dscim's own defaults stay recorded for reference
    assert CATALOGUE["eta"].default == 1.421158116
    assert CATALOGUE["rho"].default == 0.00461878399
    assert CATALOGUE["discounting_type"].default is None
    assert CATALOGUE["formula"].default is REQUIRED


def test_pipeline_stages_carry_citations_and_flow():
    from dscim_cil.options import PIPELINE

    names = [stage.name for stage in PIPELINE]
    assert names == ["sum-sectors", "reduce", "run", "combine", "scc"]
    for stage in PIPELINE:
        assert stage.consumes, stage.name
        assert stage.produces, stage.name
        assert stage.collapses, stage.name
        for statement in stage.collapses:
            assert ".py" in statement or "none" in statement, (
                stage.name,
                statement,
            )
    reduce_stage = next(s for s in PIPELINE if s.name == "reduce")
    assert "batch" in " ".join(reduce_stage.collapses)
    run_stage = next(s for s in PIPELINE if s.name == "run")
    joined = " ".join(run_stage.collapses)
    assert "gwr" in joined and "runid" in joined and "discrate" in joined
