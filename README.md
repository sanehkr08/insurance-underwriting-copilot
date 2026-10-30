# Insurance Underwriting Copilot

An AI assistant for commercial insurance underwriters. It reads a broker submission for a small-business property and general liability package, checks it against written underwriting guidelines, and recommends **ACCEPT**, **REFER** or **DECLINE**. Every reason cites the guideline rule it comes from and quotes the evidence from the submission.

It runs on free AI APIs (Google Gemini and Groq) and switches to the other provider automatically when one is busy.

> All guidelines, businesses, people and email addresses in this project are fictional and for testing only.

## Results

Scored against an answer key of 5 sample submissions (2 accept, 2 refer, 1 decline), each with deliberate traps:

| Metric | Score |
|---|---|
| Decisions correct | 5 / 5 |
| Cited exactly the right rules | 5 / 5 |
| Rule recall | 100% |
| Rule precision | 100% |

The first eval run cited one wrong rule (precision 91%). The cause was traced to the extraction step and fixed with a one-line prompt change. This is a single run on a small set, so treat it as a baseline, not proof of reliability.

## How it works

```
Broker submission (free text)
        |
        v
1. Extract facts      AI -> structured JSON (revenue, year built, claims, ...)
        |
        v
2. Derive numbers     Python: total insured value, roof age, claim totals
        |
        v
3. Check each rule    AI -> one finding per rule: ACCEPTABLE / REFER / DECLINE / NOT_APPLICABLE,
        |                   with evidence
        v
4. Decide             Python: any DECLINE -> DECLINE, else any REFER or missing info -> REFER,
                              else ACCEPT
```

Design choices:

- **The AI reads and judges; code does the maths and the final call.** Language models are unreliable at arithmetic, and the decision logic must be predictable. So ages, totals and the decline > refer > accept order are plain Python.
- **Guardrails on the AI's answer.** Answers are validated against Pydantic schemas. Findings for rules that don't exist are dropped, and rules the AI skipped are flagged for a human to check.
- **Provider fallback.** If Gemini fails (for example, a "high demand" error) or returns badly shaped JSON, the same request goes to Groq.

## The guidelines

The rule book lives in [data/guidelines](data/guidelines). Each rule has an ID:

| File | Rules |
|---|---|
| [01_appetite.md](data/guidelines/01_appetite.md) | APP-1 to APP-5: eligible and ineligible businesses, years in business, territory |
| [02_property.md](data/guidelines/02_property.md) | PROP-1 to PROP-7: insured value, building age, construction, roof, cooking, flood, occupancy |
| [03_liability.md](data/guidelines/03_liability.md) | GL-1 to GL-6: revenue, alcohol sales, loss history, subcontractors, working height, prior cancellation |
| [04_decision_rules.md](data/guidelines/04_decision_rules.md) | AUTH-1 to AUTH-5: how to combine findings, and required information |

To change the underwriting rules, edit these files. New rule IDs in the `## RULE-ID: Title` format are picked up automatically.

## Setup (Windows)

You need **Python 3.11 or newer** and at least one free API key.

1. Clone or download the project, then open a terminal in the project folder.
2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.
3. Install the packages:
   ```powershell
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and paste in your key(s):
   - Gemini: [aistudio.google.com](https://aistudio.google.com) → Get API key
   - Groq: [console.groq.com](https://console.groq.com) → API Keys

On macOS or Linux, activate with `source .venv/bin/activate` instead.

## Usage

**Web page:**
```powershell
streamlit run app.py
```
Open http://localhost:8501, pick a sample or paste a submission, and click **Underwrite**.

**Command line:**
```powershell
python -m src.copilot data/submissions/SUB-002_oakridge_hardware.txt
python -m src.copilot --all
```
Each result is printed and saved as JSON in `artifacts/`.

**Score against the answer key:**
```powershell
python -m evals.run_evals            # fresh AI calls
python -m evals.run_evals --cached   # re-score saved results, no API calls
```

**Unit tests** (no API calls):
```powershell
python -m pytest
```

## Project structure

```
app.py                      Streamlit web page
src/copilot.py              Extract, derive, check rules, decide (also the CLI)
src/llm.py                  Gemini/Groq client with fallback and JSON validation
src/schemas.py              Pydantic models for facts, findings and decisions
data/guidelines/            Underwriting rules (Markdown)
data/submissions/           Fictional broker submissions
evals/expected_decisions.json   Answer key: expected decision and rules per submission
evals/run_evals.py          Scoring script
tests/                      Unit tests for decision logic and scoring
```

## Limitations

- **Small eval set.** Five submissions is enough to catch obvious mistakes, not to measure reliability. AI answers can also vary between runs.
- **Free API plans may use your data** to improve their models. Use only fictional or anonymised data.
- **A recommendation, not a decision.** The copilot is meant to help an underwriter work faster. A licensed person should review every result.
- **Text submissions only.** PDFs and scanned forms (for example ACORD applications) are not supported yet.
