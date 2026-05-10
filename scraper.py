"""
Job posting scraper with two-tier strategy:
  1. requests + BeautifulSoup  (fast, no browser needed)
  2. Playwright headless Chromium  (fallback for JS-rendered pages)

Workday is explicitly unsupported — those boards require authentication
and produce inconsistent results even with a browser.
"""

import re

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Ordered by specificity — tried in sequence, first match > 300 chars wins.
_JOB_SELECTORS = [
    # LinkedIn
    ".description__text",
    ".jobs-description__content",
    # Indeed
    "#jobDescriptionText",
    # Greenhouse
    "#content",
    # Lever
    ".posting-categories",
    ".section-wrapper",
    # iCIMS
    "[class*='iCIMS_JobContent']",
    # SmartRecruiters
    ".job-description",
    # Generic patterns
    "[class*='job-description']",
    "[class*='jobDescription']",
    "[id*='job-description']",
    "[class*='job_description']",
    "[class*='posting-description']",
    "[class*='job-detail']",
    "article",
    "main",
]

# Minimum characters to consider a scrape successful.
_MIN_LENGTH = 300


def scrape_job_posting(url: str) -> str:
    """Scrape a job posting URL. Tries requests first, falls back to Playwright."""
    if _is_workday(url):
        raise RuntimeError(
            "Workday job boards are not supported due to their authentication requirements. "
            "Copy the job description text and paste it into the 'Job text' field instead."
        )

    # --- Tier 1: requests ---
    requests_error: str | None = None
    try:
        text = _scrape_with_requests(url)
        if len(text) >= _MIN_LENGTH:
            return text
        requests_error = f"only extracted {len(text)} characters (page likely JS-rendered)"
    except RuntimeError as e:
        requests_error = str(e)

    # --- Tier 2: Playwright ---
    try:
        return _scrape_with_playwright(url)
    except ImportError:
        raise RuntimeError(
            f"requests scraping failed ({requests_error}) and Playwright is not installed.\n"
            "Install it with:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
            "Or paste the job description text directly."
        )
    except Exception as pw_err:
        raise RuntimeError(
            f"Both scraping strategies failed.\n"
            f"  requests:   {requests_error}\n"
            f"  Playwright: {pw_err}\n"
            "Please paste the job description text directly."
        )


def _is_workday(url: str) -> bool:
    return "myworkdayjobs.com" in url or (
        "workday.com" in url and "job" in url.lower()
    )


def _scrape_with_requests(url: str) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(str(e)) from e

    return _extract_text(resp.text)


def _scrape_with_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeout
    except ImportError:
        raise ImportError("playwright not installed")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=_HEADERS["User-Agent"],
            locale="en-US",
        )
        page = context.new_page()

        try:
            # networkidle is most reliable but can time out on heavy SPAs.
            page.goto(url, wait_until="networkidle", timeout=30_000)
        except PWTimeout:
            # Fall back to domcontentloaded + manual delay.
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(4_000)
            except PWTimeout as e:
                browser.close()
                raise RuntimeError(f"Page load timed out: {e}") from e

        # Give any lazy-loaded content a moment to settle.
        page.wait_for_timeout(1_500)
        html = page.content()
        browser.close()

    text = _extract_text(html)
    if len(text) < _MIN_LENGTH:
        raise RuntimeError(f"Playwright rendered page but only extracted {len(text)} characters")
    return text


def _extract_text(html: str) -> str:
    """Parse HTML and return the best-matching job description text."""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    for selector in _JOB_SELECTORS:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator="\n", strip=True)
            if len(text) > _MIN_LENGTH:
                return _clean_text(text)

    body = soup.find("body")
    raw = body.get_text(separator="\n", strip=True) if body else soup.get_text()
    return _clean_text(raw)[:12_000]


def _clean_text(text: str) -> str:
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
