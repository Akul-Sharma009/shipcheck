"""Per-file evidence: Nemotron Nano summaries in parallel, plus deterministic grep hits with line numbers."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from shipcheck import config
from shipcheck.llm import LLMError, call_json
from shipcheck.repo import PER_FILE_CHARS, USAGE_PATTERN
from shipcheck.schemas import FileEvidence

log = logging.getLogger(__name__)

MAX_CHARS_PER_FILE = PER_FILE_CHARS  # ~3K tokens
MAX_HITS = 150
MAX_WORKERS = 8

PROMPT = """Summarize this file for a hackathon judge.
- purpose: one sentence.
- models_used: AI model IDs copied exactly as they appear in the file; [] if none.
- apis_called: external services this code itself calls at runtime, named as they appear in the file (base URL host, client library or SDK name); [] if the file makes no external calls. Dependency lists, configs and docs call nothing: use [].
- notable: up to 3 short facts a judge would care about.
Only report what is literally in this file. Empty lists are normal.

Path: {path}
Content:
{content}"""

_WORD = re.compile(r"[a-z0-9]{4,}")
_GENERIC = {"api", "apis", "service", "client", "cloud", "rest", "http", "https", "endpoint", "server", "model"}


def _grounded(claim: str, content_lower: str) -> bool:
    """True if the claim's brand word appears in the file ('Nebius Token Factory' -> 'nebius', 'Tavily Search' -> 'tavily')."""
    words = [w for w in _WORD.findall(claim.lower()) if w not in _GENERIC]
    return bool(words) and words[0] in content_lower


def ground(ev: FileEvidence, content: str) -> FileEvidence:
    """Drop model IDs and services the file never mentions: the model must not invent evidence."""
    low = content.lower()
    ev.models_used = [m for m in ev.models_used if m.lower() in low]
    ev.apis_called = [a for a in ev.apis_called if _grounded(a, low)]
    return ev


def summarize_file(path: str, content: str, stats: Optional[Dict[str, Any]] = None) -> Optional[FileEvidence]:
    snippet = content[:MAX_CHARS_PER_FILE] + ("\n...[truncated]" if len(content) > MAX_CHARS_PER_FILE else "")
    ev = call_json(config.MODEL_NANO, PROMPT.format(path=path, content=snippet), FileEvidence,
                   config.MAX_TOKENS_NANO, thinking=False if config.NANO_DISABLE_THINKING else None, stats=stats)
    if ev:
        ev.path = path  # trust our path, not the model's
        ground(ev, content)
    return ev


def gather_evidence(files: Dict[str, str], stats: Optional[Dict[str, Any]] = None) -> List[FileEvidence]:
    """One Nano call per file, in parallel. Files whose output never validates are skipped.
    Auth/credit errors abort the run (every other call would fail the same way)."""

    def one(item):
        path, content = item
        try:
            return summarize_file(path, content, stats)
        except LLMError as e:
            if e.status_code in (401, 402, 403):
                raise
            log.warning("evidence for %s failed: %s", path, e)
            return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(one, files.items()))
    return [r for r in results if r]


def grep_hits(files: Dict[str, str], readme: str = "", readme_path: Optional[str] = None) -> List[str]:
    """Lines that mention models, platforms or API clients, as 'path:line: text'. Deterministic and citable."""
    hits = []
    sources = ([(readme_path, readme)] if readme and readme_path else []) + list(files.items())
    for path, content in sources:
        for n, line in enumerate(content.splitlines(), 1):
            if USAGE_PATTERN.search(line):
                hits.append(f"{path}:{n}: {line.strip()[:160]}")
                if len(hits) >= MAX_HITS:
                    return hits
    return hits
