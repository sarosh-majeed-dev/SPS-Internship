"""
RFP Intelligence Portal
-----------------------
Upload an RFP document and automatically extract the Deliverables,
Evaluation Criteria, and a department-wise Compliance Checklist
(Financial/Accounting, Legal, Operations, Technical) built on the
SPS RFP review template.

Run:  streamlit run app.py
"""

import html
import io
import json

import pandas as pd
import streamlit as st

import ai_extractor as engine

st.set_page_config(
    page_title="RFP Intelligence Portal",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
#  Styling - clean, professional, no emojis
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      .stApp { background: #0d1117; color: #e6edf3; }
      section[data-testid="stSidebar"] { background: #11161d; border-right: 1px solid #20262e; }
      h1, h2, h3, h4 { color: #f0f6fc !important; letter-spacing: .2px; }
      .hero {
        background: linear-gradient(135deg, #131a24 0%, #0d1117 100%);
        border: 1px solid #222b36; border-radius: 14px;
        padding: 26px 30px; margin-bottom: 22px;
      }
      .hero h1 { margin: 0; font-size: 30px; font-weight: 700; }
      .hero p  { margin: 6px 0 0; color: #9aa7b4; font-size: 15px; }
      .badge {
        display:inline-block; padding:3px 11px; border-radius:20px;
        font-size:12px; font-weight:600; letter-spacing:.3px;
        border:1px solid #2b3947; color:#8ab4f8; margin-top:12px;
      }
      .metric-card {
        background:#131a24; border:1px solid #222b36; border-radius:12px;
        padding:16px 18px; text-align:center;
      }
      .metric-card .v { font-size:26px; font-weight:700; color:#f0f6fc; }
      .metric-card .l { font-size:12px; color:#8b97a4; text-transform:uppercase; letter-spacing:.6px; }
      .rec {
        border-radius:12px; padding:18px 22px; margin:6px 0 18px;
        font-size:16px; font-weight:600; border:1px solid;
      }
      .rec.go       { background:#0e2a16; border-color:#1f7a3a; color:#5ee08a; }
      .rec.nogo     { background:#2a1010; border-color:#7a1f1f; color:#f08a8a; }
      .rec.escalate { background:#2a2410; border-color:#7a661f; color:#e0c95e; }
      .rec.review   { background:#15202b; border-color:#2b4a66; color:#8ab4f8; }
      .item-card {
        background:#0f151d; border:1px solid #20262e; border-left:3px solid #2b4a66;
        border-radius:8px; padding:10px 14px; margin-bottom:8px; font-size:14px; color:#cdd6df;
      }
      .stTabs [data-baseweb="tab-list"] { gap:4px; }
      .stTabs [data-baseweb="tab"] { background:#131a24; border-radius:8px 8px 0 0; color:#9aa7b4; }
      .stTabs [aria-selected="true"] { background:#1b2531; color:#f0f6fc; }
      .stDataFrame { border:1px solid #222b36; border-radius:10px; }
      .stButton>button, .stDownloadButton>button {
        background:#1b2531; color:#e6edf3; border:1px solid #2b3947; border-radius:8px;
      }
      .stButton>button:hover, .stDownloadButton>button:hover { border-color:#3b82f6; color:#fff; }

      /* department checklist cards */
      .dept { background:#0f151d; border:1px solid #20262e; border-radius:14px;
              overflow:hidden; margin-bottom:18px; }
      .dept-head { padding:14px 18px; font-size:16px; font-weight:700; color:#fff;
                   display:flex; justify-content:space-between; align-items:center; }
      .dept-score { font-size:15px; font-weight:700; opacity:.95; }
      .conf { color:#8b97a4; font-size:11px; margin-right:8px; white-space:nowrap; }
      .dept-body { padding:14px; }
      .citem { background:#131a24; border:1px solid #222b36; border-radius:10px;
               padding:12px 14px; margin-bottom:10px; }
      .citem-top { display:flex; justify-content:space-between; align-items:center; gap:10px; }
      .citem-name { font-weight:600; color:#f0f6fc; font-size:14px; }
      .citem-reason { color:#9aa7b4; font-size:12.5px; margin-top:6px; line-height:1.5; }
      .vbadge { padding:3px 12px; border-radius:20px; font-size:11px; font-weight:700;
                letter-spacing:.5px; white-space:nowrap; }
      .vbadge.go   { background:#0e2a16; color:#5ee08a; border:1px solid #1f7a3a; }
      .vbadge.nogo { background:#2a1010; color:#f08a8a; border:1px solid #7a1f1f; }
      .vbadge.rev  { background:#2a2410; color:#e0c95e; border:1px solid #7a661f; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
#  Header
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="hero">
      <h1>RFP Intelligence Portal</h1>
      <p>Upload a Request for Proposal and automatically extract deliverables,
      evaluation criteria, and a department-wise compliance checklist.</p>
      <span class="badge">SPS &nbsp;|&nbsp; Automated RFP Review</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
#  Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### How it works")
    st.markdown(
        "1. Upload an RFP (PDF, DOCX or TXT).\n"
        "2. The engine parses the full document.\n"
        "3. Review the extracted deliverables, evaluation criteria, "
        "and compliance tasks per department."
    )
    st.markdown("---")
    st.markdown("### Decision rules applied")
    st.markdown(
        "- Payment NET30 -> GO; beyond NET30 -> escalate to Accounting\n"
        "- Insurance up to \\$5M -> GO; above \\$5M -> NO-GO\n"
        "- E-Verify, MBE, bonds and registrations are flagged for review"
    )
    st.markdown("---")
    use_sample = st.button("Load sample RFP")

# --------------------------------------------------------------------------- #
#  Input
# --------------------------------------------------------------------------- #
uploaded = st.file_uploader(
    "Upload RFP document", type=["pdf", "docx", "txt"], label_visibility="collapsed"
)

file_bytes, filename = None, None
if uploaded is not None:
    file_bytes, filename = uploaded.read(), uploaded.name
elif use_sample:
    import os
    sample_path = os.path.join(os.path.dirname(__file__), "sample_rfp", "sample_rfp.docx")
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            file_bytes, filename = f.read(), "sample_rfp.docx"
    else:
        st.warning("Sample file not found. Run  python make_sample.py  first.")

if not file_bytes:
    st.info("Upload an RFP document above, or click 'Load sample RFP' in the sidebar to test the workflow.")
    st.stop()

# --------------------------------------------------------------------------- #
#  Analyse
# --------------------------------------------------------------------------- #
with st.spinner("Analysing document with the on-device AI model "
                "(scanned PDFs are run through OCR first, which can take a minute)..."):
    result = engine.analyze(file_bytes, filename)

st.success(f"Analysed: {filename}    |    Engine: {result.get('engine', 'Rule-based')}")

# Warn when the document yielded almost no readable text (scanned / image PDF)
if result["word_count"] < 80:
    st.warning(
        "Very little selectable text was found in this file. It is likely a "
        "scanned or image-based PDF, so the AI has almost nothing to read. "
        "Use a text-based PDF/DOCX, or run the file through OCR first."
    )

# --------------------------------------------------------------------------- #
#  Compare checklist vs RFP  ->  matches / missing / compliance %
# --------------------------------------------------------------------------- #
all_rows = [r for dept_rows in result["compliance"].values() for r in dept_rows]
full_df = pd.DataFrame(all_rows)
matches = [r for r in all_rows if r["Status"] == "Found in RFP"]
missing = [r for r in all_rows if r["Status"] != "Found in RFP"]
total = max(1, len(all_rows))
compliance_pct = round(len(matches) / total * 100)

# --- Graded scoring from match strength (avoids a flat, suspicious 100%) ------ #
def _conf_val(c):
    try:
        return int(str(c).replace("%", ""))
    except ValueError:
        return 0


def _item_score(conf):
    """Turn a semantic match confidence into a 0 to 100 grade.
    Not addressed scores 0; a just-passing match (33%) scores about 50;
    a strong, direct match (75% or more) scores 100."""
    if conf <= 0:
        return 0
    return int(round(min(100, max(0, (conf - 33) / 42 * 50 + 50))))


dept_scores = {}
for dept, rows in result["compliance"].items():
    s = [_item_score(_conf_val(r.get("Confidence", "-"))) for r in rows]
    dept_scores[dept] = round(sum(s) / len(s)) if s else 0

item_scores = [_item_score(_conf_val(r.get("Confidence", "-"))) for r in all_rows]
overall_score = round(sum(item_scores) / len(item_scores)) if item_scores else 0

n_nogo = sum(1 for _, d, _ in result["decisions"] if d == "NO-GO")
n_esc = sum(1 for _, d, _ in result["decisions"] if d == "ESCALATE")
blocked = n_nogo > 0

if blocked:
    verdict, vcls = "NO-GO", "nogo"
    why = "a hard company rule was broken (see Decision Rules)"
elif n_esc:
    verdict, vcls = "ESCALATE", "escalate"
    why = "a term needs Accounting sign-off (see Decision Rules)"
elif len(missing) > 0 or overall_score < 55:
    verdict, vcls = "REVIEW", "review"
    why = f"{len(missing)} requirement(s) need a manual check before bidding"
else:
    verdict, vcls = "GO", "go"
    why = "the RFP addresses the checklist well and breaks no hard rules"

readiness_display = "BLOCKED" if blocked else f"{overall_score}%"

# Metrics row
c1, c2, c3, c4 = st.columns(4)
for col, value, label in [
    (c1, readiness_display, "Bid readiness score"),
    (c2, f"{len(matches)} / {total}", "Requirements addressed"),
    (c3, len(missing), "Requirements missing"),
    (c4, len(result["deliverables"]), "Deliverables found"),
]:
    col.markdown(
        f"<div class='metric-card'><div class='v'>{value}</div>"
        f"<div class='l'>{label}</div></div>",
        unsafe_allow_html=True,
    )

# Readiness progress bar
if blocked:
    caption = (f"This RFP is blocked by {n_nogo} hard rule"
               f"{'s' if n_nogo > 1 else ''} that break company policy. See Decision Rules.")
else:
    caption = ("The bid readiness score is the average match strength across the "
               f"{total} checklist requirements. Each department is graded below.")
st.markdown(
    f"<div style='margin:14px 0 4px;color:#9aa7b4;font-size:13px;'>{caption}</div>",
    unsafe_allow_html=True,
)
st.progress(0.0 if blocked else overall_score / 100)

# Final verdict banner
head = "Bid Readiness: BLOCKED (No Go)" if blocked else f"Bid Readiness: {overall_score}%"
st.markdown(
    f"<div class='rec {vcls}'>{head} &nbsp;-&nbsp; "
    f"Recommendation: {verdict} &nbsp;-&nbsp; {why.capitalize()}.</div>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
#  Tabs
# --------------------------------------------------------------------------- #
tab1, tab2, tab3, tab4 = st.tabs(
    ["Checklist Review", "Deliverables", "Evaluation Criteria", "Decision Rules"]
)

DEPT_COLORS = {
    "Financial / Accounting": "linear-gradient(135deg,#1e40af,#3b82f6)",
    "Legal": "linear-gradient(135deg,#9d174d,#db2777)",
    "Operations": "linear-gradient(135deg,#166534,#16a34a)",
    "Technical": "linear-gradient(135deg,#9a3412,#ea580c)",
}
_BADGE = {"GO": "go", "NO-GO": "nogo", "REVIEW": "rev"}


def _dept_card_html(dept, rows, score):
    color = DEPT_COLORS.get(dept, "linear-gradient(135deg,#334155,#475569)")
    items = ""
    for r in rows:
        v = r.get("Verdict", "REVIEW")
        reason = html.escape(str(r.get("Reason", "-")))
        name = html.escape(r["Checklist Item"])
        conf = r.get("Confidence", "-")
        conf_html = (f"<span class='conf'>match {html.escape(str(conf))}</span>"
                     if conf and conf != "-" else "")
        items += (
            f"<div class='citem'><div class='citem-top'>"
            f"<span class='citem-name'>{name}</span>"
            f"<span>{conf_html}<span class='vbadge {_BADGE.get(v,'rev')}'>{v}</span></span>"
            f"</div><div class='citem-reason'>{reason}</div></div>"
        )
    head = (f"<span>{html.escape(dept)}</span>"
            f"<span class='dept-score'>{score} / 100</span>")
    return (f"<div class='dept'><div class='dept-head' style='background:{color}'>"
            f"{head}</div><div class='dept-body'>{items}</div></div>")


with tab1:
    st.subheader("Checklist Review - graded by department")
    st.caption("Each SPS checklist item is judged against the RFP. GO means addressed "
               "and compliant, REVIEW means not found or needs a manual check, and "
               "NO-GO means a hard company rule is broken. The score on each department "
               "is the average match strength for its items.")
    depts = list(result["compliance"].keys())
    left, right = st.columns(2)
    for idx, dept in enumerate(depts):
        target = left if idx % 2 == 0 else right
        target.markdown(_dept_card_html(dept, result["compliance"][dept],
                                        dept_scores[dept]),
                        unsafe_allow_html=True)

with tab2:
    st.subheader("Deliverables - what we need to provide")
    if result["deliverables"]:
        for d in result["deliverables"]:
            st.markdown(f"<div class='item-card'>{d}</div>", unsafe_allow_html=True)
    else:
        st.write("No explicit deliverables detected. Review the scope of work section manually.")

with tab3:
    st.subheader("Evaluation Criteria - how the client will judge our proposal")
    if result["evaluation"]:
        df = pd.DataFrame(
            [{"Criterion": e["criterion"], "Weight": e["weight"] or "-"}
             for e in result["evaluation"]]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.write("No scored evaluation criteria detected. Review the evaluation section manually.")

with tab4:
    st.subheader("Automatic decision rules")
    if result["decisions"]:
        for name, dec, reason in result["decisions"]:
            st.markdown(f"<div class='item-card'><b>{name}: {dec}</b><br>{reason}</div>",
                        unsafe_allow_html=True)
    else:
        st.write("No automatic GO / NO-GO rules were triggered by this document.")

# --------------------------------------------------------------------------- #
#  Exports
# --------------------------------------------------------------------------- #
st.markdown("---")
st.subheader("Export results")
e1, e2, e3 = st.columns(3)

e1.download_button(
    "Download compliance checklist (CSV)",
    full_df.to_csv(index=False).encode("utf-8"),
    file_name="compliance_checklist.csv",
    mime="text/csv",
)

summary = {
    "file": filename,
    "bid_readiness": readiness_display,
    "blocked": blocked,
    "recommendation": verdict,
    "recommendation_reason": why,
    "department_scores": dept_scores,
    "requirements_addressed": f"{len(matches)} / {total}",
    "requirements_missing": len(missing),
    "missing_requirements": [f"{r['Department']}: {r['Checklist Item']}" for r in missing],
    "deliverables": result["deliverables"],
    "evaluation_criteria": result["evaluation"],
    "decisions": [{"area": n, "decision": d, "reason": r} for n, d, r in result["decisions"]],
}
e2.download_button(
    "Download full summary (JSON)",
    json.dumps(summary, indent=2).encode("utf-8"),
    file_name="rfp_summary.json",
    mime="application/json",
)

deliv_txt = "DELIVERABLES\n\n" + "\n".join(f"- {d}" for d in result["deliverables"])
e3.download_button(
    "Download deliverables (TXT)",
    deliv_txt.encode("utf-8"),
    file_name="deliverables.txt",
    mime="text/plain",
)
