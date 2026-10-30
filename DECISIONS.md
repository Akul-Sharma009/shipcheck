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

## Core approach: deterministic checks + Nemotron routing (Nano/Super/Ultra)
Status: ASSUMED
Decision: as specified in BRIEF.md §6.
Evidence: none yet. The head-to-head at ~10:15 PM tests it against the baseline and a single-chatbot-call incumbent on about 3 labeled repos.
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

## Cost caps are best effort; the kill switch is the reliable control
Status: ASSUMED
Decision: a disk JSON result cache, a file-backed daily counter, a per-session cap, and `SHIPCHECK_LIVE=false` to serve only `examples/`.
Evidence: Streamlit Cloud reboots reset in-memory caches and local disk, so the counters can't be hard limits.
Revisit if: Token Factory offers a spend limit (then rely on it), or traffic during judging is higher than expected.

## Pinned dependencies
Status: ASSUMED
Decision: pin `requirements.txt` to the versions verified locally.
Evidence: Streamlit Cloud reinstalls the latest versions on reboot, and the demo must work until 23 Dec.
Evidence (30 Oct): every module imports under Python 3.11.17 with the pinned requirements (uvx).
Revisit if: a pinned version fails to install on Streamlit Cloud's Python 3.11.

## Open questions
- What does ShipCheck do concretely that SubmitGuard, Hackverify and the others don't? The demo must show it.
  - Research (30 Oct): AI Lakaton is the closest prior art. It extracts requirements from the rules, gives verdicts that cite a quote or path, deterministically checks that the cited text exists, and has a keyword fallback.
  - Gaps no tool documents:
    - GitHub's own license detection and repo facts (visibility, commit dates vs the event window)
    - per-event Devpost rules parsing that marks each item deterministic, LLM-judged or not checkable
    - any accuracy measured on a labeled set
- Which real gallery repo is the unbiased ground-truth case? For the eval, freeze one Rules extraction and score every method against that same requirement list.
- The brief's `Rules` schema has no `submission_start`, so "commits within submission period" needs it added. If it's absent, the check is unclear.
- Does the Token Factory console have a spend limit, or a way to turn off auto top-up? (The user is checking.)
