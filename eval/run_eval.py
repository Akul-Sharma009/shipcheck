"""Head-to-head eval (GUARDRAILS.md): ShipCheck vs a keyword baseline vs one chatbot-style call.

All three see the same pinned commits and the same frozen requirement list; ground truth comes from an
independent reviewer who never saw ShipCheck. Usage:

    python -m eval.run_eval eval/labels.json eval/repos.txt
"""
import json
import sys
from typing import Dict, List

from shipcheck import config, guard
from shipcheck.baseline import keyword_verdict
from shipcheck.llm import call_json
from shipcheck.pipeline import run
from shipcheck.repo import ingest
from shipcheck.schemas import Rules, VerdictList

HACKATHON = "https://nebiusglobalaihackathon.devpost.com/"
MAX_PASTE = 60_000

ONE_CALL = """You are judging a hackathon submission. Here are the hackathon's requirements and the project's
GitHub repo (file list, README and source files). For each requirement answer pass, fail or unclear.

REQUIREMENTS:
{reqs}

REPO: {name} (public: {public}; GitHub-detected license: {license})
FILES:
{tree}

README:
{readme}

SOURCE FILES:
{files}

Return one verdict per requirement id: {ids}"""


def one_call(rules: Rules, ids: List[str], facts, readme: str, files: Dict[str, str],
             with_license: bool = True) -> Dict[str, str]:
    """The incumbent: paste everything into one model call (same model as ShipCheck, no pipeline).
    with_license=False hides GitHub's detected-license field, as a pasted repo realistically would."""
    reqs = [r for r in rules.requirements if r.id in ids]
    body, used = [], 0
    for p, c in files.items():
        chunk = f"--- {p}\n{c}\n"
        if used + len(chunk) > MAX_PASTE:
            break
        body.append(chunk)
        used += len(chunk)
    out = call_json(config.MODEL_SUPER, ONE_CALL.format(
        reqs="\n".join(f"{r.id}: {r.text}" for r in reqs), name=facts.full_name, public=facts.is_public,
        license=facts.license_spdx if with_license else "(not given)", tree="\n".join(files), readme=readme[:8000], files="".join(body),
        ids=", ".join(ids)), VerdictList, config.MAX_TOKENS_SUPER)
    got = {v.requirement_id: v.status for v in (out.verdicts if out else [])}
    return {i: got.get(i, "unclear") for i in ids}


def metrics(pairs: List[tuple]) -> Dict[str, float]:
    """pairs of (prediction, label). Labels are pass/fail; 'unclear' predictions count as wrong."""
    n = len(pairs)
    fails = [p for p, l in pairs if l == "fail"]
    f1s = []
    for cls in ("pass", "fail"):
        tp = sum(1 for p, l in pairs if p == cls and l == cls)
        pred = sum(1 for p, _ in pairs if p == cls)
        act = sum(1 for _, l in pairs if l == cls)
        prec = tp / pred if pred else 0.0
        rec = tp / act if act else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return {"n": n, "n_fail": len(fails),
            "accuracy": sum(1 for p, l in pairs if p == l) / n,
            "macro_f1": sum(f1s) / 2,
            "false_pass_rate": (sum(1 for p in fails if p == "pass") / len(fails)) if fails else 0.0,
            "unclear_rate": sum(1 for p, _ in pairs if p == "unclear") / n}


def main(labels_path: str, repos_path: str) -> None:
    labels = json.load(open(labels_path))
    rules, _ = guard.get_rules(guard.rules_key(HACKATHON))
    preds: Dict[str, Dict[str, Dict[str, str]]] = {"ShipCheck": {}, "Keyword baseline": {}, "One model call": {},
                                                  "One model call (no license field)": {}}
    for line in open(repos_path):
        if not line.strip():
            continue
        name, sha = line.split()
        ids = sorted(labels[name], key=lambda x: int(x[1:]))
        print(f"· {name} @ {sha[:7]}", flush=True)
        facts, readme, files = ingest(name, sha)
        report = run(HACKATHON, name, rules=rules, rules_source="frozen", ref=sha)
        by_id = {v.requirement_id: v.status for v in report.verdicts}
        preds["ShipCheck"][name] = {i: by_id.get(i, "unclear") for i in ids}
        reqs = {r.id: r for r in rules.requirements}
        preds["Keyword baseline"][name] = {i: keyword_verdict(reqs[i], facts, readme, files) for i in ids}
        preds["One model call"][name] = one_call(rules, ids, facts, readme, files)
        preds["One model call (no license field)"][name] = one_call(rules, ids, facts, readme, files, False)

    json.dump(preds, open("eval/predictions.json", "w"), indent=1)
    rows = []
    for method, by_repo in preds.items():
        pairs = [(by_repo[r][i], labels[r][i]["label"]) for r in by_repo for i in by_repo[r]]
        m = metrics(pairs)
        rows.append((method, m))
        print(f"{method:18} acc {m['accuracy']:.0%}  macroF1 {m['macro_f1']:.2f}  false-pass "
              f"{m['false_pass_rate']:.0%} (of {m['n_fail']} true fails)  unclear {m['unclear_rate']:.0%}  n={m['n']}")
    print("\nDisagreements with ground truth:")
    for method, by_repo in preds.items():
        for r in by_repo:
            for i, p in by_repo[r].items():
                if p != labels[r][i]["label"]:
                    print(f"  {method:18} {r:48} {i}: predicted {p}, truth {labels[r][i]['label']}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
