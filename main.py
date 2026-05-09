"""
Resume Analyzer — CLI tool to compare a resume against a job posting using Claude.

Usage examples:
  python main.py analyze resume.pdf --job-url https://company.com/jobs/123
  python main.py analyze resume.pdf --job-url https://... --session my-app
  python main.py iterate my-app resume_v2.docx
  python main.py history my-app
  python main.py compare my-app
  python main.py sessions
"""

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

import session as session_store
from analyzer import run_analysis
from display import (
    console,
    render_analysis,
    render_comparison,
    render_session_history,
)
from parsers import parse_resume
from scraper import scrape_job_posting

load_dotenv()

app = typer.Typer(
    name="resume-analyzer",
    help="Analyze a resume against a job posting using Claude.",
    add_completion=False,
)
err_console = Console(stderr=True, style="bold red")


# ── helpers ───────────────────────────────────────────────────────────────────


def _get_job_description(job_url: Optional[str], job_file: Optional[Path]) -> tuple[str, str]:
    """Return (source_label, job_description_text)."""
    if job_url and job_file:
        err_console.print("Provide either --job-url or --job-file, not both.")
        raise typer.Exit(1)

    if job_url:
        console.print(f"  Fetching job posting: [cyan]{job_url}[/cyan]")
        try:
            text = scrape_job_posting(job_url)
        except RuntimeError as e:
            err_console.print(str(e))
            raise typer.Exit(1)
        if len(text) < 100:
            err_console.print(
                "Scraped text is too short — the page may require JavaScript. "
                "Save the job description to a .txt file and use --job-file instead."
            )
            raise typer.Exit(1)
        console.print(f"  [dim]Scraped {len(text):,} characters[/dim]")
        return job_url, text

    if job_file:
        if not job_file.exists():
            err_console.print(f"File not found: {job_file}")
            raise typer.Exit(1)
        text = job_file.read_text(encoding="utf-8")
        return str(job_file), text

    err_console.print("Provide either --job-url <url> or --job-file <path.txt>.")
    raise typer.Exit(1)


def _load_resume(resume: Path) -> str:
    if not resume.exists():
        err_console.print(f"Resume file not found: {resume}")
        raise typer.Exit(1)
    console.print(f"  Parsing resume: [cyan]{resume.name}[/cyan]")
    try:
        text = parse_resume(resume)
    except ValueError as e:
        err_console.print(str(e))
        raise typer.Exit(1)
    console.print(f"  [dim]Extracted {len(text):,} characters[/dim]")
    return text


# ── commands ──────────────────────────────────────────────────────────────────


@app.command()
def analyze(
    resume: Annotated[Path, typer.Argument(help="Resume file (.pdf or .docx)")],
    job_url: Annotated[Optional[str], typer.Option(help="URL of the job posting")] = None,
    job_file: Annotated[
        Optional[Path], typer.Option(help="Path to a plain-text job description file")
    ] = None,
    session: Annotated[
        Optional[str],
        typer.Option(help="Session name to save this analysis for iteration tracking"),
    ] = None,
    output_json: Annotated[
        bool, typer.Option("--json", help="Print raw JSON result instead of formatted output")
    ] = False,
) -> None:
    """Analyze a resume against a job posting."""
    console.print("\n[bold blue]Resume Analyzer[/bold blue]")
    console.rule(style="blue")

    job_source, job_desc = _get_job_description(job_url, job_file)
    resume_text = _load_resume(resume)

    console.print("  Running analysis with Claude…")
    try:
        result = run_analysis(resume_text, job_desc)
    except RuntimeError as e:
        err_console.print(str(e))
        raise typer.Exit(1)

    if session:
        if session_store.session_exists(session):
            sess = session_store.load_session(session)
        else:
            sess = session_store.create_session(session, job_source, job_desc)
        session_store.add_iteration(session, str(resume), result.model_dump())
        console.print(
            f"  [dim]Saved to session '{session}' "
            f"(iteration {len(sess['iterations']) + 1})[/dim]"
        )

    if output_json:
        print(json.dumps(result.model_dump(), indent=2))
    else:
        render_analysis(result)


@app.command()
def iterate(
    session_name: Annotated[str, typer.Argument(help="Session name created during analyze")],
    resume: Annotated[Path, typer.Argument(help="New resume version (.pdf or .docx)")],
    output_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Analyze a new resume version against a saved session's job description."""
    console.print(f"\n[bold blue]Resume Analyzer[/bold blue]  — iteration for session [cyan]{session_name}[/cyan]")
    console.rule(style="blue")

    try:
        sess = session_store.load_session(session_name)
    except FileNotFoundError as e:
        err_console.print(str(e))
        raise typer.Exit(1)

    job_desc = sess["job_description"]
    resume_text = _load_resume(resume)

    console.print(
        f"  Re-using job description from session  "
        f"[dim]({len(job_desc):,} chars, prompt cache may apply)[/dim]"
    )
    console.print("  Running analysis with Claude…")

    try:
        result = run_analysis(resume_text, job_desc)
    except RuntimeError as e:
        err_console.print(str(e))
        raise typer.Exit(1)

    session_store.add_iteration(session_name, str(resume), result.model_dump())

    if output_json:
        print(json.dumps(result.model_dump(), indent=2))
    else:
        render_analysis(result)

    # Automatically show score comparison after adding the new iteration.
    updated_sess = session_store.load_session(session_name)
    if len(updated_sess["iterations"]) >= 2:
        render_comparison(updated_sess)


@app.command()
def compare(
    session_name: Annotated[str, typer.Argument(help="Session name to compare iterations of")],
) -> None:
    """Show a score comparison table across all iterations in a session."""
    try:
        sess = session_store.load_session(session_name)
    except FileNotFoundError as e:
        err_console.print(str(e))
        raise typer.Exit(1)
    render_comparison(sess)


@app.command()
def history(
    session_name: Annotated[str, typer.Argument(help="Session name")],
) -> None:
    """Show the iteration history of a session."""
    try:
        sess = session_store.load_session(session_name)
    except FileNotFoundError as e:
        err_console.print(str(e))
        raise typer.Exit(1)
    render_session_history(sess)


@app.command()
def sessions() -> None:
    """List all saved sessions."""
    names = session_store.list_sessions()
    if not names:
        console.print("[dim]No sessions found. Run 'analyze' with --session to create one.[/dim]")
        return
    for name in names:
        try:
            sess = session_store.load_session(name)
            n = len(sess["iterations"])
            last_overall = (
                sess["iterations"][-1]["result"]["match_scores"]["overall"] if n else "—"
            )
            console.print(
                f"  [cyan]{name}[/cyan]  "
                f"[dim]{n} iteration(s)[/dim]  "
                f"last overall: [bold]{last_overall}%[/bold]"
            )
        except Exception:
            console.print(f"  [yellow]{name}[/yellow]  [dim](could not load)[/dim]")


if __name__ == "__main__":
    app()
