"""
Manages iteration sessions so you can re-analyze the same job posting
against successive versions of a resume and track score improvements.

Session data is stored as JSON files under .sessions/.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

_SESSIONS_DIR = Path(".sessions")


def _path(name: str) -> Path:
    return _SESSIONS_DIR / f"{name}.json"


def session_exists(name: str) -> bool:
    return _path(name).exists()


def load_session(name: str) -> dict:
    p = _path(name)
    if not p.exists():
        raise FileNotFoundError(
            f"Session '{name}' not found. "
            "Create it first with: python main.py analyze <resume> --job-url <url> --session <name>"
        )
    return json.loads(p.read_text(encoding="utf-8"))


def create_session(name: str, job_source: str, job_description: str) -> dict:
    _SESSIONS_DIR.mkdir(exist_ok=True)
    session = {
        "session_name": name,
        "job_source": job_source,
        "job_description": job_description,
        "created_at": datetime.now().isoformat(),
        "iterations": [],
    }
    _save(name, session)
    return session


def add_iteration(name: str, resume_file: str, result_dict: dict) -> dict:
    session = load_session(name)
    iteration = {
        "iteration": len(session["iterations"]) + 1,
        "resume_file": resume_file,
        "timestamp": datetime.now().isoformat(),
        "result": result_dict,
    }
    session["iterations"].append(iteration)
    _save(name, session)
    return iteration


def list_sessions() -> list[str]:
    if not _SESSIONS_DIR.exists():
        return []
    return [p.stem for p in sorted(_SESSIONS_DIR.glob("*.json"))]


def _save(name: str, data: dict) -> None:
    _SESSIONS_DIR.mkdir(exist_ok=True)
    _path(name).write_text(json.dumps(data, indent=2), encoding="utf-8")
