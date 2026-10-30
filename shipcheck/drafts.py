"""Turn a README failure into a ready-to-paste section, written from the evidence ShipCheck already gathered."""
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel

from shipcheck import config
from shipcheck.llm import call_json
from shipcheck.schemas import Report

PROMPT = """Write the README section that fixes this failed hackathon requirement for the project below.

Rules:
- Use ONLY the facts given: real file paths, model IDs, services and commands that the evidence supports.
- Never invent features, numbers, results or URLs. Where a fact is missing, write a placeholder like <TODO: demo URL>.
- Keep it short and scannable: a heading, a few bullets or a small table, and exact commands in code blocks.
- If the requirement asks to highlight how specific platforms/models are used, name each one with the file where it is used.

REQUIREMENT: {requirement}
WHY IT FAILED: {why}

PROJECT: {full_name} (license: {license})
CURRENT README (excerpt):
{readme}

FILES READ AND WHAT THEY DO:
{evidence}"""


class Draft(BaseModel):
    heading: str
    markdown: str


def is_readme_fix(report: Report, requirement_id: str) -> bool:
    r = next((x for x in report.rules.requirements if x.id == requirement_id), None)
    return bool(r) and (r.category == "readme" or "readme" in r.text.lower())


def draft_readme_section(report: Report, requirement_id: str, stats: Optional[Dict[str, Any]] = None
                         ) -> Optional[Draft]:
    r = next(x for x in report.rules.requirements if x.id == requirement_id)
    v = next(x for x in report.verdicts if x.requirement_id == requirement_id)
    evidence = "\n".join(json.dumps({"path": e.path, "purpose": e.purpose, "models": e.models_used,
                                     "calls": e.apis_called}) for e in report.evidence)
    prompt = PROMPT.format(requirement=r.text, why=v.fix or "; ".join(v.evidence),
                           full_name=report.facts.full_name, license=report.facts.license_spdx or "none detected",
                           readme=report.readme[:4000] or "(empty)", evidence=evidence or "(none)")
    return call_json(config.MODEL_SUPER, prompt, Draft, config.MAX_TOKENS_SUPER, thinking=False, stats=stats)
