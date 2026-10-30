"""Tests for the eval scoring. No API calls."""
from evals.run_evals import score_case, summarize
from src.schemas import RuleFinding, SubmissionFacts, UnderwritingDecision


def result(decision, cited):
    reasons = [RuleFinding(rule_id=r, outcome="REFER", evidence="x", explanation="x") for r in cited]
    return UnderwritingDecision(
        submission="s.txt", decision=decision, reasons=reasons, missing_information=[],
        summary="", derived={}, facts=SubmissionFacts(), findings=reasons, models_used=[],
    )


def test_exact_match():
    s = score_case({"submission": "s.txt", "expected_decision": "REFER", "triggered_rules": ["GL-3", "GL-4"]},
                   result("REFER", ["GL-4", "GL-3"]))
    assert s["decision_correct"] and s["rules_correct"]


def test_missed_and_extra_rules():
    s = score_case({"submission": "s.txt", "expected_decision": "REFER", "triggered_rules": ["GL-3", "GL-4"]},
                   result("REFER", ["GL-3", "APP-3"]))
    assert s["decision_correct"] and not s["rules_correct"]
    assert s["rules_missed"] == ["GL-4"] and s["rules_extra"] == ["APP-3"]


def test_summary_precision_and_recall():
    scores = [
        score_case({"submission": "a", "expected_decision": "REFER", "triggered_rules": ["GL-3", "GL-4"]},
                   result("REFER", ["GL-3", "APP-3"])),
        score_case({"submission": "b", "expected_decision": "ACCEPT", "triggered_rules": []},
                   result("ACCEPT", [])),
    ]
    summary = summarize(scores)
    assert summary["decisions_correct"] == 2
    assert summary["rules_exactly_right"] == 1
    assert summary["rule_recall"] == 0.5
    assert summary["rule_precision"] == 0.5
