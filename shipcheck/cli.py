"""Command-line run of the pipeline (for testing and evaluation).

    python -m shipcheck.cli <hackathon_url> <repo_url> [--json out.json]
"""
import sys

from shipcheck.pipeline import run

ICON = {"pass": "PASS", "fail": "FAIL", "unclear": "??  ", "not_checkable": "--  "}


def main(argv) -> None:
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--json"):
        sys.exit(__doc__)
    report = run(argv[0], argv[1], progress=lambda m: print("·", m))
    reqs = {r.id: r for r in report.rules.requirements}
    print(f"\n{report.rules.hackathon_name}  ×  {report.facts.full_name} @ {report.facts.head_sha[:7]}")
    print("\nDETERMINISTIC CHECKS")
    for c in report.checks:
        print(f"  {ICON[c.status]} {c.id} {c.name}")
    print("\nREQUIREMENTS")
    for v in report.verdicts:
        print(f"  {ICON[v.status]} {v.requirement_id:4} {reqs[v.requirement_id].text[:90]}")
        if v.status in ("pass", "fail", "unclear"):
            print(f"         evidence: {' | '.join(v.evidence)[:220]}")
        if v.fix:
            print(f"         fix: {v.fix}")
    counts = {s: sum(v.status == s for v in report.verdicts) for s in ICON}
    print(f"\n{counts['pass']} pass · {counts['fail']} fail · {counts['unclear']} unclear · "
          f"{counts['not_checkable']} to confirm yourself   ({report.seconds}s, {len(report.evidence)} files summarized)")
    for model, s in report.usage.items():
        print(f"  {model}: {s['calls']} calls, {s['prompt_tokens']} in / {s['completion_tokens']} out, "
              f"{s['seconds']:.0f}s summed")
    if len(argv) == 4:
        open(argv[3], "w").write(report.model_dump_json(indent=2))
        print("saved", argv[3])


if __name__ == "__main__":
    main(sys.argv[1:])
