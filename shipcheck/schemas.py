"""Pydantic models for every LLM output and pipeline result. Python 3.9-compatible typing."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["platform", "model", "repo", "license", "readme", "video", "description", "feedback", "other"]
Status = Literal["pass", "fail", "unclear", "not_checkable"]


class Requirement(BaseModel):
    id: str = Field(description="Short stable id, e.g. R1, R2")
    text: str = Field(description="The requirement, close to the rules' wording")
    category: Category
    checkable_from_repo: bool = Field(description="True only if verifiable from a public GitHub repo")


class Criterion(BaseModel):
    name: str
    description: str


class Rules(BaseModel):
    hackathon_name: str
    submission_start: Optional[str] = Field(None, description="ISO 8601 with timezone offset, or null")
    deadline: Optional[str] = Field(None, description="ISO 8601 with timezone offset, or null")
    tracks: List[str]
    requirements: List[Requirement]
    criteria: List[Criterion]


class FileEvidence(BaseModel):
    path: str
    purpose: str
    models_used: List[str]
    apis_called: List[str]
    notable: List[str]


class RepoFacts(BaseModel):
    full_name: str
    url: str
    is_public: bool
    default_branch: str
    head_sha: str
    license_spdx: Optional[str]  # GitHub's own detection; NOASSERTION = file found but not identified
    license_file: Optional[str]
    has_readme: bool
    readme_path: Optional[str]
    readme_has_setup: bool
    last_commit_iso: Optional[str]
    files_in_tree: int
    files_considered: int


class Check(BaseModel):
    """A deterministic (no-LLM) check on the repo."""
    id: str
    name: str
    status: Status
    evidence: List[str]
    fix: Optional[str] = None
    required: bool = True  # False: this hackathon's rules don't ask for it (shown as info only)


class Verdict(BaseModel):
    requirement_id: str
    status: Status
    evidence: List[str] = Field(description="File paths or repo facts")
    fix: Optional[str] = Field(None, description="One concrete fix for fail/unclear, else null")


class VerdictList(BaseModel):
    verdicts: List[Verdict]


class CriterionScore(BaseModel):
    criterion: str
    score: int = Field(ge=1, le=5)
    rationale: str
    improvements: List[str]


class ScoreList(BaseModel):
    scores: List[CriterionScore]


class Report(BaseModel):
    """Everything one run produces; what gets cached and rendered."""
    hackathon_url: str
    repo_url: str
    rules: Rules
    rules_source: str
    facts: RepoFacts
    checks: List[Check]
    verdicts: List[Verdict]
    evidence: List[FileEvidence]
    usage: Dict[str, Any]
    seconds: float
    created_at: str
    readme: str = ""  # first 8K chars, for drafting README fixes
    video_url: str = ""
    description_checked: bool = False
