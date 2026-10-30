"""ShipCheck pre-flight: verifies keys, credits, model IDs, JSON output, Tavily, GitHub."""
import json, os, time
from dotenv import load_dotenv
import requests
from openai import OpenAI, APIStatusError, APIConnectionError

load_dotenv()
RESULTS = []

def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {('- ' + detail) if detail else ''}")

def env(name):
    v = os.getenv(name)
    record(f"env {name}", bool(v), "" if v else "missing in .env")
    return v

# ---------- env ----------
NEBIUS_KEY = env("NEBIUS_API_KEY")
TAVILY_KEY = env("TAVILY_API_KEY")
GH_TOKEN = env("GITHUB_TOKEN")
MODELS = {k: os.getenv(f"MODEL_{k}") for k in ("NANO", "SUPER", "ULTRA")}

# ---------- Token Factory ----------
client = OpenAI(base_url="https://api.tokenfactory.nebius.com/v1/", api_key=NEBIUS_KEY or "x")

catalog = set()
try:
    catalog = {m.id for m in client.models.list().data}
    record("Token Factory: list models (auth OK)", True, f"{len(catalog)} models available")
    nemotrons = sorted(m for m in catalog if "nemotron" in m.lower())
    print("    Nemotron models in catalog:\n      " + "\n      ".join(nemotrons or ["(none found)"]))
except APIStatusError as e:
    record("Token Factory: list models", False, f"HTTP {e.status_code}: {e.message}")
except APIConnectionError as e:
    record("Token Factory: list models", False, f"connection error: {e}")

def try_model(tier, model_id):
    if not model_id:
        record(f"{tier}: configured", False, "MODEL_" + tier + " not set"); return
    if catalog and model_id not in catalog:
        record(f"{tier}: model ID exists", False, f"'{model_id}' not in catalog (see list above)"); return
    # plain call
    try:
        t = time.time()
        r = client.chat.completions.create(
            model=model_id, max_tokens=800, temperature=0.2,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}])
        dt = time.time() - t
        text = (r.choices[0].message.content or "").strip()
        u = r.usage
        record(f"{tier}: chat call", bool(text), f"{dt:.1f}s, reply={text[:40]!r}, "
               f"tokens in/out={getattr(u,'prompt_tokens','?')}/{getattr(u,'completion_tokens','?')}"
               + ("" if text else " (empty content: raise max_tokens, model may be spending it on reasoning)"))
    except APIStatusError as e:
        hint = " <- likely NO CREDITS / billing issue" if e.status_code in (402, 403, 429) else ""
        record(f"{tier}: chat call", False, f"HTTP {e.status_code}: {e.message}{hint}"); return
    # JSON call
    raw = ""
    try:
        r = client.chat.completions.create(
            model=model_id, max_tokens=800, temperature=0.2,
            messages=[{"role": "user", "content":
                'Return ONLY a JSON object, no prose, no code fences: '
                '{"status": "pass" or "fail", "reason": "<short string>"} '
                'for this check: "Repo has an MIT license file."'}])
        raw = (r.choices[0].message.content or "").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        obj = json.loads(raw)
        record(f"{tier}: JSON output", "status" in obj, raw[:80])
    except json.JSONDecodeError:
        record(f"{tier}: JSON output", False, f"not valid JSON: {raw[:120]!r}")
    except APIStatusError as e:
        record(f"{tier}: JSON output", False, f"HTTP {e.status_code}: {e.message}")

for tier, mid in MODELS.items():
    try_model(tier, mid)

# ---------- Tavily ----------
try:
    from tavily import TavilyClient
    tv = TavilyClient(api_key=TAVILY_KEY)
    rules_url = "https://nebiusglobalaihackathon.devpost.com/rules"
    ex = tv.extract(urls=[rules_url])
    got = ex.get("results", [])
    chars = len(got[0].get("raw_content", "")) if got else 0
    record("Tavily: extract Devpost rules page", chars > 2000,
           f"{chars} chars extracted" + ("" if chars > 2000 else " (too little: rely on paste-rules fallback)"))
    if got:
        print("    Snippet:", got[0]["raw_content"][:200].replace("\n", " "), "...")
    s = tv.search(query="devpost hackathon submission checker tool", max_results=3)
    record("Tavily: search", bool(s.get("results")), f"{len(s.get('results', []))} results")
except Exception as e:
    record("Tavily", False, f"{type(e).__name__}: {e}")

# ---------- GitHub ----------
try:
    h = {"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"}
    rl = requests.get("https://api.github.com/rate_limit", headers=h, timeout=15).json()
    core = rl["resources"]["core"]
    record("GitHub: token auth", core["limit"] >= 5000, f"rate limit {core['remaining']}/{core['limit']}")
    repo = requests.get("https://api.github.com/repos/streamlit/streamlit", headers=h, timeout=15).json()
    lic = (repo.get("license") or {}).get("spdx_id")
    record("GitHub: repo + license detection", bool(lic), f"streamlit/streamlit license={lic}")
except Exception as e:
    record("GitHub", False, f"{type(e).__name__}: {e}")

# ---------- summary ----------
fails = [r for r in RESULTS if not r[1]]
print("\n" + "=" * 60)
print(f"{len(RESULTS) - len(fails)}/{len(RESULTS)} checks passed")
for name, _, detail in fails:
    print(f"  FAIL  {name}: {detail}")
print("READY TO BUILD" if not fails else "Fix the failures above before building.")