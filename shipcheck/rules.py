"""Hackathon rules: Tavily Extract (overview + rules pages) -> clean -> Nemotron Super -> Rules."""
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from tavily import TavilyClient

from shipcheck import config
from shipcheck.llm import call_json
from shipcheck.schemas import Rules

MAX_RULES_CHARS = 60_000

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPTY_HEADING = re.compile(r"^#+\s*$")


def page_urls(url: str) -> List[str]:
    """For a Devpost hackathon, read both the overview and the rules page; otherwise just the given URL."""
    p = urlparse(url if "://" in url else "https://" + url)
    if p.netloc.endswith(".devpost.com") and p.netloc != "devpost.com":
        base = f"https://{p.netloc}"
        return [base + "/", base + "/rules"]
    return [p.geturl()]


def clean(text: str) -> str:
    """Drop site navigation, images, link targets, empty headings and repeated lines."""
    text = _LINK.sub(r"\1", _IMAGE.sub("", text))
    h1 = re.search(r"^# ", text, re.M)  # Devpost pages: the nav block sits above the page's H1
    if h1:
        text = text[h1.start():]
    seen, out = set(), []
    for line in text.splitlines():
        line = line.strip()
        if not line or _EMPTY_HEADING.match(line):
            if out and out[-1]:
                out.append("")
            continue
        if line in seen and len(line) < 200:
            continue
        seen.add(line)
        out.append(line)
    return "\n".join(out).strip()


def fetch_rules_text(url: str) -> Tuple[str, List[str]]:
    """Returns (cleaned text, list of URLs that failed). Raises on Tavily errors."""
    urls = page_urls(url)
    res = TavilyClient(api_key=config.TAVILY_API_KEY).extract(urls=urls)
    by_url = {r.get("url"): r.get("raw_content") or "" for r in res.get("results", [])}
    parts = [f"=== PAGE: {u} ===\n{clean(by_url[u])}" for u in urls if by_url.get(u)]
    failed = [u for u in urls if not by_url.get(u)]
    return "\n\n".join(parts)[:MAX_RULES_CHARS], failed


PROMPT = """You are given the text of a hackathon's overview and rules pages.
Extract every concrete submission requirement and every judging criterion.

- Only include requirements actually stated in the text. Merge duplicates (overview and rules often repeat).
- Requirements are things a submission must have or do (required platform/model usage, repo, license, README, video, description, feedback, deadlines). Skip general legal terms (eligibility by country, IP assignment, publicity) unless they are something an entrant must produce.
- Mark checkable_from_repo true if it can be verified by reading a public GitHub repo: its code (e.g. which platform, API or model it calls), README, license, visibility, or commit history. Required platform/model usage IS checkable from code. Video, demo URL, Devpost form fields, feedback and legal authorization are not.
- submission_start and deadline: the submission period start and end as ISO 8601 with timezone offset (e.g. 2026-10-30T10:00:00-07:00), or null if not stated.

TEXT:
{text}"""


def extract_rules(text: str, stats: Optional[Dict[str, Any]] = None) -> Optional[Rules]:
    return call_json(config.MODEL_SUPER, PROMPT.format(text=text), Rules, config.MAX_TOKENS_SUPER,
                     thinking=None if config.RULES_THINKING else False, stats=stats)


def get_rules(url: str, pasted_text: str = "", stats: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Rules], str]:
    """Pasted rules text wins over extraction. Returns (rules or None, source description)."""
    if pasted_text.strip():
        return extract_rules(clean(pasted_text)[:MAX_RULES_CHARS], stats), "pasted text"
    text, failed = fetch_rules_text(url)
    if len(text) < 1000:
        return None, f"extraction returned too little text (failed: {failed}); paste the rules instead"
    return extract_rules(text, stats), "Tavily Extract: " + ", ".join(page_urls(url))


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://nebiusglobalaihackathon.devpost.com/"
    stats: Dict[str, Any] = {}
    rules, source = get_rules(url, stats=stats)
    print("source:", source)
    if not rules:
        sys.exit("FAILED to extract rules")
    print(f"\n{rules.hackathon_name}  |  {rules.submission_start} -> {rules.deadline}")
    print("tracks:", ", ".join(rules.tracks))
    print(f"\nREQUIREMENTS ({len(rules.requirements)})")
    for r in rules.requirements:
        print(f"  {r.id:4} [{r.category:11}] {'repo' if r.checkable_from_repo else '    '}  {r.text}")
    print(f"\nCRITERIA ({len(rules.criteria)})")
    for c in rules.criteria:
        print(f"  - {c.name}: {c.description[:110]}")
    print("\nusage:", stats)
