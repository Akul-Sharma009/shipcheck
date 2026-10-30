# ShipCheck — Hackathon Brief

> Pre-judge your hackathon submission before the judges do.

**Hackathon:** Nebius x NVIDIA Global AI Hackathon (Devpost)
**Deadline:** Sat 31 Oct 2026, 1:00 AM SGT (= Fri 30 Oct, 10:00 AM PT). Target submit: 12:30 AM SGT.
**Track:** Best Apps and Agents
**Bonus prize targeted:** Best Use of Tavily (requires a functional runtime call to the Tavily API)
**Builder:** solo
**Status:** started 30 Oct, 5:45 PM SGT

---

## 1. Hackathon facts that constrain the build

### Hard requirements (Stage One is pass/fail on these)
- Must make a **runtime call to Nebius Token Factory** (or run on Nebius AI Cloud). Calling NVIDIA models via HuggingFace/OpenRouter/etc. does NOT count.
- Must use **at least one NVIDIA open-source model** (Nemotron, GR00T, Cosmos, Sonic, etc.).
- Must be a genuine attempt at the track's goal, not a rebrand of an unrelated idea.
- The rest of the app (frontend, other backend) can be hosted anywhere.

### What to submit
- [ ] Track selection: Best Apps and Agents
- [ ] **Working demo URL** (hosted app), free and unrestricted for judges until judging ends (23 Dec 2026)
- [ ] **Project description:** what, why, how
- [ ] **Public repo** (GitHub) with an **open-source license detected by GitHub** (visible in the About section): MIT
- [ ] **README** with setup + run instructions, and a clear section on how NVIDIA models, Token Factory, and other Nebius tools are used
- [ ] **Demo video**: under 3 minutes, **public on YouTube**, shows the app working and explains Nebius + NVIDIA usage, no copyrighted music
- [ ] **Feedback** on Token Factory and NVIDIA models used (required, and separately prized)
- [ ] All materials in English

### Judging criteria (equal weight)
1. **Technological Implementation:** how well it's built and how effectively it uses Token Factory + Nemotron
2. **Design:** complete, coherent product experience, not a proof of concept
3. **Potential Impact:** credible, specific case for a real problem and real audience, shown in the demo
4. **Quality of the Idea:** creative, non-obvious use of the models; genuine understanding of the problem space

Judges' advice from the "Will It Ship?" session: real problem for a real audience; the aha moment within 30 seconds of the demo.

### Prize eligibility notes
- A project can win one overall award, OR one track award + one bonus award.
- City Winner requires having attended the in-person Builders & Brews event (Singapore was 14 Sep). Skip unless attended.
- Most Valuable Feedback ($100 + swag, 10 winners): judged on completeness, viability, impact of feedback.

### Judging timeline
- Judging: 9–23 Dec 2026. **The hosted demo and its API credits must still work through 23 Dec.**
- Winners announced around 25 Jan 2027.

---

## 2. The product

### One-liner
Paste a hackathon URL and your GitHub repo. In under a minute, ShipCheck gives you a pass/fail report on every submission requirement, a score on each judging criterion, and the specific fixes to make before the deadline.

### Problem
Submissions lose points or get disqualified for avoidable reasons:
- license not detected by GitHub
- README missing setup steps
- required model/platform usage never called out
- project misses the track's actual goal

Rules pages are long and nobody rereads them at 11 PM.

### Audience
Hackathon participants in the final hours before a deadline. This hackathon alone has 29,561 registrants; Devpost runs dozens of hackathons at a time. Secondary audience: organizers who want to pre-screen submissions.

### Why I'm credible on this
I built ShipCheck in the final 8 hours of this hackathon, under exactly the conditions it's designed for. ShipCheck passes its own check.

### The aha moment (first 30 seconds of the demo)
1. Run ShipCheck on a deliberately broken demo repo (no license, thin README).
2. Red **FAIL: no open-source license detected**, with a one-line fix.
3. Add the license, rerun, and it goes green.

---

## 3. Features

### P0: must ship
1. **Input form:** hackathon URL, GitHub repo URL, optional "paste rules text" box (fallback if extraction fails).
2. **Rules extraction:** Tavily Extract pulls the hackathon overview + rules pages; Nemotron Super converts them into structured `rules.json` (requirements + judging criteria).
3. **Repo ingestion (GitHub REST API):** public/private, detected license, README, file tree, contents of up to ~40 relevant files.
4. **Deterministic checks (no LLM):** repo public; license detected by GitHub; README exists; README has setup/run section; repo has commits within the submission period.
5. **Requirement verdicts:** Pass / Fail / Unclear for each requirement, with evidence citing file paths.
6. **Report card UI:** traffic-light checklist, "Fix this" line under each failure, overall readiness summary.

**CUT LINE:** if P0 is not working end to end by 9:00 PM, stop adding features and polish P0.

### P1: should ship
7. **Judging-criteria scores** (Nemotron Ultra): 1–5 per criterion, 2-line rationale, top 3 improvements.
8. **Originality check:** Tavily Search for similar projects (Devpost galleries, GitHub), fed into the Quality of the Idea score.
9. **README generator:** auto-drafts a "How this project uses NVIDIA models and Nebius" section from the evidence found.

### P2: only if ahead
10. Check a pasted Devpost description against the rules (e.g. missing feedback section).
11. Export report as Markdown.

### Explicitly out of scope
- Executing any repo code
- Private repos / GitHub OAuth
- Watching the YouTube video
- Non-Devpost platforms (mention as "what's next")

---

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| UI | Streamlit | Custom theme in `.streamlit/config.toml` |
| Hosting | Streamlit Community Cloud | Free; secrets via the dashboard |
| LLM inference | Nebius Token Factory | OpenAI-compatible API |
| LLM client | `openai` Python SDK | Pointed at Token Factory's base URL |
| Models | Nemotron 3 Nano / Super / Ultra | See routing table below |
| Web extraction + search | Tavily (`tavily-python`) | Extract for rules pages, Search for originality |
| Repo data | GitHub REST API via `requests` | Authenticated with a personal access token |
| Validation | Pydantic v2 | For every LLM output |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` | Parallel Nano calls |
| Caching | `st.cache_data` keyed by commit SHA + hackathon URL | Protects credits during judging |

### Token Factory
- Base URL: `https://api.tokenfactory.nebius.com/v1/`
- Auth: API key from the Token Factory console (API keys page; shown only once)
- **Confirm exact model IDs in the Token Factory model catalog before coding.** Expected:
  - Nano: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
  - Super: `nvidia/nemotron-3-super-120b-a12b`
  - Ultra: `nvidia/Nemotron-3-ultra-550b-a55b`

### Model routing

| Job | Model | Why |
|---|---|---|
| Per-file evidence extraction | Nemotron 3 Nano | Many small parallel calls; fast and cheap |
| Rules → structured checklist | Nemotron 3 Super | Reliable structured output |
| Requirement verdicts | Nemotron 3 Super | Reasoning over rules + evidence |
| Judging scores + fixes (P1) | Nemotron 3 Ultra | Hardest reasoning step, one call per run |

This mirrors the track's own guidance (Ultra for serious reasoning, Nano/Super for fast everyday calls). Call it out in the README and video.

### Rough cost per run (approximate; check live pricing)
- Nano: ~40 files × ~3K tokens in + ~300 out ≈ $0.01
- Super: ~20K in + ~3K out ≈ $0.01
- Ultra: ~25K in + ~3K out ≈ $0.03–0.04
- **Total ≈ $0.05 per uncached run.** $50 of credits covers roughly 1,000 runs. Caching and a per-session cap keep judging safe.

---

## 5. Accounts, keys, and credits

| Service | What's needed | How |
|---|---|---|
| Nebius Token Factory | Account + API key + credits | Sign up at tokenfactory.nebius.com; redeem $25 via the hackathon promo form with code `NEBIUS-DEVPOST-GLOBAL26`; another $25 via the Nebius Builders Program (dev.nebius.com/builders) |
| Tavily | API key (+ credits) | Builders Program includes Tavily credits; also check the free tier on the Tavily dashboard |
| GitHub | Public repo + personal access token (read-only, public repos) | Settings → Developer settings → Fine-grained tokens |
| Streamlit Community Cloud | Account linked to GitHub | share.streamlit.io |
| YouTube | Channel to upload a public video | |
| Devpost | Already registered | |

If credits don't appear or the country/billing screen blocks you: Nebius Discord, immediately.

### Environment variables

```
# .env.example
NEBIUS_API_KEY=
TAVILY_API_KEY=
GITHUB_TOKEN=
MODEL_NANO=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
MODEL_SUPER=nvidia/nemotron-3-super-120b-a12b
MODEL_ULTRA=nvidia/nemotron-3-ultra-550b-a55b
MAX_FILES=40
MAX_RUNS_PER_SESSION=5
```

Model IDs are env vars so a wrong or retired ID is a config change, not a code change.

### requirements.txt

```
streamlit
openai
tavily-python
requests
pydantic>=2
python-dotenv
```

---

## 6. Architecture

```
hackathon URL ─► Tavily Extract ─► Nemotron Super ─► rules.json
                 (overview + rules pages)            (requirements + judging criteria)
                 [fallback: pasted rules text]

repo URL ─► GitHub API ─► deterministic checks ─────────────────┐
                    └─► selected files ─► Nemotron Nano ×N ─► evidence.json
                                          (parallel)            │
                                                                ▼
                        rules.json + evidence.json + checks ─► Nemotron Super ─► verdicts
                                                          └──► Nemotron Ultra ─► scores + fixes (P1)

Tavily Search (similar projects) ─► originality context ─► Ultra (P1)

All results ─► Streamlit report card
```

### Repo layout

```
shipcheck/
├── app.py                  # Streamlit UI
├── shipcheck/
│   ├── __init__.py
│   ├── config.py           # env vars, model IDs, limits
│   ├── llm.py              # Token Factory client, call_json() with retry + Pydantic validation
│   ├── rules.py            # Tavily Extract → Super → Rules
│   ├── repo.py             # GitHub ingestion + deterministic checks
│   ├── evidence.py         # Nano per-file extraction (parallel)
│   ├── judge.py            # Super verdicts, Ultra scores
│   ├── originality.py      # Tavily Search (P1)
│   └── schemas.py          # Pydantic models
├── examples/               # cached sample reports (offline demo fallback)
├── .streamlit/config.toml  # theme
├── .env.example
├── requirements.txt
├── LICENSE                 # MIT
└── README.md
```

### Data schemas (Pydantic sketch)

```python
class Requirement(BaseModel):
    id: str
    text: str
    category: Literal["platform", "model", "repo", "readme", "video", "description", "feedback", "other"]
    checkable_from_repo: bool

class Criterion(BaseModel):
    name: str
    description: str

class Rules(BaseModel):
    hackathon_name: str
    deadline: str | None
    tracks: list[str]
    requirements: list[Requirement]
    criteria: list[Criterion]

class FileEvidence(BaseModel):
    path: str
    purpose: str
    models_used: list[str]
    apis_called: list[str]          # e.g. "Nebius Token Factory", "Tavily"
    notable: list[str]

class RepoFacts(BaseModel):
    full_name: str
    is_public: bool
    license_spdx: str | None        # from GitHub's own license detection
    has_readme: bool
    readme_has_setup: bool
    last_commit_iso: str
    files_considered: int

class Verdict(BaseModel):
    requirement_id: str
    status: Literal["pass", "fail", "unclear", "not_checkable"]
    evidence: list[str]             # file paths or facts
    fix: str | None

class CriterionScore(BaseModel):
    criterion: str
    score: int                      # 1–5
    rationale: str
    improvements: list[str]
```

### Prompt sketches

**Rules extraction (Super):**
"You are given the text of a hackathon's overview and rules pages. Extract every concrete submission requirement and every judging criterion. Return JSON matching this schema: {schema}. Only include requirements stated in the text. Mark `checkable_from_repo` true only if it can be verified from a public GitHub repo."

**Per-file evidence (Nano):**
"Summarize this file for a hackathon judge. Return JSON: purpose (one sentence), models_used (exact model IDs found), apis_called (external services called at runtime), notable (up to 3 facts). Path: {path}. Content: {content}"

**Verdicts (Super):**
"Given hackathon requirements, deterministic repo facts, and per-file evidence, decide for each requirement: pass, fail, unclear, or not_checkable. Cite evidence by file path or fact. For fail/unclear, give one concrete fix. Deterministic facts override your judgment. Return JSON list matching {schema}."

**Scores (Ultra, P1):**
"Act as a judge for {hackathon}. Score the project 1–5 on each criterion using only the evidence provided. Be strict and specific. For each, give a 2-line rationale and the top 3 improvements achievable in under 2 hours. Similar existing projects: {tavily_results}. Return JSON matching {schema}."

### Implementation rules
- Every LLM call goes through `call_json(model, prompt, schema)`: temperature ~0.2, parse + validate, retry once with the error appended, otherwise return "unclear".
- License check uses GitHub's `license` field on the repo object. Never ask the LLM.
- File selection priority: README, files importing `openai` / `tavily` / `requests`, entry points (`app.py`, `main.py`, `index.*`), config files. Skip binaries, lockfiles, `node_modules`, files over 50 KB. Cap total at ~200 KB.
- Never execute code from the repo.
- Cache by `(repo commit SHA, hackathon URL)`.
- Per-session run cap (`MAX_RUNS_PER_SESSION`).
- Ship `examples/` with 2–3 cached reports so the demo works even if the API is slow.

---

## 7. Timeline (SGT)

| Time | Task | Done when |
|---|---|---|
| 5:45–6:15 PM | Accounts, credits, keys; repo with MIT license; first Nemotron call | One Nano, Super, and Ultra call each succeed |
| 6:15–7:30 PM | `config.py`, `llm.py`, `rules.py`, `repo.py` | Prints rules checklist + repo facts for this hackathon |
| 7:30–8:45 PM | `evidence.py`, `judge.py` (verdicts) | Pass/Fail/Unclear JSON for every requirement |
| 8:45–9:00 PM | Eat. **Cut-line check.** | |
| 9:00–9:45 PM | Streamlit report card + theme | Looks like a product, not a debug page |
| 9:45–10:15 PM | P1: Ultra scores, Tavily originality (skip if behind) | |
| 10:15–10:45 PM | Deploy to Streamlit Cloud; test on 3 repos (ShipCheck, broken demo repo, one from the project gallery) | Public URL works in an incognito window |
| 10:45–11:15 PM | README, Devpost write-up, tool feedback | |
| 11:15 PM–12:00 AM | Record + upload video (public, under 3 min) | |
| 12:00–12:30 AM | Submit; check every link logged out | Submitted |
| 12:30–1:00 AM | Buffer | |

---

## 8. Demo video shot list (under 3:00)

| Time | Shot |
|---|---|
| 0:00–0:20 | Hook: 29,561 people in this hackathon; many will lose points for things like a license GitHub can't see. ShipCheck catches it first. |
| 0:20–1:00 | Aha: run on the broken repo → red fails + fixes → add license → rerun → green. |
| 1:00–1:45 | How it works: pipeline diagram; Nano / Super / Ultra routing and why; Token Factory; Tavily Extract + Search. |
| 1:45–2:30 | Run on ShipCheck's own repo (and another hackathon URL if P1 is done). |
| 2:30–3:00 | Who it's for; what's next (GitHub Action, organizer pre-screening, more platforms). |

Prep: app already open, cached report ready, no copyrighted music, screen recorded at 1080p.

---

## 9. README template

```
# ShipCheck
One-liner. Demo link. Video link. Screenshot.

## What it does
## How it uses NVIDIA Nemotron + Nebius Token Factory
- Model routing table (Nano / Super / Ultra and why)
- Where Token Factory accelerated the workflow
## Tavily usage
## Architecture (diagram)
## Run locally
1. git clone ...
2. pip install -r requirements.txt
3. cp .env.example .env and fill in keys
4. streamlit run app.py
## Limitations
## License (MIT)
```

---

## 10. Devpost write-up skeleton

- **Inspiration:** started this hackathon with 8 hours left; wanted to know if the submission would pass before submitting.
- **What it does:** one-liner + shipped features.
- **How we built it:** pipeline, model routing, Token Factory, Tavily, GitHub API, Streamlit.
- **Challenges:** reliable structured JSON, large repos, JS-rendered rules pages.
- **Accomplishments:** ShipCheck passes its own check.
- **What we learned:** fill in honestly.
- **What's next:** GitHub Action, organizer bulk pre-screening, more hackathon platforms.
- **Built with:** python, streamlit, nebius-token-factory, nvidia-nemotron, tavily, github-api.

---

## 11. Tool feedback notes (fill in as you go)

For Token Factory, each Nemotron model, and Tavily:
- What I used it for:
- Time from signup to first successful call:
- What worked well:
- What needs work (name the exact page, feature, or error):
- Would I build with it again, and why:

Running log:
- 
- 

---

## 12. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Credits don't arrive / account blocked | Nebius Discord immediately; test in Playground meanwhile |
| A model ID is wrong or retired | Model IDs are env vars; swap in the catalog's ID |
| Ultra slow or expensive | Route scoring to Super; mention in feedback |
| Tavily can't extract the Devpost page | "Paste rules text" box (P0) |
| Flaky JSON | Low temperature, schema example in prompt, one retry, else "unclear" |
| Large repo timeout | Lower `MAX_FILES`; fall back to file tree + README |
| GitHub rate limit | Authenticated token (5,000 requests/hour) |
| Deploy breaks late | Submit with the video; note hosted-URL status in README |
| Credits run out during judging (Dec) | Caching, per-session cap, keep credits in reserve, cached examples |

---

## 13. Final submission checklist

- [ ] Track: Best Apps and Agents
- [ ] Demo URL works in a logged-out browser
- [ ] Repo public; MIT license visible in About
- [ ] README: setup/run steps, NVIDIA model usage, Token Factory, Tavily
- [ ] YouTube video public, under 3 minutes
- [ ] Description: what, why, how
- [ ] Tool feedback completed
- [ ] Tavily runtime call present (for the bonus)
- [ ] Submitted before 1:00 AM SGT