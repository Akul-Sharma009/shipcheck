"""One ShipCheck run: rules + repo -> deterministic checks -> Nano evidence -> Super verdicts -> Report."""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from shipcheck.evidence import gather_evidence, grep_hits
from shipcheck.judge import judge, mark_required
from shipcheck.repo import deterministic_checks, ingest
from shipcheck.rules import get_rules
from shipcheck.schemas import Report, Rules
from shipcheck.submission import apply_description, apply_video, judge_description, video_checks


class PipelineError(Exception):
    """A step failed in a way the user can act on (bad URL, rules not extractable)."""


def run(hackathon_url: str, repo_url: str, pasted_rules: str = "", rules: Optional[Rules] = None,
        rules_source: str = "", description: str = "", video_url: str = "",
        progress: Optional[Callable[[str], None]] = None) -> Report:
    """Pass `rules` to reuse a cached extraction. Raises PipelineError, RepoError or LLMError."""
    say = progress or (lambda msg: None)
    stats: Dict[str, Any] = {}
    t0 = time.time()

    if rules is None:
        say("Reading the hackathon rules (Tavily Extract → Nemotron Super)…")
        rules, rules_source = get_rules(hackathon_url, pasted_rules, stats)
        if rules is None:
            raise PipelineError(f"Couldn't extract the rules: {rules_source}. Paste the rules text instead.")

    say("Reading the repo (GitHub API)…")
    facts, readme, files = ingest(repo_url)
    checks = deterministic_checks(facts, rules)
    mark_required(rules, checks)

    say(f"Summarizing {len(files)} files in parallel (Nemotron Nano)…")
    evidence = gather_evidence(files, stats)
    hits = grep_hits(files, readme, facts.readme_path)

    say("Judging each requirement (Nemotron Super)" + (" and your Devpost write-up" if description.strip() else "")
        + "…")
    with ThreadPoolExecutor(max_workers=2) as ex:
        desc = ex.submit(judge_description, rules, description, stats)
        verdicts = judge(rules, facts, checks, readme, evidence, hits, stats)
        verdicts = apply_description(verdicts, desc.result())

    if video_url.strip():
        say("Checking the demo video on YouTube…")
        vchecks = video_checks(video_url.strip(), rules)
        checks += vchecks
        verdicts = apply_video(rules, verdicts, vchecks)

    return Report(hackathon_url=hackathon_url, repo_url=repo_url, rules=rules, rules_source=rules_source,
                  facts=facts, checks=checks, verdicts=verdicts, evidence=evidence, usage=stats,
                  readme=readme[:8000], video_url=video_url.strip(), description_checked=bool(description.strip()),
                  seconds=round(time.time() - t0, 1), created_at=datetime.now(timezone.utc).isoformat())
