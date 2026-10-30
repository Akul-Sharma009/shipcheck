"""Cost guardrails: result + rules cache, per-day cap on uncached runs, cached example reports.

All state is on local disk. Streamlit Cloud wipes it on reboot, so the daily cap is best effort;
SHIPCHECK_LIVE=false is the reliable off switch.
"""
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from shipcheck import config
from shipcheck.rules import page_urls
from shipcheck.schemas import Report, Rules

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"
EXAMPLES_DIR = ROOT / "examples"
_lock = threading.Lock()


def _key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text()
    except OSError:
        return None


def _write(path: Path, text: str) -> None:
    try:
        CACHE_DIR.mkdir(exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text)
        tmp.replace(path)
    except OSError:
        pass  # a cache that can't write is just a slower app


# ---------- rules cache (one extraction per hackathon, so reruns see the same checklist) ----------
def rules_key(hackathon_url: str, pasted: str = "") -> str:
    return _key("rules", page_urls(hackathon_url)[0], hashlib.sha256(pasted.strip().encode()).hexdigest())


def get_rules(key: str) -> Optional[Tuple[Rules, str]]:
    """Runtime cache first, then rules bundled in the repo (so a known hackathon never depends on its page)."""
    raw = _read(CACHE_DIR / f"rules_{key}.json") or _read(EXAMPLES_DIR / "rules" / f"rules_{key}.json")
    if not raw:
        return None
    d = json.loads(raw)
    return Rules.model_validate(d["rules"]), d["source"]


def put_rules(key: str, rules: Rules, source: str) -> None:
    _write(CACHE_DIR / f"rules_{key}.json", json.dumps({"rules": rules.model_dump(), "source": source}))


# ---------- report cache: (repo commit SHA, hackathon URL, pasted rules) ----------
def report_key(head_sha: str, rkey: str, submission: str = "") -> str:
    """submission = video URL + Devpost text; a different write-up is a different check."""
    return _key("report", head_sha, rkey, hashlib.sha256(submission.strip().encode()).hexdigest())


def get_report(key: str) -> Optional[Report]:
    raw = _read(CACHE_DIR / f"report_{key}.json")
    return Report.model_validate_json(raw) if raw else None


def put_report(key: str, report: Report) -> None:
    _write(CACHE_DIR / f"report_{key}.json", report.model_dump_json())


# ---------- daily cap on uncached runs ----------
def _usage_path() -> Path:
    return CACHE_DIR / f"usage_{datetime.now(timezone.utc):%Y-%m-%d}.json"


def runs_today() -> int:
    raw = _read(_usage_path())
    return json.loads(raw).get("uncached_runs", 0) if raw else 0


def reserve_run() -> bool:
    """Count an uncached run before it starts (so concurrent sessions can't overshoot). False if the cap is hit."""
    with _lock:
        n = runs_today()
        if n >= config.MAX_UNCACHED_RUNS_PER_DAY:
            return False
        _write(_usage_path(), json.dumps({"uncached_runs": n + 1}))
        return True


# ---------- examples (committed; the demo works with no API calls at all) ----------
def examples() -> List[Tuple[str, Report]]:
    out = []
    for p in sorted(EXAMPLES_DIR.glob("*.json")):
        try:
            out.append((p.stem, Report.model_validate_json(p.read_text())))
        except (OSError, ValueError):
            continue
    return out
