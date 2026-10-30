"""GitHub ingestion (REST API, read-only) and deterministic checks. Never executes repo code."""
import base64
import logging
import re
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

from shipcheck import config
from shipcheck.schemas import Check, RepoFacts, Rules

log = logging.getLogger(__name__)
API = "https://api.github.com"
PER_FILE_CHARS = 12_000  # evidence.py truncates each file to this
RAW = "https://raw.githubusercontent.com"
GL_API = "https://gitlab.com/api/v4"
GL_TREE_CAP = 2000
BB_MAX_FETCH = 20
BB_API = "https://api.bitbucket.org/2.0"
BB_TREE_CAP = 2000


class RepoError(Exception):
    """Repo URL invalid, not found, or private."""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    if config.GITHUB_TOKEN:
        s.headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return s


def is_gitlab(url: str) -> bool:
    return bool(re.search(r"(?:^|//|@)(?:www\.)?gitlab\.com[/:]", url.strip(), re.I))


def _gl_parse(url: str) -> Tuple[str, str]:
    """gitlab.com/group[/subgroup...]/project -> ("group/subgroup", "project")."""
    m = re.search(r"gitlab\.com[/:](.+)$", url.strip(), re.I)
    path = m.group(1) if m else ""
    path = re.split(r"[?#]", path)[0].split("/-/")[0].rstrip("/")
    path = re.sub(r"\.git$", "", path)
    parts = [x for x in path.split("/") if x]
    if len(parts) < 2 or not all(re.fullmatch(r"[\w.-]+", x) for x in parts):
        raise RepoError(f"Not a GitLab repo URL: {url}")
    return "/".join(parts[:-1]), parts[-1]


def is_bitbucket(url: str) -> bool:
    return bool(re.search(r"(?:^|//|@)(?:www\.)?bitbucket\.org[/:]", url.strip(), re.I))


def _bb_parse(url: str) -> Tuple[str, str]:
    """bitbucket.org/workspace/repo[/...] -> ("workspace", "repo")."""
    m = re.search(r"bitbucket\.org[/:](.+)$", url.strip(), re.I)
    path = re.split(r"[?#]", m.group(1) if m else "")[0].rstrip("/")
    parts = [x for x in path.split("/") if x]
    if len(parts) < 2 or not all(re.fullmatch(r"[\w.-]+", x) for x in parts[:2]):
        raise RepoError(f"Not a Bitbucket repo URL: {url}")
    return parts[0], re.sub(r"\.git$", "", parts[1])


def parse_repo_url(url: str) -> Tuple[str, str]:
    if is_gitlab(url):
        return _gl_parse(url)
    if is_bitbucket(url):
        return _bb_parse(url)
    m = re.search(r"(?:github\.com[/:])?([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/.*)?$", url.strip().rstrip("/"))
    if not m or m.group(1) in ("http:", "https:"):
        raise RepoError(f"Not a GitHub repo URL: {url}")
    return m.group(1), m.group(2)


def _get(s: requests.Session, path: str, **params) -> requests.Response:
    r = s.get(API + path, params=params, timeout=20)
    if r.status_code == 401 and "Authorization" in s.headers:
        # Expired or revoked token: public repos still work unauthenticated (60 requests/hour instead of 5,000).
        log.warning("GITHUB_TOKEN rejected (401); continuing without it")
        del s.headers["Authorization"]
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


def _fetch_raw(s: Optional[requests.Session], full_name, sha: str, path: str) -> Optional[str]:
    if isinstance(full_name, int):  # GitLab project id
        return _gl_raw(full_name, sha, path)
    if isinstance(full_name, tuple):  # ("bb", "workspace/repo")
        return _bb_raw(full_name[1], sha, path)
    try:
        r = requests.get(f"{RAW}/{full_name}/{sha}/{path}", timeout=20)  # public files: no token needed
        if r.status_code != 200:
            return None
        return r.content.decode("utf-8", errors="replace")
    except requests.RequestException:
        return None


def select_files(s: Optional[requests.Session], full_name, sha: str, tree: List[Dict], readme_path: Optional[str]
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


# ---------- GitLab (REST v4, unauthenticated, public projects only) ----------
GL_LICENSE_SPDX = {"mit": "MIT", "apache-2.0": "Apache-2.0", "gpl-2.0": "GPL-2.0", "gpl-3.0": "GPL-3.0",
                   "lgpl-2.1": "LGPL-2.1", "lgpl-3.0": "LGPL-3.0", "agpl-3.0": "AGPL-3.0",
                   "bsd-2-clause": "BSD-2-Clause", "bsd-3-clause": "BSD-3-Clause", "mpl-2.0": "MPL-2.0",
                   "unlicense": "Unlicense", "isc": "ISC", "cc0-1.0": "CC0-1.0", "0bsd": "0BSD",
                   "epl-2.0": "EPL-2.0", "bsl-1.0": "BSL-1.0", "other": "NOASSERTION"}


def _gl_get(path: str, **params) -> requests.Response:
    r = requests.get(GL_API + path, params=params, timeout=20)
    if r.status_code == 429:
        raise RepoError("GitLab rate limit reached; try again later")
    return r


def _gl_project(owner: str, name: str) -> Dict:
    r = _gl_get(f"/projects/{quote(owner + '/' + name, safe='')}", license="true")
    if r.status_code in (401, 403, 404):
        raise RepoError(f"Repo {owner}/{name} not found (or private)")
    r.raise_for_status()
    p = r.json()
    if p.get("visibility", "public") != "public":
        raise RepoError(f"{p['path_with_namespace']} is private. Judges can't see it either: "
                        "make it public, then rerun.")
    return p


def _gl_head(repo_url: str) -> Tuple[str, str]:
    owner, name = parse_repo_url(repo_url)
    p = _gl_project(owner, name)
    if not p.get("default_branch"):
        raise RepoError(f"{p['path_with_namespace']} has no commits yet")
    c = _gl_get(f"/projects/{p['id']}/repository/commits/{quote(p['default_branch'], safe='')}")
    c.raise_for_status()
    return p["path_with_namespace"], c.json()["id"]


def _gl_tree(pid: int, sha: str) -> List[Dict]:
    """Recursive tree normalised to GitHub's shape ({path, type blob|tree, size}); GitLab gives no size."""
    out, page = [], "1"
    while page and len(out) < GL_TREE_CAP:
        r = _gl_get(f"/projects/{pid}/repository/tree", recursive="true", per_page=100, ref=sha, page=page)
        r.raise_for_status()
        out += [{"path": e["path"], "type": e["type"], "size": 0} for e in r.json()]
        page = r.headers.get("X-Next-Page", "")
    return out[:GL_TREE_CAP]


def _gl_raw(pid: int, sha: str, path: str) -> Optional[str]:
    try:
        r = requests.get(f"{GL_API}/projects/{pid}/repository/files/{quote(path, safe='')}/raw",
                         params={"ref": sha}, timeout=20)
        return r.content.decode("utf-8", errors="replace") if r.status_code == 200 else None
    except requests.RequestException:
        return None


def _gl_root_file(tree: List[Dict], pattern: str) -> Optional[str]:
    return next((t["path"] for t in sorted(tree, key=lambda t: t["path"])
                 if t["type"] == "blob" and "/" not in t["path"] and re.match(pattern, t["path"], re.I)), None)


def _gl_ingest(repo_url: str, ref: Optional[str]) -> Tuple[RepoFacts, str, Dict[str, str]]:
    owner, name = parse_repo_url(repo_url)
    p = _gl_project(owner, name)
    full_name, branch, pid = p["path_with_namespace"], p.get("default_branch"), p["id"]
    if not branch:
        raise RepoError(f"{full_name} has no commits yet")
    c = _gl_get(f"/projects/{pid}/repository/commits/{quote(ref or branch, safe='')}")
    c.raise_for_status()
    head_c = c.json()
    sha = head_c["id"]
    tree = _gl_tree(pid, sha)

    readme_path = _gl_root_file(tree, r"readme(\.\w+)?$")
    readme = (_gl_raw(pid, sha, readme_path) or "") if readme_path else ""
    if not readme:
        readme_path = None

    license_file = _gl_root_file(tree, r"(un)?licen[cs]e|copying")
    lic = p.get("license") or {}
    spdx = None
    if lic:
        spdx = GL_LICENSE_SPDX.get(str(lic.get("key", "")).lower()) or lic.get("nickname") or lic.get("name")
    if not spdx and license_file:
        spdx = "NOASSERTION"  # file present, but GitLab couldn't identify it (mirrors GitHub)

    files = select_files(None, pid, sha, tree, readme_path)
    facts = RepoFacts(
        full_name=full_name, url=p["web_url"], is_public=True, default_branch=branch, head_sha=sha,
        license_spdx=spdx, license_file=license_file, has_readme=bool(readme), readme_path=readme_path,
        readme_has_setup=readme_has_setup(readme), last_commit_iso=head_c.get("committed_date"),
        files_in_tree=sum(1 for x in tree if x["type"] == "blob"), files_considered=len(files) + bool(readme),
        license_file_present=license_file is not None)
    return facts, readme, files


def _gl_commits_in_window(full_name: str, start: datetime, end: datetime) -> int:
    r = _gl_get(f"/projects/{quote(full_name, safe='')}/repository/commits", since=start.isoformat(),
                until=end.isoformat(), per_page=100)
    return len(r.json()) if r.status_code == 200 else 0


# ---------- Bitbucket Cloud (REST 2.0, unauthenticated, public repos only) ----------
def _bb_get(path: str, **params) -> requests.Response:
    r = requests.get(path if path.startswith("http") else BB_API + path, params=params or None, timeout=20)
    if r.status_code == 429:
        raise RepoError("Bitbucket rate limit reached; try again later")
    return r


def _bb_repo(owner: str, name: str) -> Dict:
    r = _bb_get(f"/repositories/{owner}/{name}")
    if r.status_code in (401, 403, 404):
        raise RepoError(f"Repo {owner}/{name} not found (or private)")
    r.raise_for_status()
    repo = r.json()
    if repo.get("is_private"):
        raise RepoError(f"{repo.get('full_name', owner + '/' + name)} is private. Judges can't see it either: "
                        "make it public, then rerun.")
    return repo


def _bb_commit(full_name: str, ref: str) -> Dict:
    c = _bb_get(f"/repositories/{full_name}/commit/{quote(ref, safe='')}")
    if c.status_code == 404:
        raise RepoError(f"Ref {ref} not found in {full_name}")
    c.raise_for_status()
    return c.json()


def _bb_head(repo_url: str) -> Tuple[str, str]:
    owner, name = parse_repo_url(repo_url)
    repo = _bb_repo(owner, name)
    branch = (repo.get("mainbranch") or {}).get("name")
    if not branch:
        raise RepoError(f"{repo['full_name']} has no commits yet")
    return repo["full_name"], _bb_commit(repo["full_name"], branch)["hash"]


def _bb_tree(full_name: str, sha: str) -> List[Dict]:
    """Recursive tree normalised to GitHub's shape ({path, type blob|tree, size})."""
    out: List[Dict] = []
    url: Optional[str] = f"{BB_API}/repositories/{full_name}/src/{sha}/"
    params: Dict = {"max_depth": 10, "pagelen": 100}
    while url and len(out) < BB_TREE_CAP:
        r = _bb_get(url, **params)
        r.raise_for_status()
        j = r.json()
        out += [{"path": e["path"], "type": "blob" if e.get("type") == "commit_file" else "tree",
                 "size": e.get("size", 0) or 0} for e in j.get("values", [])]
        url, params = j.get("next"), {}
    return out[:BB_TREE_CAP]


def _bb_raw(full_name: str, sha: str, path: str) -> Optional[str]:
    try:
        r = requests.get(f"{BB_API}/repositories/{full_name}/src/{sha}/{quote(path)}", timeout=20)
        return r.content.decode("utf-8", errors="replace") if r.status_code == 200 else None
    except requests.RequestException:
        return None


def detect_license(text: str) -> str:
    """Match the head of a license file against well-known texts. Returns an SPDX id or "NOASSERTION"."""
    t = re.sub(r"\s+", " ", text[:1500]).lower()
    if "mozilla public license" in t and "version 2.0" in t:
        return "MPL-2.0"
    if "apache license" in t and "version 2.0" in t:
        return "Apache-2.0"
    if "gnu affero general public license" in t and "version 3" in t:
        return "AGPL-3.0"
    if "gnu lesser general public license" in t:
        return "LGPL-3.0" if "version 3" in t else "LGPL-2.1" if "version 2.1" in t else "NOASSERTION"
    if "gnu general public license" in t:
        return "GPL-3.0" if "version 3" in t else "GPL-2.0" if "version 2" in t else "NOASSERTION"
    if "mit license" in t[:200] and "permission is hereby granted, free of charge" in t:
        return "MIT"
    if "redistribution and use in source and binary forms" in t:
        return "BSD-3-Clause" if "neither the name" in t else "BSD-2-Clause"
    if "this is free and unencumbered software" in t:
        return "Unlicense"
    return "NOASSERTION"


def _bb_ingest(repo_url: str, ref: Optional[str]) -> Tuple[RepoFacts, str, Dict[str, str]]:
    owner, name = parse_repo_url(repo_url)
    repo = _bb_repo(owner, name)
    full_name = repo["full_name"]
    branch = (repo.get("mainbranch") or {}).get("name")
    if not branch:
        raise RepoError(f"{full_name} has no commits yet")
    head_c = _bb_commit(full_name, ref or branch)
    sha = head_c["hash"]
    tree = _bb_tree(full_name, sha)

    readme_path = _gl_root_file(tree, r"readme(\.\w+)?$")
    readme = (_bb_raw(full_name, sha, readme_path) or "") if readme_path else ""
    if not readme:
        readme_path = None

    license_file = _gl_root_file(tree, r"(un)?licen[cs]e|copying")
    spdx = detect_license(_bb_raw(full_name, sha, license_file) or "") if license_file else None

    # Bitbucket's anonymous API limit is small and every raw fetch counts, so only fetch the best-ranked paths.
    pool = sorted((t for t in tree if t["type"] == "blob" and not _skippable(t["path"], t.get("size", 0))),
                  key=lambda t: _rank(t["path"]))[:BB_MAX_FETCH]
    files = select_files(None, ("bb", full_name), sha, pool, readme_path)
    html = ((repo.get("links") or {}).get("html") or {}).get("href") or f"https://bitbucket.org/{full_name}"
    facts = RepoFacts(
        full_name=full_name, url=html, is_public=True, default_branch=branch, head_sha=sha, license_spdx=spdx,
        license_file=license_file, has_readme=bool(readme), readme_path=readme_path,
        readme_has_setup=readme_has_setup(readme), last_commit_iso=head_c.get("date"),
        files_in_tree=sum(1 for x in tree if x["type"] == "blob"), files_considered=len(files) + bool(readme),
        license_file_present=license_file is not None)
    return facts, readme, files


def _bb_commits_in_window(full_name: str, start: datetime, end: datetime) -> Optional[int]:
    try:
        return _bb_count_commits(full_name, start, end)
    except RepoError:  # rate limited: let D5 fall back to the last commit date rather than failing the run
        return None


def _bb_count_commits(full_name: str, start: datetime, end: datetime) -> int:
    r = _bb_get(f"/repositories/{full_name}")
    branch = ((r.json().get("mainbranch") or {}).get("name") or "") if r.status_code == 200 else ""
    if not branch:
        return 0
    r = _bb_get(f"/repositories/{full_name}/commits/{quote(branch, safe='')}", pagelen=100)
    if r.status_code != 200:
        return 0
    n = 0
    for c in r.json().get("values", []):
        d = _parse_dt(c.get("date"))
        if d and start <= d <= end:
            n += 1
    return n


# ---------- ingestion ----------
def head(repo_url: str) -> Tuple[str, str]:
    """(full_name, head commit SHA) of the default branch: 2 cheap API calls, used as the cache key."""
    if is_gitlab(repo_url):
        return _gl_head(repo_url)
    if is_bitbucket(repo_url):
        return _bb_head(repo_url)
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


def ingest(repo_url: str, ref: Optional[str] = None) -> Tuple[RepoFacts, str, Dict[str, str]]:
    """Returns (facts, README text, {path: content} for selected files) at `ref` (default: the default branch's
    head). Private repos are not read."""
    if is_gitlab(repo_url):
        return _gl_ingest(repo_url, ref)
    if is_bitbucket(repo_url):
        return _bb_ingest(repo_url, ref)
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

    c = _get(s, f"/repos/{full_name}/commits/{ref or branch}")
    c.raise_for_status()
    head = c.json()
    sha = head["sha"]
    last_commit = head["commit"]["committer"]["date"]

    t = _get(s, f"/repos/{full_name}/git/trees/{sha}", recursive="1")
    t.raise_for_status()
    tree = t.json().get("tree", [])

    readme, readme_path = "", None
    rd = _get(s, f"/repos/{full_name}/readme", ref=sha)
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
        files_in_tree=sum(1 for x in tree if x.get("type") == "blob"), files_considered=len(files) + bool(readme),
        license_file_present=any(x.get("type") == "blob" and "/" not in x["path"]
                                 and re.match(r"(un)?licen[cs]e|copying", x["path"], re.I) for x in tree))
    return facts, readme, files


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def commits_in_window(full_name: str, start: datetime, end: datetime, url: str = "") -> Optional[int]:
    """Number of commits on the default branch in [start, end], capped at 100; None if it couldn't be counted."""
    if is_gitlab(url):
        return _gl_commits_in_window(full_name, start, end)
    if is_bitbucket(url):
        return _bb_commits_in_window(full_name, start, end)
    r = _get(_session(), f"/repos/{full_name}/commits", since=start.isoformat(), until=end.isoformat(),
             per_page=100)
    return len(r.json()) if r.status_code == 200 else 0


# ---------- deterministic checks ----------
def deterministic_checks(facts: RepoFacts, rules: Optional[Rules] = None) -> List[Check]:
    bb = is_bitbucket(facts.url)
    host = "Bitbucket" if bb else "GitLab" if is_gitlab(facts.url) else "GitHub"
    checks = [Check(id="D1", name="Repository is public", status="pass" if facts.is_public else "fail",
                    evidence=[f"{host} reports {facts.full_name} as {'public' if facts.is_public else 'private'}"],
                    fix=None if facts.is_public else "Settings → General → Danger Zone → Change visibility → Public.")]

    if bb:  # Bitbucket has no license detection: we match the root license file's text ourselves.
        d2 = "Open-source license detected"
        if facts.license_spdx and facts.license_spdx != "NOASSERTION":
            checks.append(Check(id="D2", name=d2, status="pass",
                                evidence=[f"License file check: {facts.license_spdx} ({facts.license_file})"]))
        elif facts.license_spdx == "NOASSERTION":
            checks.append(Check(id="D2", name=d2, status="fail",
                                evidence=[f"{facts.license_file} exists, but it doesn't match a standard license text"],
                                fix=f"Replace {facts.license_file} with an unmodified license template "
                                    "(e.g. the MIT text from choosealicense.com)."))
        else:
            checks.append(Check(id="D2", name=d2, status="fail",
                                evidence=["No LICENSE file found at the repo root"],
                                fix="Add a LICENSE file at the repo root with an open-source license text "
                                    "(e.g. MIT from choosealicense.com)."))
    elif facts.license_spdx and facts.license_spdx != "NOASSERTION":
        checks.append(Check(id="D2", name=f"Open-source license detected by {host}", status="pass",
                            evidence=[f"{host} license detection: {facts.license_spdx} ({facts.license_file})"]))
    elif facts.license_spdx == "NOASSERTION":
        checks.append(Check(id="D2", name=f"Open-source license detected by {host}", status="fail",
                            evidence=[f"{facts.license_file} exists, but {host} can't identify the license"],
                            fix=f"Replace {facts.license_file} with an unmodified template (Add file → Create new "
                                "file → name it LICENSE → Choose a license template) so it shows in the About panel."))
    else:
        checks.append(Check(id="D2", name=f"Open-source license detected by {host}", status="fail",
                            evidence=[f"{host} detects no license in this repo"],
                            fix="Add file → Create new file → name it LICENSE → Choose a license template → MIT."))

    checks.append(Check(id="D3", name="README exists", status="pass" if facts.has_readme else "fail",
                        evidence=[facts.readme_path or f"no README found by {host}"],
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
        n = commits_in_window(facts.full_name, start, end, facts.url)
        last = _parse_dt(facts.last_commit_iso)
        counted = n is not None
        if not counted:  # couldn't count (rate limited); the head commit's date still tells us something
            n = 1 if last and start <= last <= end else 0
        what = (f"{n}{'+' if n == 100 else ''} commits" if counted
                else f"Couldn't count commits; the last commit is {'inside' if n else 'outside'} the window")
        checks.append(Check(id="D5", name="Commits during the submission period", status="pass" if n else "fail",
                            evidence=[f"{what} between {start:%d %b %Y} and "
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
