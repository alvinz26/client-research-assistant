"""Streamlit page: streamlit run app.py"""
import time

import streamlit as st

from research.claude_client import ResearchError
from research.config import estimate_cost, load_config
from research.models import Brief
from research.pipeline import run

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

st.set_page_config(page_title="Client Research Assistant", page_icon=":mag:")
cfg = load_config()
st.title("Client Research Assistant")
st.caption("Enter a company, get a Word report in which every statement points to a quoted source.")
if cfg.demo:
    st.warning("**DEMO MODE**: no API key found (or DEMO_MODE=1). "
               "The report always shows a fictional sample company, whatever you type.")

with st.form("brief"):
    company = st.text_input("Company name *")
    st.markdown("**Optional clues** help find and confirm the right company.")
    left, right = st.columns(2)
    website = left.text_input("Website")
    location = right.text_input("Country / city")
    contact = left.text_input("Contact name")
    job_title = right.text_input("Job title")
    phone = left.text_input("Phone")
    email = right.text_input("Email")
    met_at = st.text_input("Where you met", placeholder="e.g. a trade fair")
    notes = st.text_area("Notes", placeholder="Anything else you know, or what you most want to find out")
    language = st.radio("Report language", ["English", "中文"], horizontal=True)
    submitted = st.form_submit_button("Research", type="primary")

if submitted:
    if not company.strip():
        st.error("Please enter a company name.")
        st.stop()
    brief = Brief(company.strip(), website, location, contact, job_title, phone, email, met_at, notes,
                  "zh" if language == "中文" else "en")
    start = time.perf_counter()
    try:
        with st.status("Researching...", expanded=True) as status:
            result = run(brief, cfg, status.write)
            status.update(label="Report ready", state="complete", expanded=False)
    except ResearchError as e:
        st.error(str(e))
        st.stop()
    except Exception as e:  # anything unexpected: a short message, not a stack trace
        st.error(f"Something went wrong ({type(e).__name__}). Please try again.")
        st.stop()
    st.session_state.result, st.session_state.seconds = result, time.perf_counter() - start

result = st.session_state.get("result")
if result:
    report, usage = result.report, result.usage
    if report.demo:
        st.error("DEMO: sample data about a fictional company, not real research.")
    st.subheader(report.brief.company)
    st.markdown(f"**Confidence: {report.confidence}.** {report.confidence_reason}")
    for bullet in report.summary:
        st.markdown(f"- {bullet.text} {''.join(f'[{n}]' for n in bullet.refs)}")
    st.caption(f"{len(report.sources)} sources · {len(report.unverified)} unverified leads · "
               f"{report.removed} statements removed · {usage.searches} searches · {st.session_state.seconds:.0f}s")
    cost = None if report.demo else estimate_cost(report.model, usage.input_tokens, usage.output_tokens, usage.searches)
    if cost is not None:
        st.caption(f"Estimated API cost: ${cost:.2f} ({usage.input_tokens:,} input / {usage.output_tokens:,} output tokens)")
    st.download_button("Download Word report", result.path.read_bytes(), file_name=result.path.name,
                       mime=DOCX_MIME, type="primary", on_click="ignore")
