"""Devpost submission check: the demo video (YouTube metadata, no AI) and the write-up (Nemotron Super)."""
import re
from typing import Any, Dict, List, Optional

import requests

from shipcheck import config
from shipcheck.llm import call_json
from shipcheck.schemas import Check, Rules, Verdict, VerdictList

YT_ID = re.compile(r"(?:youtu\.be/|[?&]v=|/shorts/|/embed/|/live/)([\w-]{11})")
WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10}
LIMIT = re.compile(r"(?:under|less than|shorter than|no (?:longer|more) than|maximum(?: of)?|max\.?|up to|"
                   r"not exceed(?:ing)?|within)\s+\(?(\d+|" + "|".join(WORD_NUM) + r")\)?\s*-?\s*min", re.I)
MAX_DESCRIPTION_CHARS = 15_000


def _is_video(category: str, text: str) -> bool:
    return category == "video" or "video" in text.lower()


def video_limit_minutes(rules: Rules) -> Optional[int]:
    for r in rules.requirements:
        if _is_video(r.category, r.text):
            m = LIMIT.search(r.text)
            if m:
                n = m.group(1).lower()
                return int(n) if n.isdigit() else WORD_NUM[n]
    return None


def video_facts(url: str) -> Dict[str, Any]:
    """Public metadata from the YouTube watch page: playability, private/unlisted flags, length."""
    m = YT_ID.search(url)
    if not m:
        return {"error": "not a YouTube video link"}
    vid = m.group(1)
    facts: Dict[str, Any] = {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}
    try:
        page = requests.get(facts["url"], timeout=15, cookies={"CONSENT": "YES+"},
                            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en"}).text
    except requests.RequestException as e:
        return {**facts, "error": f"couldn't reach YouTube ({type(e).__name__})"}
    status = re.search(r'"playabilityStatus":\{"status":"([A-Z_]+)"', page)
    facts["status"] = status.group(1) if status else None
    for key in ("isPrivate", "isUnlisted"):
        m2 = re.search(rf'"{key}":(true|false)', page)
        facts[key] = (m2.group(1) == "true") if m2 else None
    secs = re.search(r'"lengthSeconds":"(\d+)"', page)
    facts["seconds"] = int(secs.group(1)) if secs else None
    return facts


def video_checks(url: str, rules: Rules) -> List[Check]:
    f = video_facts(url)
    if f.get("error") or not f.get("status"):
        return [Check(id="V1", name="Demo video is public on YouTube", status="unclear",
                      evidence=[f"{url}: {f.get('error', 'YouTube returned no video details')}"],
                      fix="Open the link in a logged-out browser and confirm it plays.")]
    public = f["status"] == "OK" and not f.get("isPrivate") and not f.get("isUnlisted")
    if public:
        state, fix = "public, plays logged out", None
    elif f["status"] == "OK" and f.get("isUnlisted"):
        state, fix = "UNLISTED", "YouTube Studio → Content → Visibility → Public. Rules usually say public."
    elif f["status"] == "LOGIN_REQUIRED" or f.get("isPrivate"):
        state, fix = "PRIVATE", "YouTube Studio → Content → Visibility → Public."
    else:
        state, fix = f"not playable ({f['status']})", "Check the link: this video doesn't play for judges."
    checks = [Check(id="V1", name="Demo video is public on YouTube", status="pass" if public else "fail",
                    evidence=[f"{f['url']}: {state}"], fix=fix)]

    limit = video_limit_minutes(rules)
    if limit and f.get("seconds") is not None:
        s = f["seconds"]
        ok = s < limit * 60
        checks.append(Check(id="V2", name=f"Video is under {limit} minutes", status="pass" if ok else "fail",
                            evidence=[f"Length {s // 60}:{s % 60:02d} (limit {limit}:00)"],
                            fix=None if ok else f"Cut {s - limit * 60 + 1}s or more: judges may stop watching "
                                                f"at {limit}:00, and the rules make it a requirement."))
    return checks


def apply_video(rules: Rules, verdicts: List[Verdict], checks: List[Check]) -> List[Verdict]:
    """A failing video check fails the video requirements; passing ones become evidence (content stays unverified)."""
    reqs = {r.id: r for r in rules.requirements}
    failing = [c for c in checks if c.status == "fail"]
    out = []
    for v in verdicts:
        r = reqs.get(v.requirement_id)
        if r and _is_video(r.category, r.text) and not r.checkable_from_repo:
            facts = [f"{c.id}: {c.status.upper()} ({'; '.join(c.evidence)})" for c in checks]
            if failing:
                v = Verdict(requirement_id=v.requirement_id, status="fail", evidence=facts, fix=failing[0].fix)
            else:
                v = Verdict(requirement_id=v.requirement_id, status="not_checkable",
                            evidence=facts + ["Content not verified: watch it once logged out"])
        out.append(v)
    return out


PROMPT = """Below is a hackathon entrant's Devpost submission text, and the hackathon requirements that can't be checked from their code.

Judge ONLY requirements the submission text itself should satisfy (e.g. explaining features and functionality, how tools/models were used, feedback on tools, what changed during the submission period).
- pass: the text clearly satisfies it. evidence MUST include a short exact quote (copied verbatim, 5-20 words) from the text.
- fail: the text should satisfy it but doesn't. fix: one sentence saying exactly what to add.
- not_checkable: can't be judged from this text: anything chosen in a form dropdown or field (track/category selection, team members), eligibility, legal terms, the video, whether the form was submitted.
- Never invent example values (track names, URLs) in a fix; refer only to what the requirement itself names.

REQUIREMENTS:
{requirements}

SUBMISSION TEXT:
{text}

Return one verdict per requirement id: {ids}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'“”‘’`*_]", "", s)).strip().lower()


def judge_description(rules: Rules, verdicts: List[Verdict], text: str,
                      stats: Optional[Dict[str, Any]] = None) -> List[Verdict]:
    reqs = {r.id: r for r in rules.requirements}
    todo = [reqs[v.requirement_id] for v in verdicts
            if v.status == "not_checkable" and v.requirement_id in reqs
            and not _is_video(reqs[v.requirement_id].category, reqs[v.requirement_id].text)]
    if not todo or not text.strip():
        return verdicts
    out = call_json(config.MODEL_SUPER, PROMPT.format(
        requirements="\n".join(f"{r.id}: {r.text}" for r in todo), text=text[:MAX_DESCRIPTION_CHARS],
        ids=", ".join(r.id for r in todo)), VerdictList, config.MAX_TOKENS_SUPER, stats=stats)
    got = {v.requirement_id: v for v in (out.verdicts if out else [])}
    body = _norm(text)
    result = []
    for v in verdicts:
        new = got.get(v.requirement_id)
        if new and v.status == "not_checkable" and new.status in ("pass", "fail"):
            if new.status == "pass" and not any(len(_norm(e)) >= 12 and _norm(e) in body for e in new.evidence):
                # Same rule as the repo: a pass must point at text we actually have.
                new = Verdict(requirement_id=v.requirement_id, status="unclear",
                              evidence=new.evidence + ["(downgraded: quote not found in your text)"],
                              fix="State this explicitly in your Devpost description.")
            new.evidence = [f"Devpost text: {e}" for e in new.evidence]
            v = new
        result.append(v)
    return result
