"""
Rich terminal rendering for analysis results and iteration comparisons.
"""

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from models import AnalysisResult

console = Console()

# ── helpers ──────────────────────────────────────────────────────────────────

_SCORE_COLORS = {range(0, 50): "red", range(50, 70): "yellow", range(70, 101): "green"}


def _score_color(score: int) -> str:
    for r, color in _SCORE_COLORS.items():
        if score in r:
            return color
    return "white"


def _score_bar(score: int, width: int = 20) -> Text:
    filled = round(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    color = _score_color(score)
    t = Text()
    t.append(bar, style=color)
    t.append(f"  {score}%", style=f"bold {color}")
    return t


def _importance_style(importance: str) -> str:
    return {"critical": "bold red", "important": "yellow", "nice_to_have": "dim"}.get(
        importance, ""
    )


def _strength_style(strength: str) -> str:
    return {"strong": "green", "moderate": "yellow", "weak": "red"}.get(strength, "")


def _impact_style(impact: str) -> str:
    return {"high": "bold green", "medium": "yellow", "low": "dim"}.get(impact, "")


def _timeline_label(t: str) -> str:
    return {
        "immediate": "Now",
        "1_week": "1 wk",
        "1_month": "1 mo",
        "3_months": "3 mo",
    }.get(t, t)


# ── main render ──────────────────────────────────────────────────────────────


def render_analysis(result: AnalysisResult) -> None:
    console.print()
    console.print(
        Panel(
            f"[bold white]{result.job_title}[/bold white]  @  [cyan]{result.company_name}[/cyan]\n"
            f"[dim]Analyzed {result.analysis_timestamp[:19].replace('T', ' ')}[/dim]",
            title="[bold]RESUME MATCH ANALYSIS[/bold]",
            border_style="blue",
        )
    )

    _render_scores(result)
    _render_summary(result)
    _render_matched_skills(result)
    _render_skill_gaps(result)
    _render_resume_edits(result)
    _render_keywords(result)
    _render_action_items(result)
    console.print()


def _render_scores(result: AnalysisResult) -> None:
    s = result.match_scores
    scores = [
        ("Overall Match", s.overall),
        ("Technical Skills", s.technical_skills),
        ("Experience Level", s.experience_level),
        ("Education / Creds", s.education_credentials),
        ("Soft Skills / Leadership", s.soft_skills_leadership),
        ("Industry Knowledge", s.industry_knowledge),
    ]

    console.print(Rule("[bold]MATCH SCORES[/bold]", style="blue"))
    for label, score in scores:
        bar = _score_bar(score)
        line = Text(f"  {label:<26}")
        line.append_text(bar)
        console.print(line)
    console.print()


def _render_summary(result: AnalysisResult) -> None:
    console.print(Rule("[bold]EXECUTIVE SUMMARY[/bold]", style="blue"))
    console.print(Panel(result.executive_summary, border_style="dim"))
    console.print()


def _render_matched_skills(result: AnalysisResult) -> None:
    if not result.matched_skills:
        return
    console.print(Rule(f"[bold]MATCHED SKILLS[/bold] ({len(result.matched_skills)})", style="green"))
    t = Table(show_header=True, header_style="bold green", box=None, padding=(0, 1))
    t.add_column("Skill", style="white", min_width=20)
    t.add_column("Match", min_width=10)
    t.add_column("Job Requirement", style="dim")
    t.add_column("Your Evidence", style="cyan")

    for ms in sorted(result.matched_skills, key=lambda x: {"strong": 0, "moderate": 1, "weak": 2}[x.strength]):
        t.add_row(
            ms.skill,
            Text(ms.strength.upper(), style=_strength_style(ms.strength)),
            ms.job_requirement,
            ms.evidence_in_resume,
        )
    console.print(t)
    console.print()


def _render_skill_gaps(result: AnalysisResult) -> None:
    if not result.skill_gaps:
        return
    console.print(Rule(f"[bold]SKILL GAPS[/bold] ({len(result.skill_gaps)})", style="red"))
    t = Table(show_header=True, header_style="bold red", box=None, padding=(0, 1))
    t.add_column("Skill", style="white", min_width=20)
    t.add_column("Priority", min_width=12)
    t.add_column("Quick Fix?", min_width=10)
    t.add_column("Why It Matters", style="dim", min_width=30)
    t.add_column("How to Address", style="cyan")

    order = {"critical": 0, "important": 1, "nice_to_have": 2}
    for gap in sorted(result.skill_gaps, key=lambda x: order[x.importance]):
        t.add_row(
            gap.skill,
            Text(gap.importance.upper().replace("_", " "), style=_importance_style(gap.importance)),
            "[green]Yes[/green]" if gap.addressable_quickly else "[red]No[/red]",
            gap.reasoning,
            gap.how_to_address,
        )
    console.print(t)
    console.print()


def _render_resume_edits(result: AnalysisResult) -> None:
    if not result.resume_edits:
        return
    console.print(Rule(f"[bold]SUGGESTED RESUME EDITS[/bold] ({len(result.resume_edits)})", style="yellow"))
    order = {"high": 0, "medium": 1, "low": 2}
    for edit in sorted(result.resume_edits, key=lambda x: order[x.impact]):
        impact_color = _impact_style(edit.impact)
        header = (
            f"[{impact_color}][{edit.impact.upper()} IMPACT][/{impact_color}]"
            f"  [bold]{edit.section}[/bold]"
        )
        body = (
            f"[dim]Issue:[/dim]   {edit.issue}\n"
            f"[dim]Change:[/dim]  [cyan]{edit.suggested_change}[/cyan]\n"
            f"[dim]Why:[/dim]     {edit.reasoning}"
        )
        console.print(Panel(body, title=header, border_style="yellow", padding=(0, 1)))
    console.print()


def _render_keywords(result: AnalysisResult) -> None:
    if not result.keywords_to_add and not result.strengths_to_emphasize:
        return
    console.print(Rule("[bold]KEYWORDS & STRENGTHS[/bold]", style="blue"))
    if result.keywords_to_add:
        kw_text = "  ".join(f"[cyan]{k}[/cyan]" for k in result.keywords_to_add)
        console.print(Panel(kw_text, title="[bold]Add These Keywords (ATS)[/bold]", border_style="cyan"))
    if result.strengths_to_emphasize:
        st_text = "  ".join(f"[green]{s}[/green]" for s in result.strengths_to_emphasize)
        console.print(Panel(st_text, title="[bold]Emphasize These Strengths[/bold]", border_style="green"))
    console.print()


def _render_action_items(result: AnalysisResult) -> None:
    if not result.action_items:
        return
    console.print(Rule("[bold]PRIORITY ACTION LIST[/bold]", style="magenta"))
    t = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1))
    t.add_column("#", style="bold", min_width=3)
    t.add_column("Timeline", min_width=7)
    t.add_column("Impact", min_width=8)
    t.add_column("Effort", min_width=8)
    t.add_column("Category", style="dim", min_width=18)
    t.add_column("Action", style="white")
    t.add_column("Details", style="dim")

    for item in sorted(result.action_items, key=lambda x: x.priority):
        t.add_row(
            str(item.priority),
            Text(_timeline_label(item.timeline), style="bold cyan"),
            Text(item.impact.upper(), style=_impact_style(item.impact)),
            Text(item.effort.upper(), style=_impact_style(item.effort)),
            item.category.replace("_", " ").title(),
            item.action,
            item.details,
        )
    console.print(t)


# ── iteration comparison ──────────────────────────────────────────────────────


def render_comparison(session: dict) -> None:
    iterations = session["iterations"]
    if len(iterations) < 2:
        console.print("[yellow]Need at least 2 iterations to compare.[/yellow]")
        return

    console.print()
    console.print(
        Panel(
            f"[bold]{session['session_name']}[/bold]  —  {len(iterations)} iterations",
            title="[bold]ITERATION COMPARISON[/bold]",
            border_style="magenta",
        )
    )

    score_keys = [
        ("overall", "Overall"),
        ("technical_skills", "Technical"),
        ("experience_level", "Experience"),
        ("education_credentials", "Education"),
        ("soft_skills_leadership", "Soft Skills"),
        ("industry_knowledge", "Industry Know."),
    ]

    t = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    t.add_column("Metric", style="white", min_width=20)
    for it in iterations:
        t.add_column(
            f"v{it['iteration']}\n{Path(it['resume_file']).name[:16]}",
            min_width=14,
            justify="right",
        )
    t.add_column("Δ v1→last", min_width=10, justify="right")

    for key, label in score_keys:
        scores = [it["result"]["match_scores"][key] for it in iterations]
        delta = scores[-1] - scores[0]
        delta_text = Text(
            f"{'+' if delta >= 0 else ''}{delta}",
            style="green" if delta > 0 else ("red" if delta < 0 else "dim"),
        )
        row = [label] + [_score_bar(s, width=10) for s in scores] + [delta_text]
        t.add_row(*row)

    console.print(t)
    console.print()


def render_session_history(session: dict) -> None:
    console.print()
    console.print(Rule(f"[bold]SESSION: {session['session_name']}[/bold]", style="blue"))
    console.print(f"  Job source: [cyan]{session['job_source']}[/cyan]")
    console.print(f"  Created:    [dim]{session['created_at'][:19].replace('T', ' ')}[/dim]")
    console.print(f"  Iterations: [bold]{len(session['iterations'])}[/bold]")
    console.print()

    for it in session["iterations"]:
        r = it["result"]
        overall = r["match_scores"]["overall"]
        color = _score_color(overall)
        console.print(
            f"  [bold]v{it['iteration']}[/bold]  "
            f"[dim]{it['timestamp'][:19].replace('T', ' ')}[/dim]  "
            f"[dim]{Path(it['resume_file']).name}[/dim]  "
            f"Overall: [{color}]{overall}%[/{color}]"
        )
    console.print()
