"""GitHub ingestion (REST API, read-only) and deterministic checks. Never executes repo code."""
import base64
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

from shipcheck import config
from shipcheck.schemas import Check, RepoFacts, Rules

API = "https://api.github.com"
PER_FILE_CHARS = 12_000  # evidence.py truncates each file to this
RAW = "https://raw.githubusercontent.com"


class RepoError(Exception):
    """Repo URL invalid, not found, or private."""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    if config.GITHUB_TOKEN:
        s.headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return s


def parse_repo_url(url: str) -> Tuple[str, str]:
    m = re.search(r"(?:github\.com[/:])?([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$", url.strip().rstrip("/"))
    if not m or m.group(1) in ("http:", "https:"):
        raise RepoError(f"Not a GitHub repo URL: {url}")
    return m.group(1), m.group(2)


def _get(s: requests.Session, path: str, **params) -> requests.Response:
    r = s.get(API + path, params=params, timeout=20)
    if r.status_code == 403 and r.headers.get("X-RateLimit-Remaining") == "0":
        raise RepoError("GitHub rate limit reached; try again later")
    return r


# ---------- file selection ----------
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "vendor", ".venv", "venv", "__pycache__", ".next",
             "target", "out", "coverage", ".idea", ".vscode", "site-packages", "third_party"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".mp4", ".mov", ".mp3", ".wav", ".pdf",
            ".zip", ".gz", ".tar", ".whl", ".pkl", ".pt", ".pth", ".onnx", ".bin", ".h5", ".npy", ".parquet",
            ".ttf", ".woff", ".woff2", ".eot", ".lock", ".map", ".min.js", ".db", ".sqlite", ".ipynb", ".csv"}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "uv.lock",
             "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock"}
CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs",
            ".swift", ".dart", ".vue", ".svelte", ".sh"}
CONFIG_NAMES = {"requirements.txt", "pyproject.toml", "package.json", "Dockerfile", "docker-compose.yml",
                ".env.example", "env.example", "setup.py", "Cargo.toml", "go.mod", "app.yaml", "vercel.json"}
ENTRY_STEMS = {"app", "main", "index", "server", "streamlit_app", "agent", "api", "run", "cli"}
HINT_WORDS = ("llm", "model", "agent", "client", "api", "chat", "infer", "nebius", "nvidia", "tavily", "config")
# Platform / model names: a file mentioning these is the strongest evidence for usage requirements.
STRONG_PATTERN = re.compile(r"nebius|tokenfactory|nemotron|nvidia/|tavily", re.I)
# Runtime API usage worth surfacing to the evidence step.
USAGE_PATTERN = re.compile(r"openai|tavily|nebius|tokenfactory|nemotron|nvidia|anthropic|httpx|requests\.|"
                           r"fetch\(|axios|base_url|api_key|chat\.completions", re.I)


def _skippable(path: str, size: int) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if any(p in SKIP_DIRS for p in parts[:-1]) or name in LOCKFILES or size > config.MAX_FILE_BYTES:
        return True
    return any(name.lower().endswith(e) for e in SKIP_EXT)


def _rank(path: str) -> int:
    """Lower is more important (before reading contents)."""
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0].lower()
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    depth = path.count("/")
    if name in CONFIG_NAMES:
        return 1
    if ext in CODE_EXT:
        score = 3 + min(depth, 4)
        if stem in ENTRY_STEMS:
            score -= 2
        if any(w in path.lower() for w in HINT_WORDS):
            score -= 1
        if "test" in path.lower():
            score += 3
        return score
    if ext in (".md", ".toml", ".yaml", ".yml", ".json", ".cfg", ".ini"):
        return 8 + depth
    return 99


def _fetch_raw(s: requests.Session, full_name: str, sha: str, path: str) -> Optional[str]:
    try:
        r = s.get(f"{RAW}/{full_name}/{sha}/{path}", timeout=20)
        if r.status_code != 200:
            return None
        return r.content.decode("utf-8", errors="replace")
    except requests.RequestException:
        return None


def select_files(s: requests.Session, full_name: str, sha: str, tree: List[Dict], readme_path: Optional[str]
                 ) -> Dict[str, str]:
    """Pick up to MAX_FILES text files within MAX_TOTAL_BYTES, preferring files that name a platform/model,
    then files that call external APIs. Reads a wider pool first (raw fetches don't use the API rate limit)."""
    blobs = [(t["path"], t.get("size", 0)) for t in tree if t.get("type") == "blob"]
    candidates = sorted(((p, sz) for p, sz in blobs if not _skippable(p, sz) and p != readme_path
                         and _rank(p) < 99), key=lambda x: (_rank(x[0]), x[0]))
    pool, pool_bytes = [], 0
    for p, sz in candidates:
        if len(pool) >= 4 * config.MAX_FILES or pool_bytes + sz > 3 * config.MAX_TOTAL_BYTES:
            break
        pool.append(p)
        pool_bytes += sz
    with ThreadPoolExecutor(max_workers=16) as ex:
        contents = dict(zip(pool, ex.map(lambda p: _fetch_raw(s, full_name, sha, p), pool)))

    def priority(p: str):
        c = contents[p]
        return (0 if STRONG_PATTERN.search(c) else 1 if USAGE_PATTERN.search(c) else 2, _rank(p), p)

    chosen, total = {}, 0
    for p in sorted((p for p in pool if contents.get(p)), key=priority):
        if len(chosen) >= config.MAX_FILES - 1:  # README takes one slot
            break
        cost = min(len(contents[p]), PER_FILE_CHARS)  # the evidence step only reads this much
        if total + cost > config.MAX_TOTAL_BYTES:
            continue
        chosen[p] = contents[p]
        total += cost
    return chosen


# ---------- README ----------
SETUP_HEADING = re.compile(r"^#{1,4}\s*.*\b(install|installation|setup|set up|getting started|quick ?start|"
                           r"run(ning)?( it)? locally|how to run|usage|local development|deploy)", re.I | re.M)
SETUP_COMMAND = re.compile(r"\b(pip3? install|npm (install|i|run|start)|yarn( install| dev| start)?\b|pnpm |"
                           r"streamlit run|python3? \S+\.py|uvicorn |docker (compose|run|build)|cargo run|go run|"
                           r"poetry install|uv (sync|run)|make )", re.I)


def readme_has_setup(readme: str) -> bool:
    return bool(SETUP_HEADING.search(readme)) and bool(SETUP_COMMAND.search(readme))


# ---------- ingestion ----------
def head(repo_url: str) -> Tuple[str, str]:
    """(full_name, head commit SHA) of the default branch: 2 cheap API calls, used as the cache key."""
    owner, name = parse_repo_url(repo_url)
    s = _session()
    r = _get(s, f"/repos/{owner}/{name}")
    if r.status_code == 404:
        raise RepoError(f"Repo {owner}/{name} not found (or private)")
    r.raise_for_status()
    repo = r.json()
    if repo.get("private"):
        raise RepoError(f"{repo['full_name']} is private. Judges can't see it either: make it public, then rerun.")
    c = _get(s, f"/repos/{repo['full_name']}/commits/{repo['default_branch']}")
    c.raise_for_status()
    return repo["full_name"], c.json()["sha"]


def ingest(repo_url: str) -> Tuple[RepoFacts, str, Dict[str, str]]:
    """Returns (facts, README text, {path: content} for selected files). Private repos are not read."""
    owner, name = parse_repo_url(repo_url)
    s = _session()
    r = _get(s, f"/repos/{owner}/{name}")
    if r.status_code == 404:
        raise RepoError(f"Repo {owner}/{name} not found (or private)")
    r.raise_for_status()
    repo = r.json()
    full_name, branch = repo["full_name"], repo["default_branch"]
    if repo.get("private"):
        # The server's token may be able to read private repos; never ingest them for an anonymous user.
        raise RepoError(f"{full_name} is private. Judges can't see it either: make it public, then rerun.")

    c = _get(s, f"/repos/{full_name}/commits/{branch}")
    c.raise_for_status()
    head = c.json()
    sha = head["sha"]
    last_commit = head["commit"]["committer"]["date"]

    t = _get(s, f"/repos/{full_name}/git/trees/{sha}", recursive="1")
    t.raise_for_status()
    tree = t.json().get("tree", [])

    readme, readme_path = "", None
    rd = _get(s, f"/repos/{full_name}/readme")
    if rd.status_code == 200:
        j = rd.json()
        readme_path = j.get("path")
        readme = base64.b64decode(j.get("content", "")).decode("utf-8", errors="replace")

    lic = repo.get("license") or {}
    license_file = None
    if lic:
        lf = _get(s, f"/repos/{full_name}/license")
        if lf.status_code == 200:
            license_file = lf.json().get("path")

    files = select_files(s, full_name, sha, tree, readme_path)
    facts = RepoFacts(
        full_name=full_name, url=repo["html_url"], is_public=not repo.get("private"), default_branch=branch,
        head_sha=sha, license_spdx=lic.get("spdx_id"), license_file=license_file, has_readme=bool(readme),
        readme_path=readme_path, readme_has_setup=readme_has_setup(readme), last_commit_iso=last_commit,
        files_in_tree=sum(1 for x in tree if x.get("type") == "blob"), files_considered=len(files) + bool(readme))
    return facts, readme, files


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def commits_in_window(full_name: str, start: datetime, end: datetime) -> int:
    """Number of commits on the default branch in [start, end], capped at 100."""
    r = _get(_session(), f"/repos/{full_name}/commits", since=start.isoformat(), until=end.isoformat(),
             per_page=100)
    return len(r.json()) if r.status_code == 200 else 0


# ---------- deterministic checks ----------
def deterministic_checks(facts: RepoFacts, rules: Optional[Rules] = None) -> List[Check]:
    checks = [Check(id="D1", name="Repository is public", status="pass" if facts.is_public else "fail",
                    evidence=[f"GitHub reports {facts.full_name} as {'public' if facts.is_public else 'private'}"],
                    fix=None if facts.is_public else "Settings → General → Danger Zone → Change visibility → Public.")]

    if facts.license_spdx and facts.license_spdx != "NOASSERTION":
        checks.append(Check(id="D2", name="Open-source license detected by GitHub", status="pass",
                            evidence=[f"GitHub license detection: {facts.license_spdx} ({facts.license_file})"]))
    elif facts.license_spdx == "NOASSERTION":
        checks.append(Check(id="D2", name="Open-source license detected by GitHub", status="fail",
                            evidence=[f"{facts.license_file} exists, but GitHub can't identify the license"],
                            fix=f"Replace {facts.license_file} with an unmodified template (Add file → Create new "
                                "file → name it LICENSE → Choose a license template) so it shows in the About panel."))
    else:
        checks.append(Check(id="D2", name="Open-source license detected by GitHub", status="fail",
                            evidence=["GitHub detects no license in this repo"],
                            fix="Add file → Create new file → name it LICENSE → Choose a license template → MIT."))

    checks.append(Check(id="D3", name="README exists", status="pass" if facts.has_readme else "fail",
                        evidence=[facts.readme_path or "no README found by GitHub"],
                        fix=None if facts.has_readme else "Add a README.md at the repo root."))

    if facts.has_readme:
        checks.append(Check(id="D4", name="README has setup / run instructions",
                            status="pass" if facts.readme_has_setup else "fail",
                            evidence=[f"{facts.readme_path}: " + ("setup heading and run command found"
                                                                  if facts.readme_has_setup else
                                                                  "no setup heading with an install/run command")],
                            fix=None if facts.readme_has_setup else
                            "Add a '## Run locally' section with the exact clone, install and run commands."))

    start = _parse_dt(rules.submission_start) if rules else None
    end = _parse_dt(rules.deadline) if rules else None
    if start and end:
        n = commits_in_window(facts.full_name, start, end)
        checks.append(Check(id="D5", name="Commits during the submission period", status="pass" if n else "fail",
                            evidence=[f"{n}{'+' if n == 100 else ''} commits between {start:%d %b %Y} and "
                                      f"{end:%d %b %Y}; last commit {facts.last_commit_iso}"],
                            fix=None if n else "Commit and push your work made during the hackathon."))
    else:
        checks.append(Check(id="D5", name="Commits during the submission period", status="unclear",
                            evidence=[f"Submission period not found in the rules; last commit {facts.last_commit_iso}"],
                            fix="Check the rules' submission dates against your commit history."))
    return checks


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/streamlit/streamlit"
    facts, readme, files = ingest(url)
    print(facts.model_dump_json(indent=2))
    print(f"\nREADME: {len(readme)} chars. Selected {len(files)} files ({sum(map(len, files.values()))} chars):")
    for p in files:
        print("  ", p)
    print("\nCHECKS (no rules dates):")
    for ch in deterministic_checks(facts):
        print(f"  {ch.id} {ch.status.upper():8} {ch.name}  | {'; '.join(ch.evidence)}"
              + (f"\n     fix: {ch.fix}" if ch.fix else ""))
