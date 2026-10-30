"""Requirement verdicts (Nemotron Super), with deterministic overrides and an evidence check against false passes."""
import json
import re
from typing import Any, Dict, List, Optional, Set

from shipcheck import config
from shipcheck.llm import call_json
from shipcheck.schemas import Check, FileEvidence, RepoFacts, Rules, Verdict, VerdictList

MAX_README_CHARS = 8_000

PROMPT = """You are checking a hackathon submission's code repo against the hackathon's requirements.

Decide for EACH requirement below: pass, fail, or unclear.
- pass: the evidence clearly shows the requirement is met. Cite at least one file path (exactly as listed) or check id (D1-D5).
- fail: the evidence shows it is not met, or something required is clearly absent.
- unclear: the evidence is insufficient either way.
- For required platform/model usage, a pass needs code or config evidence (a path:line from the code lines below, or a file whose per-file evidence lists it). A README claim alone is "unclear".
- Deterministic checks (D1-D5) are facts from the repo host's API and override your judgment.
- evidence: short items citing file paths, path:line, or check ids. No invented paths.
- fix: for fail/unclear, ONE concrete action the entrant can do in under 30 minutes (name the file and what to add). null for pass.

REQUIREMENTS:
{requirements}

DETERMINISTIC CHECKS:
{checks}

REPO FACTS:
{facts}

README ({readme_path}):
{readme}

LINES MENTIONING MODELS / PLATFORMS / API CLIENTS (path:line: text):
{hits}

PER-FILE EVIDENCE:
{evidence}

Return one verdict per requirement id: {ids}"""


def links(req_text: str, category: str) -> List[str]:
    """Deterministic checks that bear on a requirement."""
    t = req_text.lower()
    out = []
    if "public" in t:
        out.append("D1")
    if category == "license" or "license" in t:
        out.append("D2")
    if category == "readme" or "readme" in t:
        out.append("D3")
        if re.search(r"setup|install|run", t):
            out.append("D4")
    return out


def mark_required(rules: Rules, checks: List[Check]) -> None:
    """Repo checks only count if this hackathon's rules ask for them (D5, the submission window, always counts)."""
    needed = {"D5"} | {d for r in rules.requirements for d in links(r.text, r.category)}
    for c in checks:
        c.required = c.id in needed


def _linked_check(req_text: str, category: str, checks: Dict[str, Check]) -> Optional[Check]:
    """The deterministic check that decides a requirement: any linked failing check wins; license decides both ways."""
    linked = [d for d in links(req_text, category) if d != "D3"]
    found = [checks[i] for i in linked if i in checks]
    failing = [c for c in found if c.status == "fail"]
    if failing:
        return failing[0]
    if "D2" in linked:
        return checks.get("D2")
    return found[0] if found else None


def _cites_known(v: Verdict, known: Set[str]) -> bool:
    return any(k in e for e in v.evidence for k in known)


# Usage the code itself shows: model IDs and endpoints, not prose. A comment saying "Nemotron" is not usage.
NVIDIA_MODEL = re.compile(r"nvidia/[\w.-]+|nemotron[-_][\w.-]+", re.I)
NEBIUS_PLATFORM = re.compile(r"tokenfactory|nebius\.com|studio\.nebius|NEBIUS_API_KEY", re.I)
OTHER_PROVIDER = re.compile(r"api\.openai\.com|\bgpt-[34o][\w.-]*|\bo[134]-mini\b|claude-[\w.-]+|gemini-[\w.-]+|"
                            r"api\.anthropic\.com|generativelanguage\.googleapis", re.I)


def _usage_kind(req_text: str) -> Optional[str]:
    """'model' / 'platform' for a requirement to use NVIDIA models / Nebius, 'readme' for one to describe that use."""
    t = req_text.lower()
    names_model = "nvidia" in t or "nemotron" in t
    names_platform = "token factory" in t or "ai cloud" in t
    if "feedback" in t:
        return None
    if "readme" in t:
        return "readme" if names_model or names_platform else None
    if names_platform:
        return "platform"
    if names_model and "model" in t:
        return "model"
    return None


def code_usage(hits: List[str], evidence: List[FileEvidence], readme_path: Optional[str]) -> Dict[str, List[str]]:
    """path:line (or path) citations, from code and config only (never the README), for each kind of usage."""
    out: Dict[str, List[str]] = {"model": [], "platform": [], "other": []}
    for h in hits:  # 'path:line: text'
        path, line, text = (h.split(":", 2) + ["", ""])[:3]
        if path == readme_path or path.lower().endswith((".md", ".rst", ".txt")):
            continue
        for kind, pat in (("model", NVIDIA_MODEL), ("platform", NEBIUS_PLATFORM), ("other", OTHER_PROVIDER)):
            m = pat.search(text)
            if m:
                out[kind].append(f"{path}:{line}: {m.group(0)}")
    for e in evidence:
        for item in e.models_used + e.apis_called:
            for kind, pat in (("model", NVIDIA_MODEL), ("platform", NEBIUS_PLATFORM), ("other", OTHER_PROVIDER)):
                if pat.search(item):
                    out[kind].append(f"{e.path}: {item}")
    return out


def check_usage(kind: str, v: Verdict, usage: Dict[str, List[str]]) -> Verdict:
    """A README claim must not pass a usage requirement. If the code shows another provider and no NVIDIA model /
    Nebius endpoint, that's a fail with the line that proves it; with no signal either way, a pass becomes unclear."""
    needed = ["model", "platform"] if kind == "readme" else [kind]
    missing = [k for k in needed if not usage[k]]
    if not missing:
        return v
    what = {"model": "an NVIDIA model ID", "platform": "a Nebius Token Factory / AI Cloud endpoint"}
    absent = " or ".join(what[k] for k in missing)
    if usage["other"]:
        claim = "The README describes usage the code doesn't have. " if kind == "readme" else ""
        return Verdict(requirement_id=v.requirement_id, status="fail",
                       evidence=usage["other"][:2] + [f"No code or config references {absent}"],
                       fix=f"{claim}Switch the model call in {usage['other'][0].split(':')[0]} to Nemotron on Nebius "
                           "Token Factory (OpenAI-compatible: set base_url and the model ID).")
    # The fix must change code, never just the README: a README-only claim is exactly what fails here.
    code_fix = (f"Reference {absent} in code or config, e.g. an OpenAI-compatible client with "
                "base_url https://api.tokenfactory.nebius.com/v1/ and model nvidia/nemotron-3-super-120b-a12b"
                + (", then describe that in the README." if kind == "readme" else "."))
    if v.status == "pass":
        return Verdict(requirement_id=v.requirement_id, status="unclear",
                       evidence=v.evidence + [f"(downgraded: no code or config references {absent})"], fix=code_fix)
    return v.model_copy(update={"fix": code_fix})


def judge(rules: Rules, facts: RepoFacts, checks: List[Check], readme: str, evidence: List[FileEvidence],
          hits: List[str], stats: Optional[Dict[str, Any]] = None) -> List[Verdict]:
    by_id = {c.id: c for c in checks}
    checkable = [r for r in rules.requirements if r.checkable_from_repo]
    llm: Dict[str, Verdict] = {}
    if checkable:
        prompt = PROMPT.format(
            requirements="\n".join(f"{r.id}: {r.text}" for r in checkable),
            checks="\n".join(f"{c.id} {c.name}: {c.status.upper()} ({'; '.join(c.evidence)})" for c in checks),
            facts=facts.model_dump_json(exclude={"head_sha"}),
            readme_path=facts.readme_path or "none",
            readme=readme[:MAX_README_CHARS] or "(no README)",
            hits="\n".join(hits) or "(none found)",
            evidence="\n".join(json.dumps(e.model_dump()) for e in evidence) or "(none)",
            ids=", ".join(r.id for r in checkable))
        out = call_json(config.MODEL_SUPER, prompt, VerdictList, config.MAX_TOKENS_SUPER, stats=stats)
        llm = {v.requirement_id: v for v in (out.verdicts if out else [])}

    usage = code_usage(hits, evidence, facts.readme_path)
    # Files ShipCheck read: summarized ones, plus any with grep hits (a failed Nano summary mustn't erase a file).
    known = ({e.path for e in evidence} | {h.split(":", 1)[0] for h in hits} | set(by_id) | {facts.url, facts.full_name}
             | {p for p in (facts.readme_path, facts.license_file) if p})
    verdicts = []
    for r in rules.requirements:
        if not r.checkable_from_repo:
            verdicts.append(Verdict(requirement_id=r.id, status="not_checkable",
                                    evidence=["Not verifiable from the repo: confirm it yourself before submitting"]))
            continue
        v = llm.get(r.id) or Verdict(requirement_id=r.id, status="unclear",
                                     evidence=["The model returned no verdict for this requirement"],
                                     fix="Check this requirement manually.")
        linked = _linked_check(r.text, r.category, by_id)
        if (linked and linked.id == "D1" and linked.status == "pass" and v.status != "pass"
                and re.search(r"\burl\b|link", r.text.lower())):
            # "Provide a URL to a public repo": the repo we just read is that URL, and D1 says it's public.
            v = Verdict(requirement_id=r.id, status="pass", evidence=[f"D1: {facts.url} is public"])
        elif linked and (linked.status == "fail" or linked.id == "D2"):
            v = Verdict(requirement_id=r.id, status=linked.status, evidence=[f"{linked.id}: {e}" for e in linked.evidence]
                        + [e for e in v.evidence if linked.id not in e], fix=linked.fix or v.fix)
        elif v.status == "pass" and not _cites_known(v, known):
            # A false pass is the costly error: a pass must point at something we actually read.
            v = Verdict(requirement_id=r.id, status="unclear",
                        evidence=v.evidence + ["(downgraded: cited evidence doesn't match any file ShipCheck read)"],
                        fix=v.fix or "Make this visible in the README or code so a judge can find it.")
        kind = _usage_kind(r.text)
        if kind and not (linked and linked.status == "fail"):
            v = check_usage(kind, v, usage)
        verdicts.append(v)
    return verdicts
