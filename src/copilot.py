"""Underwriting copilot: read an application and recommend ACCEPT, REFER or DECLINE.

How it works:
  1. extract_facts  - the AI pulls the key facts out of the application text
  2. derive         - our code does the arithmetic (TIV, roof age, claim totals)
  3. assess         - the AI checks every guideline rule and cites evidence
  4. decide         - our code applies AUTH-1 to AUTH-3 to get one decision

Run it:
    python -m src.copilot data/submissions/SUB-001_bean_there_cafe.txt
    python -m src.copilot --all
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from src.llm import LLMError, ask_json
from src.schemas import Assessment, RuleFinding, SubmissionFacts, UnderwritingDecision

ROOT = Path(__file__).resolve().parents[1]
GUIDELINES_DIR = ROOT / "data" / "guidelines"
SUBMISSIONS_DIR = ROOT / "data" / "submissions"
ARTIFACTS_DIR = ROOT / "artifacts"

EXTRACT_SYSTEM = """You are an insurance underwriting assistant. Extract facts from a broker \
submission for a small-business property and general liability package.

Rules:
- Use only what the submission says. If a fact is not stated, use null. Never guess.
- Always fill business_class with a short name for the kind of business \
(e.g. "cocktail lounge", "cafe", "accounting office"), based on the description.
- Money is a plain number in USD (e.g. 1200000, not "$1.2M").
- Percentages are numbers from 0 to 100.
- A claim's amount is total incurred: paid plus reserved.
- insures_building is true only if the applicant wants coverage on the building itself.
- If only a start year is given ("in business since 1995"), set years_in_business from the \
submission date."""

ASSESS_SYSTEM = """You are an underwriting assistant for a small-business package program. \
Check an application against the written guidelines.

Rules:
- Give exactly one finding for every rule ID you are asked to check.
- outcome is ACCEPTABLE, REFER, DECLINE, or NOT_APPLICABLE (the rule does not apply to this \
business, for example contractor rules for a cafe, or building rules when the building is not insured).
- Use the numbers in DERIVED VALUES for ages, totals and TIV. Do not redo that arithmetic.
- evidence must quote or restate the specific facts from the application.
- Apply only the rules written in the guidelines. Do not add rules of your own.
- missing_information lists only AUTH-5 required items that are missing or unclear.
- You do not make the final decision; just check each rule."""


def load_guidelines() -> tuple[str, list[str]]:
    """Return all guideline text and the rule IDs to check (AUTH rules are applied in code)."""
    text = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted(GUIDELINES_DIR.glob("*.md")))
    rule_ids = re.findall(r"^## ([A-Z]+-\d+)", text, re.MULTILINE)
    return text, [r for r in rule_ids if not r.startswith("AUTH-")]


def extract_facts(submission_text: str) -> tuple[SubmissionFacts, str]:
    return ask_json(EXTRACT_SYSTEM, f"SUBMISSION:\n{submission_text}", SubmissionFacts)


def _as_of(facts: SubmissionFacts) -> date:
    try:
        return date.fromisoformat(facts.submission_date or "")
    except ValueError:
        return date.today()


def derive(facts: SubmissionFacts) -> dict:
    """Arithmetic the AI should not do itself. Unknown values stay None."""
    as_of = _as_of(facts)

    def years_since(year):
        return as_of.year - year if year else None

    building = facts.building_value if facts.insures_building else 0
    values = [building, facts.contents_value, facts.business_income_value]
    amounts = [c.amount for c in facts.claims_past_3_years]
    return {
        "as_of_date": as_of.isoformat(),
        "total_insured_value": sum(v for v in values if v) or None,
        "building_age_years": years_since(facts.year_built),
        "roof_age_years": years_since(facts.roof_year),
        "years_since_electrical_update": years_since(facts.electrical_updated_year),
        "years_since_plumbing_update": years_since(facts.plumbing_updated_year),
        "years_since_heating_update": years_since(facts.heating_updated_year),
        "claim_count_past_3_years": len(amounts),
        "claims_total_incurred": sum(a for a in amounts if a),
        "claims_with_unknown_amount": sum(1 for a in amounts if a is None),
    }


def assess(submission_text: str, facts: SubmissionFacts, derived: dict,
           guidelines: str, rule_ids: list[str]) -> tuple[Assessment, str]:
    user = (
        f"GUIDELINES:\n{guidelines}\n\n"
        f"RULE IDS TO CHECK: {', '.join(rule_ids)}\n\n"
        f"DERIVED VALUES (already calculated, use these):\n{json.dumps(derived, indent=2)}\n\n"
        f"EXTRACTED FACTS:\n{facts.model_dump_json(indent=2)}\n\n"
        f"ORIGINAL SUBMISSION:\n{submission_text}"
    )
    return ask_json(ASSESS_SYSTEM, user, Assessment)


def decide(findings: list[RuleFinding], missing_information: list[str]) -> str:
    """AUTH-1: any decline wins. AUTH-2: any refer or missing info. AUTH-3: otherwise accept."""
    outcomes = {f.outcome for f in findings}
    if "DECLINE" in outcomes:
        return "DECLINE"
    if "REFER" in outcomes or missing_information:
        return "REFER"
    return "ACCEPT"


def check_findings(findings: list[RuleFinding], rule_ids: list[str]) -> tuple[list[RuleFinding], list[str]]:
    """Drop findings for rules that don't exist (AUTH-4) and flag rules the AI skipped."""
    warnings = []
    known = [f for f in findings if f.rule_id in rule_ids]
    for f in findings:
        if f.rule_id not in rule_ids:
            warnings.append(f"Ignored a finding for unknown rule '{f.rule_id}'.")
    checked = {f.rule_id for f in known}
    skipped = [r for r in rule_ids if r not in checked]
    if skipped:
        warnings.append(f"The AI did not check these rules: {', '.join(skipped)}. Review them by hand.")
    return known, warnings


def underwrite(path: Path) -> UnderwritingDecision:
    submission_text = path.read_text(encoding="utf-8")
    guidelines, rule_ids = load_guidelines()

    facts, model_1 = extract_facts(submission_text)
    derived = derive(facts)
    assessment, model_2 = assess(submission_text, facts, derived, guidelines, rule_ids)
    findings, warnings = check_findings(assessment.findings, rule_ids)

    decision = decide(findings, assessment.missing_information)
    return UnderwritingDecision(
        submission=path.name,
        decision=decision,
        reasons=[f for f in findings if f.outcome in ("REFER", "DECLINE")],
        missing_information=assessment.missing_information,
        summary=assessment.summary,
        warnings=warnings,
        derived=derived,
        facts=facts,
        findings=findings,
        models_used=[model_1, model_2],
    )


def print_decision(result: UnderwritingDecision) -> None:
    print(f"\n=== {result.submission} ===")
    print(f"DECISION: {result.decision}")
    print(f"Summary:  {result.summary}")
    for f in result.reasons:
        print(f"  - [{f.rule_id}] {f.outcome}: {f.explanation}")
        print(f"      Evidence: {f.evidence}")
    for item in result.missing_information:
        print(f"  - Missing: {item}")
    for w in result.warnings:
        print(f"  ! {w}")
    print(f"Models:   {', '.join(result.models_used)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Underwriting copilot")
    parser.add_argument("files", nargs="*", type=Path, help="Submission text files")
    parser.add_argument("--all", action="store_true", help="Run every file in data/submissions")
    args = parser.parse_args()

    files = sorted(SUBMISSIONS_DIR.glob("*.txt")) if args.all else args.files
    if not files:
        parser.error("give a submission file or use --all")

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    failed = 0
    for path in files:
        try:
            result = underwrite(path)
        except LLMError as e:
            print(f"\n=== {path.name} ===\nFAILED: {e}")
            failed += 1
            continue
        print_decision(result)
        out = ARTIFACTS_DIR / f"{path.stem}.json"
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(f"Saved:    {out.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
