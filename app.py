"""Web page for the underwriting copilot.

Run it:
    streamlit run app.py
"""
import re

import streamlit as st

from src.copilot import SUBMISSIONS_DIR, load_guidelines, underwrite_text
from src.llm import LLMError

DECISION_STYLE = {
    "ACCEPT": (st.success, "ACCEPT: within guidelines"),
    "REFER": (st.warning, "REFER: send to a senior underwriter"),
    "DECLINE": (st.error, "DECLINE: outside guidelines"),
}



def md(text: str) -> str:
    """Escape $ so Streamlit doesn't render "$3M and $5M" as a math formula."""
    return text.replace("$", r"\$")


def money(value) -> str:
    if not value:
        return "n/a" if value is None else "$0"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value / 1e3:.0f}K" if value >= 1e3 else f"${value:,.0f}"


st.set_page_config(page_title="Underwriting Copilot", layout="wide")
st.title("Underwriting Copilot")
st.caption(
    "Small-business property and liability package. Reads a broker submission, checks it "
    "against the written guidelines, and recommends ACCEPT, REFER or DECLINE with the rules cited. "
    "Sample data is fictional. Do not paste real customer data: free AI plans may use it for training."
)

samples = {p.name: p for p in sorted(SUBMISSIONS_DIR.glob("*.txt"))}
choice = st.selectbox("Start from a sample submission, or paste your own below", ["(paste my own)", *samples])
default_text = samples[choice].read_text(encoding="utf-8") if choice in samples else ""
text = st.text_area("Submission", value=default_text, height=320, key=f"text-{choice}")

if st.button("Underwrite", type="primary", disabled=not text.strip()):
    with st.spinner("Reading the submission and checking each rule. This takes about 20-60 seconds..."):
        try:
            st.session_state["result"] = underwrite_text(text, choice if choice in samples else "pasted submission")
        except LLMError as e:
            st.session_state.pop("result", None)
            st.error(f"Neither AI provider answered. Try again in a minute.\n\n{e}")

result = st.session_state.get("result")
if result:
    show, label = DECISION_STYLE[result.decision]
    show(f"### {label}")
    st.markdown(md(result.summary))

    d = result.derived
    cols = st.columns(4)
    cols[0].metric("Total insured value", money(d["total_insured_value"]))
    cols[1].metric("Annual revenue", money(result.facts.annual_revenue))
    cols[2].metric("Claims (3 years)", d["claim_count_past_3_years"])
    cols[3].metric("Claims incurred", money(d["claims_total_incurred"]))

    if result.reasons:
        st.subheader("Reasons")
        for f in sorted(result.reasons, key=lambda f: f.outcome != "DECLINE"):
            st.markdown(f"**{f.rule_id} - {f.outcome}**: {md(f.explanation)}  \n*Evidence:* {md(f.evidence)}")

    if result.missing_information:
        st.subheader("Information needed")
        for item in result.missing_information:
            st.markdown(f"- {md(item)}")

    for w in result.warnings:
        st.warning(w)

    with st.expander("Every rule checked"):
        st.dataframe(
            [{"Rule": f.rule_id, "Outcome": f.outcome, "Why": f.explanation, "Evidence": f.evidence}
             for f in result.findings],
            hide_index=True, width="stretch",
        )
    with st.expander("Facts the AI extracted"):
        st.json(result.facts.model_dump(exclude_defaults=True))
    st.caption(f"Models used: {', '.join(result.models_used)}")

with st.sidebar:
    st.header("Guidelines")
    guidelines, rule_ids = load_guidelines()
    st.caption(f"{len(rule_ids)} rules checked on every submission")
    # Shrink the guideline headings so they fit the sidebar
    st.markdown(md(re.sub(r"^(#+) ", lambda m: "#" * (len(m.group(1)) + 3) + " ", guidelines, flags=re.MULTILINE)))
