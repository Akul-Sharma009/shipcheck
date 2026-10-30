# Guardrails: ShipCheck

Read this with the brief. It defines what any solution will be measured against.
It deliberately contains no solution approaches.

## Problem
Hackathon entrants lose points or get disqualified for avoidable compliance gaps:
- a license that GitHub doesn't detect
- a README with no setup steps
- required platform or model usage that is never called out
- a project that misses the track's goal

Rules pages are long, and nobody rereads them in the final hours.

## Incumbent
- **Manual.** The entrant rereads the event's rules page, or pastes the rules and README into a general chatbot.
- **No official Devpost validator.** Devpost publishes per-event rules only. Its MCP server exposes submission requirements to agents.
- **Prior art.** Small AI checkers exist: SubmitGuard, a hackathon-submission-gate skill, Hackverify, AI Lakaton, JudgeLens, hackanalyzer, gitcheck.

## Dumb baseline
Keyword and file rules:
- License passes if a `LICENSE*` file exists.
- "README has setup" passes if the README contains install / run / setup.
- "Uses X" passes if the repo text contains the platform or model name.
- Anything else is "unclear".

## Metrics
- **Recognized:** per-requirement classification accuracy and macro-F1, against hand-labeled ground truth. The rubric names no metric.
- **Failure cost:** false-pass rate, the share of truly failing requirements reported as PASS. A false pass gets an entrant disqualified while they believe they're fine. A false fail only costs minutes.
- **Timeliness:** n/a.

Head-to-head rule: the incumbent ("one chatbot call" with rules + README), the baseline and the solution are scored on the same repo × hackathon pairs with the same metrics.

## Known traps
- **Prior art vs "Quality of the Idea".** Similar checkers exist. The difference has to be concrete and shown in the demo.
- **Biased test set.** A repo built to pass, or one built to fail, is a biased sample. Ground truth needs at least one real gallery repo that nobody tuned for.
- **License detection.** "License detected by GitHub" is not the same as "LICENSE file exists".
- **Non-checkable requirements.** Video, feedback and description can't be verified from a repo. Exclude them from accuracy; don't count them as errors.
- **No composite score.** Don't invent a readiness score. Report counts.
- **Cost through judging.** The demo must keep working, within cost, until 23 Dec 2026 with a card attached.

## Domain research prompt
> How do hackathon organizers and judges currently screen submissions for rule compliance (eligibility, required tech usage, license, README, video) on Devpost and similar platforms? How do existing AI submission checkers (e.g. SubmitGuard, Hackverify, AI Lakaton, hackathon-submission-gate) work: deterministic checks vs LLM, what they verify, how they cite evidence, and any reported accuracy or failure modes? Which compliance failures most often get submissions disqualified? Summarize in under 300 words, with links.

## Sources
- https://hackquest.io/projects/SubmitGuard
- https://www.agensi.io/skills/hackathon-submission-gate
- https://hackverify.vercel.app/
- https://lablab.ai/submissions/fbwbfxcxgy9j8rsdk2168w61
- https://github.com/JVikramV/JudgeLens
- https://github.com/angeblecon/hackanalyzer
- https://devpost.com/software/gitcheck
- https://www.mcpbundles.com/skills/devpost-mcp-1e5cf31d8c
