"""
Jupyter widget UI for Resume Analyzer.

Usage (in a notebook cell):
    from ui import launch
    launch()
"""

import os
import sys
import tempfile
from pathlib import Path

import ipywidgets as widgets
from IPython.display import HTML, clear_output, display

# Ensure the project root is importable when the notebook lives elsewhere.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv

load_dotenv()

import display as display_module
import session as session_store
from analyzer import run_analysis
from display import render_analysis, render_comparison, render_session_history
from parsers import parse_resume
from scraper import scrape_job_posting


# ── internal helpers ──────────────────────────────────────────────────────────

def _extract_upload(widget: widgets.FileUpload) -> tuple[Path, str] | None:
    """Save the uploaded file to a temp path. Returns (path, original_filename)."""
    if not widget.value:
        return None
    try:
        # ipywidgets 8.x: value is a tuple of dicts
        info = widget.value[0]
        name, content = info["name"], info["content"]
    except (IndexError, KeyError, TypeError):
        # ipywidgets 7.x: value is {filename: {metadata, content}}
        name, meta = next(iter(widget.value.items()))
        content = meta["content"]

    suffix = Path(name).suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name), name


def _render_into(output_widget: widgets.Output, render_fn, *args) -> None:
    """
    Render a display.py function by capturing its Rich output as HTML,
    then injecting that HTML into an Output widget.

    This works by temporarily replacing the module-level console with a
    record-mode console, exporting to HTML, then restoring the original.
    """
    from rich.console import Console

    buf = Console(record=True, width=110, highlight=False)
    old = display_module.console
    display_module.console = buf
    try:
        render_fn(*args)
    finally:
        display_module.console = old

    html = buf.export_html(inline_styles=True)
    with output_widget:
        display(HTML(html))


def _status_err(msg: str) -> str:
    return f'<span style="color:#c0392b;font-weight:bold">⚠ {msg}</span>'


def _status_ok(msg: str) -> str:
    return f'<span style="color:#27ae60;font-weight:bold">✓ {msg}</span>'


def _status_info(msg: str) -> str:
    return f'<span style="color:#555;font-style:italic">{msg}</span>'


def _refresh_dropdowns(*dropdowns: widgets.Dropdown) -> None:
    names = session_store.list_sessions()
    options = names if names else ["(no sessions yet)"]
    for dd in dropdowns:
        dd.options = options
        if names:
            dd.value = names[0]


# ── widget layout constants ───────────────────────────────────────────────────

_WIDE = widgets.Layout(width="530px")
_LABEL = {"description_width": "135px"}
_HR = widgets.HTML("<hr style='border:none;border-top:1px solid #e0e0e0;margin:10px 0'>")
_DIVIDER = widgets.HTML(
    "<div style='text-align:center;color:#bbb;font-size:12px;margin:2px 80px'>— or paste below —</div>"
)


# ── Tab 1: New Analysis ───────────────────────────────────────────────────────

def _build_tab_analyze(t2_session_dd: widgets.Dropdown, t3_session_dd: widgets.Dropdown):
    upload = widgets.FileUpload(
        accept=".pdf,.docx", multiple=False,
        description="Resume:", style=_LABEL,
        layout=widgets.Layout(width="400px"),
    )
    url_input = widgets.Text(
        placeholder="https://company.com/jobs/...",
        description="Job URL:", style=_LABEL, layout=_WIDE,
    )
    paste_input = widgets.Textarea(
        placeholder="Paste the full job description here (used only when Job URL is empty)",
        description="Job text:", rows=7, style=_LABEL, layout=_WIDE,
    )
    session_input = widgets.Text(
        placeholder="e.g. google-swe  (leave blank to skip saving)",
        description="Session name:", style=_LABEL, layout=_WIDE,
    )
    run_btn = widgets.Button(
        description="▶  Run Analysis", button_style="primary",
        layout=widgets.Layout(width="180px", height="36px"),
    )
    status = widgets.HTML()
    out = widgets.Output()

    def on_run(_):
        out.clear_output()
        status.value = _status_info("Starting…")
        run_btn.disabled = True

        try:
            saved = _extract_upload(upload)
            if not saved:
                status.value = _status_err("Please upload a resume (.pdf or .docx).")
                return
            tmp_path, orig_name = saved

            try:
                resume_text = parse_resume(tmp_path)
            except ValueError as e:
                status.value = _status_err(str(e))
                return
            finally:
                os.unlink(tmp_path)

            if url_input.value.strip():
                status.value = _status_info(f"Fetching job posting…")
                try:
                    job_desc = scrape_job_posting(url_input.value.strip())
                except RuntimeError as e:
                    status.value = _status_err(str(e))
                    return
                job_source = url_input.value.strip()
            elif paste_input.value.strip():
                job_desc = paste_input.value.strip()
                job_source = "(pasted text)"
            else:
                status.value = _status_err("Provide a Job URL or paste the job description.")
                return

            status.value = _status_info("Analyzing with Claude…")
            try:
                result = run_analysis(resume_text, job_desc)
            except RuntimeError as e:
                status.value = _status_err(str(e))
                return

            name = session_input.value.strip()
            if name:
                if not session_store.session_exists(name):
                    session_store.create_session(name, job_source, job_desc)
                session_store.add_iteration(name, orig_name, result.model_dump())
                status.value = _status_ok(f"Done — saved to session '{name}'.")
                _refresh_dropdowns(t2_session_dd, t3_session_dd)
            else:
                status.value = _status_ok("Done.")

            _render_into(out, render_analysis, result)

        except Exception as e:
            status.value = _status_err(f"Unexpected error: {e}")
        finally:
            run_btn.disabled = False

    run_btn.on_click(on_run)

    tab = widgets.VBox([
        widgets.HTML("<h3 style='margin:6px 0 12px'>Analyze Resume vs Job Posting</h3>"),
        upload,
        _HR,
        url_input,
        _DIVIDER,
        paste_input,
        _HR,
        session_input,
        widgets.HTML("<p style='color:#888;font-size:12px;margin:2px 0 8px'>"
                     "A session name lets you iterate on the same job posting "
                     "and track score changes over resume versions.</p>"),
        run_btn,
        status,
        out,
    ], layout=widgets.Layout(padding="16px"))

    return tab


# ── Tab 2: Iterate ────────────────────────────────────────────────────────────

def _build_tab_iterate():
    names = session_store.list_sessions()
    session_dd = widgets.Dropdown(
        options=names or ["(no sessions yet)"],
        description="Session:", style=_LABEL, layout=_WIDE,
    )
    upload = widgets.FileUpload(
        accept=".pdf,.docx", multiple=False,
        description="New resume:", style=_LABEL,
        layout=widgets.Layout(width="400px"),
    )
    run_btn = widgets.Button(
        description="▶  Run Iteration", button_style="primary",
        layout=widgets.Layout(width="180px", height="36px"),
    )
    status = widgets.HTML()
    out = widgets.Output()

    def on_run(_):
        out.clear_output()
        status.value = _status_info("Starting…")
        run_btn.disabled = True

        try:
            name = session_dd.value
            if name == "(no sessions yet)":
                status.value = _status_err("No sessions yet. Run an analysis with a session name first.")
                return

            try:
                sess = session_store.load_session(name)
            except FileNotFoundError as e:
                status.value = _status_err(str(e))
                return

            saved = _extract_upload(upload)
            if not saved:
                status.value = _status_err("Please upload a resume.")
                return
            tmp_path, orig_name = saved

            try:
                resume_text = parse_resume(tmp_path)
            except ValueError as e:
                status.value = _status_err(str(e))
                return
            finally:
                os.unlink(tmp_path)

            status.value = _status_info(
                "Analyzing with Claude — job description pulled from session "
                "(prompt cache may apply)…"
            )
            try:
                result = run_analysis(resume_text, sess["job_description"])
            except RuntimeError as e:
                status.value = _status_err(str(e))
                return

            session_store.add_iteration(name, orig_name, result.model_dump())
            updated = session_store.load_session(name)
            n = len(updated["iterations"])
            status.value = _status_ok(f"Saved — iteration {n} of session '{name}'.")

            _render_into(out, render_analysis, result)
            if n >= 2:
                _render_into(out, render_comparison, updated)

        except Exception as e:
            status.value = _status_err(f"Unexpected error: {e}")
        finally:
            run_btn.disabled = False

    run_btn.on_click(on_run)

    tab = widgets.VBox([
        widgets.HTML("<h3 style='margin:6px 0 4px'>Iterate on an Existing Session</h3>"),
        widgets.HTML("<p style='color:#666;font-size:13px;margin:0 0 12px'>"
                     "Upload a revised resume to re-run analysis against the saved "
                     "job description. Score changes are shown automatically.</p>"),
        session_dd,
        upload,
        run_btn,
        status,
        out,
    ], layout=widgets.Layout(padding="16px"))

    return tab, session_dd


# ── Tab 3: History / Compare ──────────────────────────────────────────────────

def _build_tab_history():
    names = session_store.list_sessions()
    session_dd = widgets.Dropdown(
        options=names or ["(no sessions yet)"],
        description="Session:", style=_LABEL, layout=_WIDE,
    )
    hist_btn = widgets.Button(
        description="View History",
        layout=widgets.Layout(width="160px"),
    )
    cmp_btn = widgets.Button(
        description="Compare Iterations", button_style="info",
        layout=widgets.Layout(width="190px"),
    )
    out = widgets.Output()

    def on_history(_):
        out.clear_output()
        try:
            sess = session_store.load_session(session_dd.value)
            _render_into(out, render_session_history, sess)
        except Exception as e:
            with out:
                display(HTML(_status_err(str(e))))

    def on_compare(_):
        out.clear_output()
        try:
            sess = session_store.load_session(session_dd.value)
            _render_into(out, render_comparison, sess)
        except Exception as e:
            with out:
                display(HTML(_status_err(str(e))))

    hist_btn.on_click(on_history)
    cmp_btn.on_click(on_compare)

    tab = widgets.VBox([
        widgets.HTML("<h3 style='margin:6px 0 12px'>Session History & Comparison</h3>"),
        session_dd,
        widgets.HBox(
            [hist_btn, cmp_btn],
            layout=widgets.Layout(gap="10px", margin="4px 0 0"),
        ),
        out,
    ], layout=widgets.Layout(padding="16px"))

    return tab, session_dd


# ── public entry point ────────────────────────────────────────────────────────

def launch() -> None:
    """Render the Resume Analyzer UI inside a Jupyter notebook cell."""
    # Build tabs — pass shared dropdowns forward so tab 1 can refresh them.
    tab2, t2_session_dd = _build_tab_iterate()
    tab3, t3_session_dd = _build_tab_history()
    tab1 = _build_tab_analyze(t2_session_dd, t3_session_dd)

    tabs = widgets.Tab(children=[tab1, tab2, tab3])
    tabs.set_title(0, "🔍 Analyze")
    tabs.set_title(1, "🔄 Iterate")
    tabs.set_title(2, "📊 History")

    display(HTML("""
    <style>
      .widget-tab > .p-TabBar .p-TabBar-tab,
      .widget-tab > .lm-TabBar .lm-TabBar-tab {
        font-size: 13px;
        padding: 6px 20px;
      }
    </style>
    """))
    display(tabs)
