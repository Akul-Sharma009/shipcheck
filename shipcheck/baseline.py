"""The dumb baseline from GUARDRAILS.md: keyword and file rules, no AI.

Used twice: in eval/ (ShipCheck must beat it), and in the report, to point out where a keyword check would
have given a false all-clear.
"""
import re
from typing import Dict

from shipcheck.schemas import RepoFacts, Requirement

SETUP_WORDS = re.compile(r"install|setup|set up|getting started|\brun\b", re.I)
GENERIC = {"must", "should", "the", "your", "you", "repository", "readme", "include", "including", "provide",
           "project", "projects", "submission", "submissions", "url", "tools", "services", "tool", "service",
           "other", "open", "source", "any", "all", "with", "public", "code", "github", "gitlab", "bitbucket",
           "apache", "mit", "mpl", "file", "license", "highlight", "video", "where", "how", "and", "for", "either"}


def _brands(text: str) -> set:
    """Proper-noun-looking words in a requirement (e.g. Nebius, Token, Factory, NVIDIA, Nemotron)."""
    words = re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", text)
    return {w.lower() for w in words[1:] if w.lower() not in GENERIC}  # skip the sentence's first word


def keyword_verdict(req: Requirement, facts: RepoFacts, readme: str, files: Dict[str, str]) -> str:
    """pass / fail / unclear by keyword and file rules only."""
    t = req.text.lower()
    if req.category == "license" or "license" in t:
        return "pass" if facts.license_file_present else "fail"
    if req.category == "readme" or "readme" in t:
        if not readme:
            return "fail"
        if re.search(r"setup|install|run", t):
            return "pass" if SETUP_WORDS.search(readme) else "fail"
        brands = _brands(req.text)
        if brands:
            hits = sum(1 for b in brands if b in readme.lower())
            return "pass" if hits * 2 >= len(brands) else "fail"
        return "unclear"
    if "public" in t:
        return "pass" if facts.is_public else "fail"
    brands = _brands(req.text)
    if brands:
        corpus = (readme + "\n" + "\n".join(files.values())).lower()
        return "pass" if any(b in corpus for b in brands) else "fail"
    return "unclear"
