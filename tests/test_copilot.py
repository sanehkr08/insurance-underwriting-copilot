"""Tests for the parts of the copilot that don't call an AI. Run with: pytest"""
from src.copilot import check_findings, decide, derive, load_guidelines
from src.schemas import Claim, RuleFinding, SubmissionFacts


def finding(rule_id, outcome):
    return RuleFinding(rule_id=rule_id, outcome=outcome, evidence="test", explanation="test")


def test_decline_wins_over_refer():
    findings = [finding("PROP-6", "REFER"), finding("GL-2", "DECLINE")]
    assert decide(findings, []) == "DECLINE"


def test_refer_when_any_rule_refers():
    findings = [finding("PROP-1", "ACCEPTABLE"), finding("PROP-4", "REFER")]
    assert decide(findings, []) == "REFER"


def test_refer_when_information_missing():
    assert decide([finding("PROP-1", "ACCEPTABLE")], ["roof age"]) == "REFER"


def test_accept_when_all_clear():
    findings = [finding("PROP-1", "ACCEPTABLE"), finding("GL-4", "NOT_APPLICABLE")]
    assert decide(findings, []) == "ACCEPT"


def test_outcome_and_rule_id_are_normalised():
    f = RuleFinding(rule_id=" prop-4 ", outcome="not applicable", evidence="x", explanation="x")
    assert (f.rule_id, f.outcome) == ("PROP-4", "NOT_APPLICABLE")


def test_derive_does_the_arithmetic():
    facts = SubmissionFacts(
        submission_date="2026-10-20",
        insures_building=True,
        year_built=1958,
        roof_year=2004,
        heating_updated_year=1998,
        building_value=1_900_000,
        contents_value=900_000,
        business_income_value=300_000,
        claims_past_3_years=[Claim(description="a", amount=12_000), Claim(description="b", amount=48_000)],
    )
    d = derive(facts)
    assert d["total_insured_value"] == 3_100_000
    assert d["building_age_years"] == 68
    assert d["roof_age_years"] == 22
    assert d["years_since_heating_update"] == 28
    assert d["claim_count_past_3_years"] == 2
    assert d["claims_total_incurred"] == 60_000


def test_building_value_ignored_for_tenants():
    facts = SubmissionFacts(insures_building=False, building_value=5_000_000, contents_value=120_000)
    assert derive(facts)["total_insured_value"] == 120_000


def test_guideline_rule_ids_are_loaded():
    _, rule_ids = load_guidelines()
    assert "APP-2" in rule_ids and "PROP-7" in rule_ids and "GL-6" in rule_ids
    assert not any(r.startswith("AUTH-") for r in rule_ids)


def test_unknown_and_skipped_rules_are_flagged():
    kept, warnings = check_findings([finding("PROP-1", "ACCEPTABLE"), finding("XYZ-9", "DECLINE")], ["PROP-1", "GL-1"])
    assert [f.rule_id for f in kept] == ["PROP-1"]
    assert any("XYZ-9" in w for w in warnings)
    assert any("GL-1" in w for w in warnings)
