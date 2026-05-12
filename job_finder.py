"""
Job discovery and batch screening pipeline.

API call budget:
  - Heuristic mode (default):  1 call total  (batch screening only)
  - Smart mode:                2 calls total  (Haiku extraction + batch screening)

Job search hits two free public APIs — no key required:
  • The Muse   (https://www.themuse.com/api/public/jobs)
    Full job descriptions, filterable by category, seniority level, and location.
  • Remotive   (https://remotive.com/api/remote-jobs)
    Remote-only roles; added automatically when the target location is remote/blank.

Batch screening sends all job descriptions in a single Claude call, so cost
scales with ~200 tokens per job rather than a full analysis per job.
"""

import os
import re
import time
from typing import Optional

import anthropic
import requests
from pydantic import BaseModel


# ── data models ───────────────────────────────────────────────────────────────

class SearchTerms(BaseModel):
    job_titles: list[str]
    key_skills: list[str]
    seniority: str = ""
    industries: list[str] = []


class JobListing(BaseModel):
    index: int
    title: str
    company: str
    url: str
    description: str    # full or partial job description text
    source: str = "the_muse"


class ScreenedJob(BaseModel):
    listing: JobListing
    overall_score: int
    top_matches: list[str]
    critical_gaps: list[str]
    one_line_summary: str
    apply_recommendation: str   # "strong" | "moderate" | "skip"


# ── heuristic term extraction (0 API calls) ───────────────────────────────────

# Broad skill vocabulary covering tech, finance, ops, marketing, etc.
_SKILLS = [
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust",
    "Ruby", "Scala", "Swift", "Kotlin", "R", "MATLAB",
    "React", "Vue", "Angular", "Next.js", "Node.js", "HTML", "CSS",
    "Django", "Flask", "FastAPI", "Spring", "Rails", ".NET",
    "SQL", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
    "Snowflake", "BigQuery", "dbt", "Spark", "Kafka", "Airflow",
    "AWS", "GCP", "Azure", "Docker", "Kubernetes", "Terraform", "CI/CD",
    "Machine Learning", "Deep Learning", "PyTorch", "TensorFlow", "NLP",
    "LLMs", "Computer Vision", "Data Science", "Analytics",
    "Tableau", "Power BI", "Looker", "Excel", "Pandas", "NumPy",
    "REST", "GraphQL", "Microservices", "DevOps", "Agile", "Scrum",
    "Product Management", "UX Research", "User Research",
    "Financial Modeling", "Valuation", "Bloomberg", "Capital IQ",
    "Equity Research", "Investment Banking", "Private Equity", "M&A",
    "Marketing", "SEO", "SEM", "Growth", "CRM", "Salesforce",
    "Operations", "Supply Chain", "Logistics", "Six Sigma",
    "Sales", "Account Management", "Business Development",
]

_TITLE_PATTERNS = [
    r"(?:senior|lead|staff|principal|junior|associate|mid[- ]level)?\s*"
    r"(?:software|data|machine learning|frontend|backend|full[- ]?stack|devops|"
    r"platform|site reliability|ml|ai|mobile|ios|android|embedded)\s*"
    r"(?:engineer|developer|architect|scientist)",
    r"(?:product|project|program|engineering|technical|data)\s+manager",
    r"data\s+(?:scientist|analyst|engineer)",
    r"(?:engineering|technical)\s+(?:manager|director|lead|vp|vice president)",
    r"(?:ux|ui|product)\s+(?:designer|researcher)",
    r"(?:financial|investment|equity|credit)\s+(?:analyst|associate)",
    r"(?:marketing|growth|brand|content)\s+(?:manager|strategist|analyst|director)",
    r"(?:operations|supply chain)\s+(?:manager|analyst|director)",
    r"(?:account|sales|business development)\s+(?:manager|executive|representative|director)",
    r"(?:management\s+)?consultant(?:\s+|$)",
    r"(?:research\s+)?analyst(?:\s+|$)",
]


def extract_terms_heuristic(resume_text: str) -> SearchTerms:
    """
    Extract job search terms from resume text with no API calls.
    Uses regex patterns and a skill vocabulary list.
    """
    text_lower = resume_text.lower()

    found_skills = [s for s in _SKILLS if s.lower() in text_lower][:8]

    titles: list[str] = []
    for pattern in _TITLE_PATTERNS:
        for m in re.finditer(pattern, text_lower):
            t = " ".join(m.group().split()).title()
            if t not in titles:
                titles.append(t)
        if len(titles) >= 4:
            break

    seniority = ""
    if any(w in text_lower for w in ["senior", "lead ", "staff ", "principal", "director", " vp ", "head of"]):
        seniority = "senior"
    elif any(w in text_lower for w in ["junior", "associate", "entry level", "entry-level"]):
        seniority = "junior"

    return SearchTerms(
        job_titles=titles[:3] if titles else ["Software Engineer"],
        key_skills=found_skills[:6],
        seniority=seniority,
    )


# ── Claude-based term extraction (1 cheap Haiku call) ────────────────────────

_EXTRACT_TOOL = {
    "name": "submit_search_terms",
    "description": "Return job search terms extracted from a resume.",
    "input_schema": {
        "type": "object",
        "required": ["job_titles", "key_skills"],
        "properties": {
            "job_titles": {
                "type": "array", "items": {"type": "string"},
                "description": "2-4 specific job titles this person would realistically apply for",
            },
            "key_skills": {
                "type": "array", "items": {"type": "string"},
                "description": "6-8 most marketable, searchable skills from the resume",
            },
            "seniority": {
                "type": "string",
                "description": "senior, mid, junior, or leave empty if unclear",
            },
            "industries": {
                "type": "array", "items": {"type": "string"},
                "description": "1-3 industries this person best fits",
            },
        },
    },
}


def extract_terms_claude(resume_text: str) -> SearchTerms:
    """
    Extract search terms with Claude Haiku — more accurate, costs ~500 tokens.
    Passes the first 3000 chars of the resume (covers most resumes entirely).
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=350,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "submit_search_terms"},
        messages=[{
            "role": "user",
            "content": (
                "Extract job search terms from this resume. "
                "Be specific and realistic about what roles this person would get interviews for.\n\n"
                f"{resume_text[:3000]}"
            ),
        }],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    return SearchTerms(**block.input)


# ── shared utilities ──────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── The Muse public API ───────────────────────────────────────────────────────
# https://www.themuse.com/api/public/jobs
# Free, no API key needed. Returns individual job postings with full descriptions.

_MUSE_API = "https://www.themuse.com/api/public/jobs"

# Map keywords (matched against title+skills) → Muse category strings.
# Order matters: more specific phrases first.
_MUSE_CATEGORY_MAP: list[tuple[str, str]] = [
    ("machine learning",    "Data & Analytics"),
    ("data scientist",      "Data & Analytics"),
    ("data engineer",       "Data & Analytics"),
    ("data analyst",        "Data & Analytics"),
    ("analytics",           "Data & Analytics"),
    ("software",            "Software Engineering"),
    ("developer",           "Software Engineering"),
    ("devops",              "Software Engineering"),
    ("site reliability",    "Software Engineering"),
    ("platform engineer",   "Software Engineering"),
    ("product manager",     "Product"),
    ("product",             "Product"),
    ("ux",                  "Design & UX"),
    ("ui designer",         "Design & UX"),
    ("designer",            "Design & UX"),
    ("investment banking",  "Finance"),
    ("private equity",      "Finance"),
    ("financial analyst",   "Finance"),
    ("financial model",     "Finance"),
    ("equity research",     "Finance"),
    ("accounting",          "Accounting"),
    ("marketing",           "Marketing & PR"),
    ("seo",                 "Marketing & PR"),
    ("content",             "Marketing & PR"),
    ("operations",          "Operations"),
    ("supply chain",        "Operations"),
    ("hr ",                 "HR & Recruiting"),
    ("recruiting",          "HR & Recruiting"),
    ("sales",               "Sales"),
    ("account manager",     "Sales"),
    ("business development","Business Development"),
    ("consultant",          "Consulting"),
    ("customer success",    "Customer Service"),
    ("support",             "Customer Service"),
    ("engineer",            "Software Engineering"),  # broad fallback
]

# Map seniority keywords → Muse level strings.
_MUSE_LEVEL_MAP: list[tuple[str, str]] = [
    ("director",        "Management"),
    ("manager",         "Management"),
    ("head of",         "Management"),
    ("vp",              "Management"),
    ("vice president",  "Management"),
    ("senior",          "Senior Level"),
    ("lead",            "Senior Level"),
    ("staff",           "Senior Level"),
    ("principal",       "Senior Level"),
    ("junior",          "Entry Level"),
    ("associate",       "Entry Level"),
    ("entry",           "Entry Level"),
]


def _infer_muse_category(terms: SearchTerms) -> Optional[str]:
    combined = " ".join(terms.job_titles + terms.key_skills).lower()
    for keyword, category in _MUSE_CATEGORY_MAP:
        if keyword in combined:
            return category
    return None


def _infer_muse_level(terms: SearchTerms) -> Optional[str]:
    combined = " ".join(terms.job_titles + [terms.seniority]).lower()
    for keyword, level in _MUSE_LEVEL_MAP:
        if keyword in combined:
            return level
    return None


def search_muse(
    terms: SearchTerms,
    location: Optional[str],
    max_results: int,
) -> list[JobListing]:
    """
    Fetch individual job postings from The Muse public API.
    Returns listings with full plain-text descriptions (HTML stripped).

    Falls back to a category-less search if the filtered first page is empty,
    so niche roles still return results.
    """
    category = _infer_muse_category(terms)
    level = _infer_muse_level(terms)

    # Normalise location: Muse uses "Flexible / Remote" for remote roles.
    muse_location: Optional[str] = None
    if location:
        loc_lower = location.lower()
        if any(w in loc_lower for w in ("remote", "anywhere", "wfh")):
            muse_location = "Flexible / Remote"
        else:
            muse_location = location

    def _fetch_page(page: int, with_category: bool) -> tuple[list[dict], int]:
        params: dict = {"page": page, "descending": "true"}
        if with_category and category:
            params["category"] = category
        if level:
            params["level"] = level
        if muse_location:
            params["location"] = muse_location
        try:
            resp = requests.get(_MUSE_API, params=params, timeout=12)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", []), data.get("page_count", 1)
        except Exception:
            return [], 0

    listings: list[JobListing] = []
    seen: set[str] = set()
    page = 0
    use_category = bool(category)

    while len(listings) < max_results:
        results, page_count = _fetch_page(page, use_category)

        # If category-filtered search returned nothing on page 0, retry broader.
        if not results and page == 0 and use_category:
            use_category = False
            results, page_count = _fetch_page(page, False)

        if not results:
            break

        for job in results:
            if len(listings) >= max_results:
                break
            url = job.get("refs", {}).get("landing_page", "")
            if not url or url in seen:
                continue
            seen.add(url)

            description = _strip_html(job.get("contents", ""))[:2000]
            listings.append(JobListing(
                index=len(listings) + 1,
                title=job.get("name", ""),
                company=job.get("company", {}).get("name", ""),
                url=url,
                description=description,
                source="the_muse",
            ))

        if page >= page_count - 1:
            break
        page += 1
        time.sleep(0.2)

    return listings


# ── Remotive public API ───────────────────────────────────────────────────────
# https://remotive.com/api/remote-jobs
# Free, no API key needed. Remote-only positions.

_REMOTIVE_API = "https://remotive.com/api/remote-jobs"

_REMOTIVE_CATEGORY_MAP: list[tuple[str, str]] = [
    ("machine learning", "data"),
    ("data scientist",   "data"),
    ("data engineer",    "data"),
    ("data analyst",     "data"),
    ("analytics",        "data"),
    ("devops",           "devops-sysadmin"),
    ("site reliability", "devops-sysadmin"),
    ("security",         "security"),
    ("qa",               "testing"),
    ("test engineer",    "testing"),
    ("product manager",  "product"),
    ("product",          "product"),
    ("design",           "design"),
    ("marketing",        "marketing"),
    ("sales",            "sales"),
    ("hr ",              "hr"),
    ("recruiting",       "hr"),
    ("finance",          "finance-legal"),
    ("legal",            "finance-legal"),
    ("customer success", "customer-support"),
    ("support",          "customer-support"),
    ("writing",          "writing"),
    ("content",          "writing"),
    ("software",         "software-dev"),
    ("developer",        "software-dev"),
    ("engineer",         "software-dev"),   # broad fallback
]


def _infer_remotive_category(terms: SearchTerms) -> Optional[str]:
    combined = " ".join(terms.job_titles + terms.key_skills).lower()
    for keyword, cat in _REMOTIVE_CATEGORY_MAP:
        if keyword in combined:
            return cat
    return None


def search_remotive(
    terms: SearchTerms,
    max_results: int,
) -> list[JobListing]:
    """
    Fetch remote job postings from Remotive's public API.
    Only returns remote positions; used as a supplement when
    the target location is remote or unspecified.
    """
    category = _infer_remotive_category(terms)
    params: dict = {"limit": max_results}
    if category:
        params["category"] = category

    try:
        resp = requests.get(_REMOTIVE_API, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    listings: list[JobListing] = []
    for job in data.get("jobs", [])[:max_results]:
        url = job.get("url", "")
        if not url:
            continue
        description = _strip_html(job.get("description", ""))[:2000]
        listings.append(JobListing(
            index=len(listings) + 1,
            title=job.get("title", ""),
            company=job.get("company_name", ""),
            url=url,
            description=description,
            source="remotive",
        ))

    return listings


# ── aggregated search entry point ─────────────────────────────────────────────

def search_jobs(
    terms: SearchTerms,
    location: Optional[str] = None,
    max_results: int = 10,
) -> list[JobListing]:
    """
    Search job boards for individual postings matching the given terms.

    Sources (in order):
      1. The Muse  — broad coverage, all job types, filterable by location.
      2. Remotive  — remote roles only; added when location is remote or blank.

    Returns listings de-duplicated by URL and re-indexed sequentially.
    LinkedIn requires login and is not supported; Workday is not supported.
    """
    listings: list[JobListing] = []
    seen_urls: set[str] = set()

    # Primary: The Muse
    for job in search_muse(terms, location, max_results):
        if job.url not in seen_urls:
            seen_urls.add(job.url)
            listings.append(job)

    # Secondary: Remotive for remote/unspecified locations
    if len(listings) < max_results:
        loc_lower = (location or "").lower()
        is_remote = not location or any(
            w in loc_lower for w in ("remote", "anywhere", "wfh")
        )
        if is_remote:
            remaining = max_results - len(listings)
            for job in search_remotive(terms, remaining):
                if job.url not in seen_urls and len(listings) < max_results:
                    seen_urls.add(job.url)
                    listings.append(job)

    # Re-index sequentially so batch screening job_index values are consistent
    for i, job in enumerate(listings):
        job.index = i + 1

    return listings


# ── batch screening (1 Claude call for all jobs) ─────────────────────────────

_BATCH_SCREEN_TOOL = {
    "name": "submit_batch_screening",
    "description": "Submit screening scores for all job postings.",
    "input_schema": {
        "type": "object",
        "required": ["rankings"],
        "properties": {
            "rankings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "job_index", "overall_score", "top_matches",
                        "critical_gaps", "one_line_summary", "apply_recommendation",
                    ],
                    "properties": {
                        "job_index": {"type": "integer"},
                        "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "top_matches": {
                            "type": "array", "items": {"type": "string"},
                            "maxItems": 3,
                            "description": "2-3 specific skills/experiences that match",
                        },
                        "critical_gaps": {
                            "type": "array", "items": {"type": "string"},
                            "maxItems": 2,
                            "description": "1-2 most important missing qualifications, or empty if strong match",
                        },
                        "one_line_summary": {
                            "type": "string",
                            "description": "One sentence explaining the score",
                        },
                        "apply_recommendation": {
                            "type": "string",
                            "enum": ["strong", "moderate", "skip"],
                        },
                    },
                },
            }
        },
    },
}


def screen_jobs_batch(resume_text: str, jobs: list[JobListing]) -> list[ScreenedJob]:
    """
    Score and rank all jobs against the resume in a single API call.

    Token cost scales at roughly 200 tokens per job (truncated description),
    so 10 jobs ≈ 3,500 input + 1,500 output tokens total (~$0.03 at Sonnet pricing).
    Uses Haiku to halve that cost further.

    The Muse/Remotive descriptions are fuller than web-search snippets were,
    so screening quality is higher at the same token budget per job.
    """
    if not jobs:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    jobs_block = ""
    for job in jobs:
        desc = job.description[:700].strip()
        jobs_block += (
            f"\n[JOB {job.index}]\n"
            f"Title: {job.title}\n"
            f"Company: {job.company}\n"
            f"Description:\n{desc}\n"
        )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150 * len(jobs) + 200,
        system=[
            {
                "type": "text",
                "text": (
                    "You are a career counselor screening job postings for a candidate. "
                    "Score honestly — 70+ means genuinely competitive, not just relevant. "
                    "Base your scores on the resume evidence, not wishful thinking."
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_BATCH_SCREEN_TOOL],
        tool_choice={"type": "tool", "name": "submit_batch_screening"},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"<resume>\n{resume_text}\n</resume>",
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": (
                        f"Screen these {len(jobs)} job postings against the resume above. "
                        "For each job provide an overall_score, top_matches, critical_gaps, "
                        "a one_line_summary, and an apply_recommendation.\n"
                        + jobs_block
                    ),
                },
            ],
        }]
    )

    block = next(b for b in response.content if b.type == "tool_use")
    by_index = {r["job_index"]: r for r in block.input.get("rankings", [])}

    screened = []
    for job in jobs:
        r = by_index.get(job.index, {})
        screened.append(ScreenedJob(
            listing=job,
            overall_score=r.get("overall_score", 0),
            top_matches=r.get("top_matches", []),
            critical_gaps=r.get("critical_gaps", []),
            one_line_summary=r.get("one_line_summary", ""),
            apply_recommendation=r.get("apply_recommendation", "skip"),
        ))

    return sorted(screened, key=lambda x: x.overall_score, reverse=True)
