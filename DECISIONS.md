# Decisions

ASSUMED = not yet tested against alternatives. Treat it as an open question.
TESTED = won a head-to-head comparison, with the evidence recorded below.

## Planning framework: Superpowers, skipping brainstorming
Status: ASSUMED
Decision: Superpowers, enabled per project. Its brainstorming step is skipped because BRIEF.md is the approved design.
Evidence: project-kickoff classified this as Small (under 3 days, solo, about 6 hours of build time).
Revisit if: the workflow slows the build more than it helps.

## Primary metric: accuracy / macro-F1, plus false-pass rate
Status: ASSUMED
Decision: score per-requirement verdicts against hand labels. A false pass is the costly error.
Evidence: the rubric names no metric; this is the standard choice for a classification task. See GUARDRAILS.md.
Revisit if: judges or the rules name a different measure.

## Dumb baseline: keyword and file rules
Status: ASSUMED
Decision: as defined in GUARDRAILS.md.
Evidence: it's the simplest thing a non-expert would build.
Revisit if: it scores about the same as ShipCheck. That would mean the LLM adds little.

## Core approach: deterministic checks + Nemotron routing (Nano/Super, Ultra cut)
Status: TESTED (small sample)
Decision: as specified in BRIEF.md §6.
Evidence: eval/RESULTS.md, 30 Oct. 4 real entries, 28 blind labels (6 fails). ShipCheck: 100% accuracy, 0% false passes. A single Super call: 89% (96% if given GitHub's license field). Keyword baseline: 82% with a 17% false-pass rate (a truncated MIT license).
Revisit if: the single-call incumbent matches it on false-pass rate.

## Structured output: prompt-based JSON + Pydantic validation + one retry
Status: ASSUMED
Decision: no `response_format` / guided JSON. The schema goes in the prompt, then the output is parsed, validated, and retried once with the error.
Evidence: in pre-flight, Nano and Super both returned valid JSON from prompt instructions alone.
Revisit if: parse or validation failures show up in more than a few calls per run.

## Nano reasoning off for per-file extraction
Status: TESTED (cost/latency only; quality not yet compared on real files)
Decision: send `chat_template_kwargs.enable_thinking=false` to Nano (`NANO_DISABLE_THINKING`, default true).
Evidence: smoke test 30 Oct, same prompt with valid JSON both ways: 227 completion tokens in 6.4 s with thinking on, 25 tokens in 3.7 s with it off.
Revisit if: per-file evidence misses model or API usage that a thinking-on run catches.

## Super thinking off for rules extraction
Status: TESTED (one hackathon; cost/latency plus a manual read of the output)
Decision: `RULES_THINKING=false`; send `enable_thinking=false` for rules → Rules.
Evidence: 30 Oct, same 40K-char page text. Thinking off: 11 s, 2.5K output tokens, 16 requirements, correct dates. Thinking on: 69 s, 14.3K tokens, 19 requirements; the 3 extra were legal terms the prompt says to skip.
Revisit if: rules for another hackathon miss requirements that thinking-on catches.

## Rules are cached per hackathon URL
Status: ASSUMED
Decision: extract rules once per hackathon URL, then reuse them across repos and reruns (in guard.py).
Evidence: three extractions of the same page gave 16, 17 and 19 requirements. Reruns of the demo must not change the checklist (the "add license, rerun, goes green" moment). Caching also saves about 10 s and one Super call per run.
Revisit if: rules pages change during a hackathon (add a TTL).

## Private repos are refused, never ingested
Status: ASSUMED
Decision: if GitHub reports the repo as private, stop before reading any contents.
Evidence: the server's GITHUB_TOKEN may be able to read the owner's private repos. Without this check, any visitor could make the public app summarize them.
Revisit if: never. Also use a fine-grained token limited to public repositories.

## Evidence is grounded deterministically; unverifiable passes are downgraded
Status: TESTED (spot check on 2 real entries, not yet the labeled eval)
Decision: (1) A model ID or service in Nano's per-file evidence is kept only if its brand word appears in that file. (2) A PASS from Super must cite a file ShipCheck actually read, or a check id; otherwise it becomes UNCLEAR. (3) Deterministic checks override: a linked failing check (D1/D2/D4) fails the requirement; D2 decides license both ways; D1 decides "provide a public repo URL". (4) Platform/model usage needs code evidence, not a README claim.
Evidence: 30 Oct, Fu93/tradeflow-ai. Nano copied the prompt's example services into most files, e.g. "Nebius Token Factory" listed for requirements.txt. After grounding, R1/R2 cite src/config/heuristics.py:519 (Token Factory base URL) and :526 (Nemotron model ID), both checked by hand.
Revisit if: the labeled eval shows grounding drops true evidence (more false "unclear").

## File selection: wide pool, then rank by content
Status: TESTED (one repo)
Decision: read up to 4×MAX_FILES candidates by path rank. Keep files that name a platform/model first, then API-calling files, counting each file's truncated size (12K chars) against the 200 KB budget.
Evidence: tradeflow-ai (600 files). The old selection missed src/engine/llm_config.py and picked 18 files; the new one picks 26, including both LLM config files, in 3 s.
Revisit if: a repo's LLM code is still missed, or GitHub raw fetches get rate-limited.

## Cost caps are best effort; the kill switch is the reliable control
Status: ASSUMED
Decision: a disk JSON result cache, a file-backed daily counter, a per-session cap, and `SHIPCHECK_LIVE=false` to serve only `examples/`.
Evidence: Streamlit Cloud reboots reset in-memory caches and local disk, so the counters can't be hard limits.
Revisit if: Token Factory offers a spend limit (then rely on it), or traffic during judging is higher than expected.

## Daily cap 30 uncached runs; survive an expired GitHub token
Status: ASSUMED
Decision: MAX_UNCACHED_RUNS_PER_DAY defaults to 30 (was 100). On a 401 from GitHub, drop the token and continue unauthenticated; raw file fetches never send the token.
Evidence: 30 Oct. The balance is S$27.15 and Token Factory has no spend cap. The GitHub token expires 29 Nov, before judging (9–23 Dec). Unauthenticated is 60 API requests/hour, about 7 runs/hour; tested with a bogus token.
Revisit if: real per-run cost (check the console after a few runs) is far below about $0.05, or judging traffic hits the cap.

## Repo checks follow the hackathon's rules
Status: TESTED (PayPal AI, Codegeist, Nebius rules)
Decision: D1/D2/D3/D4 count only if a requirement links to them; otherwise they're shown as INFO. D5 (submission window) always counts.
Evidence: Codegeist doesn't require a license. Before this, a missing license would have topped "Fix these first" for a hackathon that never asked for one.
Revisit if: a hackathon states a requirement the keyword linking misses.

## Devpost submission check: video by YouTube metadata, write-up by Super with verified quotes
Status: TESTED (one live run + offline tests)
Decision:
- V1 (public, plays logged out) and V2 (under the rules' stated limit) come from the YouTube watch page, with no API key.
- Each check decides only the requirements it covers (visibility/link vs a stated time limit).
- The write-up is judged by Super, in parallel with the repo verdicts. A pass needs a quote found verbatim in the text.
- Form-field requirements (track/category selection) are skipped deterministically.
Evidence: the first live run failed 7 video requirements from one length failure, and Super failed "identify your track" despite the prompt. Both are fixed and re-tested offline.
Revisit if: YouTube changes its page markup (V1 then comes back "unclear", not a false pass).

## Pinned dependencies
Status: ASSUMED
Decision: pin `requirements.txt` to the versions verified locally.
Evidence: Streamlit Cloud reinstalls the latest versions on reboot, and the demo must work until 23 Dec.
Evidence (30 Oct): every module imports under Python 3.11.17 with the pinned requirements (uvx).
Revisit if: a pinned version fails to install on Streamlit Cloud's Python 3.11.

## Bundled rules for this hackathon; example report on first load
Status: ASSUMED
Decision: ship examples/rules/rules_<key>.json (this hackathon's extracted rules, 30 Oct) and examples/*.json reports. The landing page shows an example with zero API calls.
Evidence: red-team (9 PM). The Devpost page may change or close after the deadline, and judging runs 9–23 Dec. The bundled rules also make reruns consistent and save one Super call (a run is 27 s instead of 37 s).
Revisit if: the rules page changes materially before the deadline.

## Cut P1 (Ultra scores, Tavily originality, README generator)
Status: DECIDED by the user, 30 Oct ~9:20 PM
Decision: spend the remaining time on deploy, the 3-repo eval, README, video and submission instead of P1.
Evidence: red-team. Ultra criterion scores invite the "invented score" trap. Tavily Extract is already a runtime call, so the bonus doesn't need originality search. Design and evidence matter more than another feature.
Revisit if: everything else is done before 11 PM.

## A README claim can't pass a usage requirement
Status: TESTED (30 Oct 9:16 PM)
Decision: after the model's verdict, a deterministic check (`judge.check_usage`) looks for usage in code and config only: NVIDIA model IDs (`nvidia/...`, `nemotron-...`) and Nebius endpoints (`tokenfactory`, `nebius.com`, `NEBIUS_API_KEY`). If none is found and the code names another provider (e.g. `gpt-4o-mini`), "uses NVIDIA model", "runs on Token Factory" and "README must highlight..." become FAIL, citing that line. With no signal either way, a pass becomes unclear.
Evidence: on the demo repo, the model returned R1/R2 as unclear and the README-highlight requirement as a false PASS, although app.py calls gpt-4o-mini. Eval rerun with the change: ShipCheck unchanged at 28/28, 0% false passes; every prediction identical to before.
Revisit if: an eval repo that sets its model only through an env var not in any selected file gets downgraded.

## Open questions
- Demo lead (red-team): a LICENSE with modified MIT text. GitHub reports NOASSERTION, so the About panel shows no license, while a keyword check or a chatbot would say PASS. Needs a small public demo repo; pre-record the rerun, because GitHub's license detection can lag after a push.
- What does ShipCheck do concretely that SubmitGuard, Hackverify and the others don't? The demo must show it.
  - Research (30 Oct): AI Lakaton is the closest prior art. It extracts requirements from the rules, gives verdicts that cite a quote or path, deterministically checks that the cited text exists, and has a keyword fallback.
  - Gaps no tool documents:
    - GitHub's own license detection and repo facts (visibility, commit dates vs the event window)
    - per-event Devpost rules parsing that marks each item deterministic, LLM-judged or not checkable
    - any accuracy measured on a labeled set
- Ground truth (resolved 30 Oct): 3 never-seen entries plus tradeflow, labeled blind by an Opus agent. The user hasn't spot-checked the labels.
- The brief's `Rules` schema has no `submission_start`, so "commits within submission period" needs it added. If it's absent, the check is unclear.
- Token Factory has no spend cap (user checked 30 Oct). The kill switch and daily cap are the only controls.
