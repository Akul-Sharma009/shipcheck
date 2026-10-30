"""Command-line run of the pipeline (for testing, evaluation and the GitHub Action).

    python -m shipcheck.cli <hackathon_url> <repo_url> [--json out.json] [--ref SHA]
                            [--markdown out.md] [--fail-on {fail,unclear,never}]

--fail-on exits 1 when a requirement fails (fail) or fails/is unclear (unclear). Default: never.
Rules bundled in examples/rules need no Tavily key; other hackathons do.
"""
import argparse
import os
import sys

from shipcheck import guard
from shipcheck.pipeline import run
from shipcheck.render import counts, to_markdown

ICON = {"pass": "PASS", "fail": "FAIL", "unclear": "??  ", "not_checkable": "--  "}


def _parse(argv):
    p = argparse.ArgumentParser(prog="python -m shipcheck.cli", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("hackathon_url")
    p.add_argument("repo_url")
    p.add_argument("--json", metavar="OUT.JSON", help="save the full report as JSON")
    p.add_argument("--ref", metavar="SHA", help="pin a commit, branch or tag of the repo")
    p.add_argument("--markdown", metavar="OUT.MD", help="save the report as Markdown")
    p.add_argument("--fail-on", choices=["fail", "unclear", "never"], default="never")
    return p.parse_args(argv)


def main(argv) -> None:
    args = _parse(argv)
    # Use rules bundled in the repo when known, so the run doesn't need Tavily.
    cached = guard.get_rules(guard.rules_key(args.hackathon_url))
    rules, rules_source = cached if cached else (None, "")
    report = run(args.hackathon_url, args.repo_url, rules=rules, rules_source=rules_source,
                 ref=args.ref, progress=lambda m: print("·", m))
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
    n = counts(report)
    print(f"\n{n['pass']} pass · {n['fail']} fail · {n['unclear']} unclear · "
          f"{n['not_checkable']} to confirm yourself   ({report.seconds}s, {len(report.evidence)} files summarized)")
    for model, s in report.usage.items():
        print(f"  {model}: {s['calls']} calls, {s['prompt_tokens']} in / {s['completion_tokens']} out, "
              f"{s['seconds']:.0f}s summed")
    if args.json:
        open(args.json, "w").write(report.model_dump_json(indent=2))
        print("saved", args.json)
    if args.markdown:
        open(args.markdown, "w").write(to_markdown(report))
        print("saved", args.markdown)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"pass={n['pass']}\nfail={n['fail']}\nunclear={n['unclear']}\n")
    print(f"pass={n['pass']} fail={n['fail']} unclear={n['unclear']}")
    if (args.fail_on == "fail" and n["fail"]) or (args.fail_on == "unclear" and (n["fail"] or n["unclear"])):
        print(f"--fail-on {args.fail_on}: exiting 1")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
