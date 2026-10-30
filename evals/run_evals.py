"""Score the copilot against the answer key in evals/expected_decisions.json.

Two scores per application:
  decision - did the copilot pick the right ACCEPT / REFER / DECLINE?
  rules    - did it cite exactly the rules that should trigger (no more, no less)?

Run it:
    python -m evals.run_evals            # calls the AI for every application
    python -m evals.run_evals --cached   # re-scores saved results in artifacts/ (no API calls)
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.copilot import ARTIFACTS_DIR, SUBMISSIONS_DIR, underwrite
from src.llm import LLMError
from src.schemas import UnderwritingDecision

ANSWER_KEY = Path(__file__).resolve().parent / "expected_decisions.json"


def score_case(case: dict, result: UnderwritingDecision) -> dict:
    expected_rules = set(case["triggered_rules"])
    cited_rules = {f.rule_id for f in result.reasons}
    return {
        "submission": case["submission"],
        "expected_decision": case["expected_decision"],
        "decision": result.decision,
        "decision_correct": result.decision == case["expected_decision"],
        "rules_correct": cited_rules == expected_rules,
        "rules_hit": sorted(expected_rules & cited_rules),
        "rules_missed": sorted(expected_rules - cited_rules),
        "rules_extra": sorted(cited_rules - expected_rules),
        "warnings": result.warnings,
        "models_used": result.models_used,
    }


def summarize(scores: list[dict]) -> dict:
    hit = sum(len(s["rules_hit"]) for s in scores)
    missed = sum(len(s["rules_missed"]) for s in scores)
    extra = sum(len(s["rules_extra"]) for s in scores)
    return {
        "cases": len(scores),
        "decisions_correct": sum(s["decision_correct"] for s in scores),
        "rules_exactly_right": sum(s["rules_correct"] for s in scores),
        # Recall: of the rules that should trigger, how many were cited?
        "rule_recall": round(hit / (hit + missed), 3) if hit + missed else 1.0,
        # Precision: of the rules cited, how many should have been?
        "rule_precision": round(hit / (hit + extra), 3) if hit + extra else 1.0,
    }


def get_result(name: str, cached: bool) -> UnderwritingDecision:
    saved = ARTIFACTS_DIR / f"{Path(name).stem}.json"
    if cached and saved.exists():
        return UnderwritingDecision.model_validate_json(saved.read_text(encoding="utf-8"))
    result = underwrite(SUBMISSIONS_DIR / name)
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    saved.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Score the underwriting copilot")
    parser.add_argument("--cached", action="store_true", help="Use saved results in artifacts/ when they exist")
    args = parser.parse_args()

    cases = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
    scores, failed = [], []
    for case in cases:
        print(f"Running {case['submission']} ...")
        try:
            scores.append(score_case(case, get_result(case["submission"], args.cached)))
        except LLMError as e:
            failed.append(case["submission"])
            print(f"  FAILED: {str(e)[:200]}")

    print(f"\n{'Application':<38}{'Expected':<10}{'Got':<10}{'Decision':<10}Rules")
    for s in scores:
        rules = "exact" if s["rules_correct"] else (
            f"missed {s['rules_missed'] or '-'}, extra {s['rules_extra'] or '-'}")
        print(f"{s['submission']:<38}{s['expected_decision']:<10}{s['decision']:<10}"
              f"{'OK' if s['decision_correct'] else 'WRONG':<10}{rules}")

    summary = summarize(scores)
    summary["failed_to_run"] = failed
    print(f"\nDecisions correct:   {summary['decisions_correct']} / {summary['cases']}")
    print(f"Rules exactly right: {summary['rules_exactly_right']} / {summary['cases']}")
    print(f"Rule recall:         {summary['rule_recall']:.0%}  (rules that should trigger and were cited)")
    print(f"Rule precision:      {summary['rule_precision']:.0%}  (cited rules that should have triggered)")
    if failed:
        print(f"Could not run:       {', '.join(failed)}")

    report = ARTIFACTS_DIR / f"eval_report_{datetime.now():%Y%m%d_%H%M%S}.json"
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    report.write_text(json.dumps({"summary": summary, "cases": scores}, indent=2), encoding="utf-8")
    print(f"Report saved:        {report.name}")

    all_good = not failed and summary["decisions_correct"] == summary["cases"]
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(main())
