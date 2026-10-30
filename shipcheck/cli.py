"""Command-line run of the pipeline (for testing and evaluation).

    python -m shipcheck.cli <hackathon_url> <repo_url>
"""
import sys
import time
from typing import Any, Dict

from shipcheck.repo import deterministic_checks, ingest
from shipcheck.rules import get_rules


def main(hackathon_url: str, repo_url: str) -> None:
    stats: Dict[str, Any] = {}
    t = time.time()
    rules, source = get_rules(hackathon_url, stats=stats)
    print(f"RULES  ({time.time() - t:.0f}s, {source})")
    if not rules:
        sys.exit("FAILED to extract rules")
    print(f"  {rules.hackathon_name} | submission period {rules.submission_start} -> {rules.deadline}")
    for r in rules.requirements:
        print(f"  {r.id:4} [{r.category:11}] {'repo' if r.checkable_from_repo else '    '}  {r.text[:100]}")
    print("  criteria:", "; ".join(c.name for c in rules.criteria))

    t = time.time()
    facts, readme, files = ingest(repo_url)
    print(f"\nREPO  ({time.time() - t:.0f}s) {facts.full_name} @ {facts.head_sha[:7]}")
    print(f"  license={facts.license_spdx} readme={facts.readme_path} files: {facts.files_considered} of "
          f"{facts.files_in_tree} selected")
    print("\nDETERMINISTIC CHECKS")
    for c in deterministic_checks(facts, rules):
        print(f"  {c.id} {c.status.upper():8} {c.name}  | {'; '.join(c.evidence)}"
              + (f"\n      fix: {c.fix}" if c.fix else ""))
    print("\nLLM usage:", stats)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
