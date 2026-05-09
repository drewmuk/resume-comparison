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

# Ordered list of CSS selectors to try for common job boards.
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
    # Workday
    "[data-automation-id='jobPostingDescription']",
    # Generic
    "[class*='job-description']",
    "[class*='jobDescription']",
    "[id*='job-description']",
    "[class*='job_description']",
    "[class*='posting-description']",
    "article",
    "main",
]


def scrape_job_posting(url: str) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(
            f"HTTP {e.response.status_code} when fetching {url}. "
            "The job board may block automated access. "
            "Use --job-file to provide the description as a text file instead."
        ) from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Could not reach {url}: {e}. "
            "Use --job-file to provide the description as a text file instead."
        ) from e

    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    for selector in _JOB_SELECTORS:
        element = soup.select_one(selector)
        if element:
            text = element.get_text(separator="\n", strip=True)
            if len(text) > 300:
                return _clean_text(text)

    # Fallback: take all body text and truncate to a reasonable size.
    body = soup.find("body")
    text = body.get_text(separator="\n", strip=True) if body else soup.get_text()
    return _clean_text(text)[:12_000]


def _clean_text(text: str) -> str:
    # Collapse 3+ blank lines into 2, strip trailing whitespace per line.
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
