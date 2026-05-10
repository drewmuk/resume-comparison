import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from analyzer import run_analysis
from models import AnalysisResult
from parsers import parse_resume
from scraper import scrape_job_posting
import session as session_store

# ── page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Resume Analyzer",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── colour / badge helpers ────────────────────────────────────────────────────

def _score_color(s: int) -> str:
    return "#27ae60" if s >= 70 else "#e67e22" if s >= 50 else "#e74c3c"


def _importance_icon(imp: str) -> str:
    return {"critical": "🔴", "important": "🟡", "nice_to_have": "⚪"}.get(imp, "")


def _impact_icon(imp: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "⚪"}.get(imp, "")


def _timeline_label(t: str) -> str:
    return {"immediate": "Now", "1_week": "1 wk", "1_month": "1 mo", "3_months": "3 mo"}.get(t, t)


def _pill(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:white;padding:2px 9px;'
        f'border-radius:10px;font-size:12px;font-weight:600;white-space:nowrap">'
        f"{text}</span>"
    )


def _score_bar_html(score: int, width_px: int = 140) -> str:
    color = _score_color(score)
    filled = round(score / 100 * width_px)
    return (
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<div style="background:#e8e8e8;border-radius:4px;height:8px;width:{width_px}px;flex-shrink:0">'
        f'<div style="background:{color};width:{filled}px;height:8px;border-radius:4px"></div></div>'
        f'<span style="color:{color};font-weight:bold;font-size:13px">{score}%</span>'
        f"</div>"
    )


# ── file upload helper ────────────────────────────────────────────────────────

def _save_upload(uploaded_file) -> tuple[Path, str]:
    suffix = Path(uploaded_file.name).suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(uploaded_file.read())
    tmp.close()
    return Path(tmp.name), uploaded_file.name


# ── display: analysis result ──────────────────────────────────────────────────

def show_scores(result: AnalysisResult) -> None:
    s = result.match_scores
    pairs = [
        ("Overall", s.overall),
        ("Technical", s.technical_skills),
        ("Experience", s.experience_level),
        ("Education", s.education_credentials),
        ("Soft Skills", s.soft_skills_leadership),
        ("Industry", s.industry_knowledge),
    ]
    cols = st.columns(len(pairs))
    for col, (label, score) in zip(cols, pairs):
        c = _score_color(score)
        col.markdown(
            f'<div style="text-align:center;padding:8px 4px">'
            f'<div style="font-size:12px;color:#888;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px">{label}</div>'
            f'<div style="font-size:30px;font-weight:700;color:{c};line-height:1">{score}%</div>'
            f'<div style="background:#e8e8e8;border-radius:4px;height:6px;margin-top:6px">'
            f'<div style="background:{c};width:{score}%;height:6px;border-radius:4px"></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


def show_matched_skills(result: AnalysisResult) -> None:
    if not result.matched_skills:
        return
    st.subheader(f"✅ Matched Skills  ({len(result.matched_skills)})")
    rows = sorted(
        result.matched_skills,
        key=lambda x: {"strong": 0, "moderate": 1, "weak": 2}[x.strength],
    )
    strength_colors = {"strong": "#27ae60", "moderate": "#e67e22", "weak": "#e74c3c"}
    html = (
        '<table style="width:100%;border-collapse:collapse;font-size:13.5px">'
        '<tr style="background:#f5f5f5;border-bottom:2px solid #ddd">'
        '<th style="padding:8px 10px;text-align:left">Skill</th>'
        '<th style="padding:8px 10px;text-align:center">Match</th>'
        '<th style="padding:8px 10px;text-align:left">Job Requirement</th>'
        '<th style="padding:8px 10px;text-align:left">Your Evidence</th>'
        "</tr>"
    )
    for i, ms in enumerate(rows):
        bg = "#fff" if i % 2 == 0 else "#fafafa"
        c = strength_colors[ms.strength]
        html += (
            f'<tr style="background:{bg};border-bottom:1px solid #eee">'
            f'<td style="padding:7px 10px;font-weight:500">{ms.skill}</td>'
            f'<td style="padding:7px 10px;text-align:center">{_pill(ms.strength.upper(), c)}</td>'
            f'<td style="padding:7px 10px;color:#555">{ms.job_requirement}</td>'
            f'<td style="padding:7px 10px;color:#2471a3">{ms.evidence_in_resume}</td>'
            "</tr>"
        )
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)
    st.write("")


def show_skill_gaps(result: AnalysisResult) -> None:
    if not result.skill_gaps:
        return
    st.subheader(f"❌ Skill Gaps  ({len(result.skill_gaps)})")
    order = {"critical": 0, "important": 1, "nice_to_have": 2}
    for gap in sorted(result.skill_gaps, key=lambda x: order[x.importance]):
        icon = _importance_icon(gap.importance)
        label_text = gap.importance.replace("_", " ").upper()
        quick = "✅ quick fix" if gap.addressable_quickly else "⏳ long-term"
        with st.expander(
            f"{icon} {label_text}  ·  **{gap.skill}**  ·  {quick}",
            expanded=(gap.importance == "critical"),
        ):
            st.markdown(f"**Why it matters for this role:** {gap.reasoning}")
            st.markdown(f"**How to address:** {gap.how_to_address}")
    st.write("")


def show_resume_edits(result: AnalysisResult) -> None:
    if not result.resume_edits:
        return
    st.subheader(f"📝 Suggested Resume Edits  ({len(result.resume_edits)})")
    order = {"high": 0, "medium": 1, "low": 2}
    for edit in sorted(result.resume_edits, key=lambda x: order[x.impact]):
        icon = _impact_icon(edit.impact)
        with st.expander(
            f"{icon} {edit.impact.upper()} IMPACT  ·  **{edit.section}** — {edit.issue}",
            expanded=(edit.impact == "high"),
        ):
            st.markdown("**Suggested change:**")
            st.info(edit.suggested_change)
            st.markdown(f"**Why:** {edit.reasoning}")
    st.write("")


def show_keywords(result: AnalysisResult) -> None:
    col1, col2 = st.columns(2)
    with col1:
        if result.keywords_to_add:
            st.subheader("🔑 Keywords to Add (ATS)")
            st.markdown(
                "  ".join(
                    _pill(k, "#2471a3") for k in result.keywords_to_add
                ),
                unsafe_allow_html=True,
            )
    with col2:
        if result.strengths_to_emphasize:
            st.subheader("💪 Strengths to Emphasize")
            st.markdown(
                "  ".join(
                    _pill(s, "#1e8449") for s in result.strengths_to_emphasize
                ),
                unsafe_allow_html=True,
            )
    st.write("")


def show_action_items(result: AnalysisResult) -> None:
    if not result.action_items:
        return
    st.subheader("🎯 Priority Action List")
    timeline_colors = {
        "immediate": "#c0392b",
        "1_week": "#d35400",
        "1_month": "#2471a3",
        "3_months": "#6c3483",
    }
    for item in sorted(result.action_items, key=lambda x: x.priority):
        tl = _timeline_label(item.timeline)
        tc = timeline_colors.get(item.timeline, "#666")
        impact_icon = _impact_icon(item.impact)
        with st.expander(
            f"#{item.priority}  ·  {tl}  ·  {impact_icon} {item.impact.upper()} IMPACT  ·  {item.action}",
            expanded=(item.priority <= 3),
        ):
            c1, c2 = st.columns(2)
            c1.markdown(f"**Category:** {item.category.replace('_', ' ').title()}")
            c2.markdown(f"**Effort:** {item.effort.upper()}")
            st.markdown(f"**Details:** {item.details}")
    st.write("")


def show_analysis(result: AnalysisResult) -> None:
    st.markdown(f"### {result.job_title}")
    st.caption(
        f"{result.company_name}  ·  "
        f"Analyzed {result.analysis_timestamp[:19].replace('T', ' ')}"
    )
    st.divider()

    show_scores(result)
    st.divider()

    with st.expander("📋 Executive Summary", expanded=True):
        st.write(result.executive_summary)
    st.write("")

    show_matched_skills(result)
    show_skill_gaps(result)
    show_resume_edits(result)
    show_keywords(result)
    st.divider()
    show_action_items(result)


# ── display: comparison ───────────────────────────────────────────────────────

def show_comparison(sess: dict) -> None:
    iterations = sess["iterations"]
    if len(iterations) < 2:
        st.info("Need at least 2 iterations to compare.")
        return

    st.subheader("Score Progression")
    score_keys = [
        ("overall", "Overall"),
        ("technical_skills", "Technical Skills"),
        ("experience_level", "Experience"),
        ("education_credentials", "Education"),
        ("soft_skills_leadership", "Soft Skills"),
        ("industry_knowledge", "Industry"),
    ]

    html = '<table style="width:100%;border-collapse:collapse;font-size:13.5px">'
    html += '<tr style="background:#f5f5f5;border-bottom:2px solid #ddd"><th style="padding:8px 10px;text-align:left">Metric</th>'
    for it in iterations:
        fname = Path(it["resume_file"]).name
        fname_short = fname[:20] + "…" if len(fname) > 20 else fname
        html += (
            f'<th style="padding:8px 10px;text-align:center">v{it["iteration"]}'
            f'<br><span style="font-weight:400;font-size:11px;color:#888">{fname_short}</span></th>'
        )
    html += '<th style="padding:8px 10px;text-align:center">Δ v1 → last</th></tr>'

    for key, label in score_keys:
        scores = [it["result"]["match_scores"][key] for it in iterations]
        delta = scores[-1] - scores[0]
        dc = "#27ae60" if delta > 0 else "#e74c3c" if delta < 0 else "#888"
        ds = f"{'+' if delta >= 0 else ''}{delta}"

        html += f'<tr style="border-bottom:1px solid #eee"><td style="padding:7px 10px;font-weight:500">{label}</td>'
        for score in scores:
            html += f'<td style="padding:7px 10px">{_score_bar_html(score, 100)}</td>'
        html += f'<td style="padding:7px 10px;text-align:center;font-weight:700;color:{dc};font-size:15px">{ds}</td></tr>'

    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)


# ── session state init ────────────────────────────────────────────────────────

for _key in ("result_tab1", "result_tab2", "session_tab2"):
    if _key not in st.session_state:
        st.session_state[_key] = None

# ── header ────────────────────────────────────────────────────────────────────

st.title("📄 Resume Analyzer")
st.caption(
    "Compare a resume against a job posting using Claude — "
    "match scores, skill gaps with reasoning, resume edits, and a prioritized action list."
)

# Optional: API key via sidebar if not in env
if not os.environ.get("ANTHROPIC_API_KEY"):
    with st.sidebar:
        st.subheader("🔑 API Key")
        key_input = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...")
        if key_input:
            os.environ["ANTHROPIC_API_KEY"] = key_input
        else:
            st.warning("Add ANTHROPIC_API_KEY to .env or enter it here.")

# ── tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["🔍 Analyze", "🔄 Iterate", "📊 History & Compare"])

# ── Tab 1: Analyze ────────────────────────────────────────────────────────────

with tab1:
    left, right = st.columns([1, 2], gap="large")

    with left:
        st.subheader("Inputs")
        resume_file = st.file_uploader(
            "Resume (.pdf or .docx)", type=["pdf", "docx"], key="up1"
        )
        job_url = st.text_input(
            "Job Posting URL", placeholder="https://company.com/jobs/..."
        )
        st.caption("— or paste the description below —")
        job_paste = st.text_area(
            "Job Description", height=160,
            placeholder="Paste the full job description here…",
            label_visibility="collapsed",
        )
        session_name = st.text_input(
            "Session name  *(optional)*",
            placeholder="e.g. google-swe",
            help="Saves this analysis so you can iterate on the same job later.",
        )
        run1 = st.button("▶  Run Analysis", type="primary", use_container_width=True)

    with right:
        if run1:
            if not resume_file:
                st.error("Please upload a resume.")
            elif not job_url.strip() and not job_paste.strip():
                st.error("Provide a Job URL or paste the job description.")
            else:
                with st.spinner("Parsing resume…"):
                    tmp, orig_name = _save_upload(resume_file)
                    try:
                        resume_text = parse_resume(tmp)
                    except ValueError as e:
                        st.error(str(e))
                        st.stop()
                    finally:
                        os.unlink(tmp)

                if job_url.strip():
                    with st.spinner("Fetching job posting…"):
                        try:
                            job_desc = scrape_job_posting(job_url.strip())
                            job_source = job_url.strip()
                        except RuntimeError as e:
                            st.error(str(e))
                            st.stop()
                else:
                    job_desc = job_paste.strip()
                    job_source = "(pasted text)"

                with st.spinner("Analyzing with Claude…"):
                    try:
                        result = run_analysis(resume_text, job_desc)
                    except RuntimeError as e:
                        st.error(str(e))
                        st.stop()

                st.session_state.result_tab1 = result

                if session_name.strip():
                    n = session_name.strip()
                    if not session_store.session_exists(n):
                        session_store.create_session(n, job_source, job_desc)
                    session_store.add_iteration(n, orig_name, result.model_dump())
                    st.success(f"Saved to session **{n}**.")

        if st.session_state.result_tab1:
            show_analysis(st.session_state.result_tab1)

# ── Tab 2: Iterate ────────────────────────────────────────────────────────────

with tab2:
    sessions = session_store.list_sessions()

    if not sessions:
        st.info(
            "No sessions yet. Run an analysis on the **Analyze** tab "
            "with a session name to get started."
        )
    else:
        left2, right2 = st.columns([1, 2], gap="large")

        with left2:
            st.subheader("Inputs")
            selected = st.selectbox("Session", sessions)

            if selected:
                sd = session_store.load_session(selected)
                n_iters = len(sd["iterations"])
                st.caption(
                    f"{n_iters} iteration{'s' if n_iters != 1 else ''} saved  ·  "
                    f"{sd['job_source'][:55]}"
                )
                if n_iters and sd["iterations"]:
                    last_score = sd["iterations"][-1]["result"]["match_scores"]["overall"]
                    st.caption(f"Last overall score: **{last_score}%**")

            resume_file2 = st.file_uploader(
                "Updated resume (.pdf or .docx)", type=["pdf", "docx"], key="up2"
            )
            run2 = st.button("▶  Run Iteration", type="primary", use_container_width=True)

        with right2:
            if run2:
                if not resume_file2:
                    st.error("Please upload a resume.")
                else:
                    sd = session_store.load_session(selected)

                    with st.spinner("Parsing resume…"):
                        tmp, orig_name = _save_upload(resume_file2)
                        try:
                            resume_text = parse_resume(tmp)
                        except ValueError as e:
                            st.error(str(e))
                            st.stop()
                        finally:
                            os.unlink(tmp)

                    with st.spinner("Analyzing with Claude (job description from session)…"):
                        try:
                            result = run_analysis(resume_text, sd["job_description"])
                        except RuntimeError as e:
                            st.error(str(e))
                            st.stop()

                    session_store.add_iteration(selected, orig_name, result.model_dump())
                    updated = session_store.load_session(selected)
                    n_now = len(updated["iterations"])

                    st.session_state.result_tab2 = result
                    st.session_state.session_tab2 = selected
                    st.success(f"Saved — iteration **{n_now}** of session **{selected}**.")

            if st.session_state.result_tab2:
                show_analysis(st.session_state.result_tab2)

                if st.session_state.session_tab2:
                    updated = session_store.load_session(st.session_state.session_tab2)
                    if len(updated["iterations"]) >= 2:
                        st.divider()
                        show_comparison(updated)

# ── Tab 3: History & Compare ──────────────────────────────────────────────────

with tab3:
    sessions3 = session_store.list_sessions()

    if not sessions3:
        st.info("No sessions yet.")
    else:
        selected3 = st.selectbox("Session", sessions3, key="sel3")

        if selected3:
            sess = session_store.load_session(selected3)
            iters = sess["iterations"]

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Iterations", len(iters))
            if iters:
                first_s = iters[0]["result"]["match_scores"]["overall"]
                last_s = iters[-1]["result"]["match_scores"]["overall"]
                m2.metric("First Score", f"{first_s}%")
                m3.metric("Latest Score", f"{last_s}%")
                m4.metric("Change", f"{last_s - first_s:+d}%")

            st.caption(
                f"Source: {sess['job_source']}  ·  "
                f"Created: {sess['created_at'][:19].replace('T', ' ')}"
            )
            st.divider()

            # Iteration list
            st.markdown("**Iteration log**")
            for it in iters:
                r = it["result"]
                overall = r["match_scores"]["overall"]
                c = _score_color(overall)
                fname = Path(it["resume_file"]).name
                ts = it["timestamp"][:19].replace("T", " ")
                st.markdown(
                    f'**v{it["iteration"]}** &nbsp; '
                    f'<span style="color:{c};font-weight:700">{overall}%</span> &nbsp; '
                    f'`{fname}` &nbsp; <span style="color:#aaa;font-size:12px">{ts}</span>',
                    unsafe_allow_html=True,
                )

            st.divider()
            show_comparison(sess)

            # Full result drill-down
            if len(iters) >= 1:
                st.divider()
                st.subheader("View Full Analysis")
                iter_options = {
                    f"v{it['iteration']} — {Path(it['resume_file']).name}": it
                    for it in iters
                }
                chosen_label = st.selectbox("Iteration", list(iter_options.keys()))
                if chosen_label:
                    from models import AnalysisResult as AR
                    chosen_data = iter_options[chosen_label]["result"]
                    show_analysis(AR(**chosen_data))
