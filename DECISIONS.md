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
Status: ASSUMED (pending smoke test)
Decision: send `chat_template_kwargs.enable_thinking=false` to Nano if Token Factory accepts it.
Evidence: reasoning tokens consume max_tokens and cost money; file summaries don't need reasoning.
Revisit if: the smoke test shows it's rejected or ignored, or output quality drops.

## Cost caps are best effort; the kill switch is the reliable control
Status: ASSUMED
Decision: a disk JSON result cache, a file-backed daily counter, a per-session cap, and `SHIPCHECK_LIVE=false` to serve only `examples/`.
Evidence: Streamlit Cloud reboots reset in-memory caches and local disk, so the counters can't be hard limits.
Revisit if: Token Factory offers a spend limit (then rely on it), or traffic during judging is higher than expected.

## Pinned dependencies
Status: ASSUMED
Decision: pin `requirements.txt` to the versions verified locally.
Evidence: Streamlit Cloud reinstalls the latest versions on reboot, and the demo must work until 23 Dec.
Revisit if: a pinned version fails to install on Streamlit Cloud's Python 3.11.

## Open questions
- What does ShipCheck do concretely that SubmitGuard, Hackverify and the others don't? The demo must show it.
- Which real gallery repo is the unbiased ground-truth case?
- The brief's `Rules` schema has no `submission_start`, so "commits within submission period" needs it added. If it's absent, the check is unclear.
- Does the Token Factory console have a spend limit, or a way to turn off auto top-up? (The user is checking.)
