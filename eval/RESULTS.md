# Head-to-head evaluation (30 Oct 2026)

This is the setup defined in [GUARDRAILS.md](../GUARDRAILS.md). Every method was scored on the same data with the same metrics.

## Setup

- **Data:** 4 real entries to the Nebius x NVIDIA Global AI Hackathon, each pinned to a commit ([repos.txt](repos.txt)). ShipCheck's own repo is excluded, since it was built to pass.
- **Requirements:** 7 checkable-from-repo requirements from the hackathon's rules (R1, R2, R5–R9). We used one frozen extraction for every method.
- **Ground truth:** 28 pass/fail labels ([labels.json](labels.json)), 6 of them fails.
  - The labels came from an independent reviewer (a separate Claude Opus agent) that never saw ShipCheck's code or outputs.
  - It read the repos at the pinned commits through the GitHub API.
  - 27 of 28 labels are high-confidence.

**The methods:**

| Method | What it is |
|---|---|
| **ShipCheck** | The full pipeline: deterministic checks, per-file Nano evidence, Super verdicts, grounding. |
| **Keyword baseline** | The dumb baseline: a LICENSE file exists, the README mentions install/run, the repo text names the platform/model. No AI. ([shipcheck/baseline.py](../shipcheck/baseline.py)) |
| **One model call** | The incumbent ("paste it into a chatbot"). The same Nemotron Super model gets the requirements, file list, README and up to 60K characters of source in one call. We ran it two ways: with GitHub's detected-license field in the prompt (generous) and without it (realistic). |

## Results

| Method | Accuracy | Macro-F1 | **False-pass rate** (of 6 true fails) | Unclear |
|---|---|---|---|---|
| **ShipCheck** | **100%** (28/28) | **1.00** | **0%** | 0% |
| One model call, without license field | 89% (25/28) | 0.86 | 0% | 0% |
| One model call, given GitHub's license field | 96% (27/28) | 0.95 | 0% | 0% |
| Keyword baseline | 82% (23/28) | 0.85 | **17%** (1/6) | 14% |

"Unclear" counts as wrong for accuracy and F1. The false-pass rate is the share of truly failing requirements reported as PASS: the error that gets entrants disqualified.

## What the errors were

- **Keyword baseline:**
  - **False pass on the license.** One entry has a LICENSE file with truncated MIT text. GitHub can't identify it (`NOASSERTION`), so no license shows in the About section and the requirement fails. "Is there a LICENSE file?" says PASS. ShipCheck uses GitHub's own detection and says FAIL.
  - It also can't judge "contains all necessary code and instructions" at all (4 unclear).
- **One model call:**
  - Without the license field, it failed a correctly licensed repo, because the LICENSE file wasn't in the pasted text.
  - It failed a repo's README setup instructions and completeness, which the reviewer passed.
  - With the license field, the README miss remained.

## Read this with care

- **The sample is small:** 4 repos, 28 labels and 6 true fails. ShipCheck vs a single strong-model call is a difference of 1–3 items. That's evidence ShipCheck is at least as good and makes fewer errors of both kinds. It isn't proof of a large margin.
- **The ground truth comes from one AI reviewer** working blind. The one low-confidence label (whether a README "highlights" Token Factory usage) could go either way.
- **One repo isn't fully untuned:** the ShipCheck builder spot-checked tradeflow earlier the same day while fixing file selection. The other three were never seen before the eval.
- **Each method ran once.** LLM outputs vary between runs.

Beyond accuracy, ShipCheck also cites `path:line` evidence and gives a fix for each failure. The single call returns verdicts only.

## Reproduce

```bash
python -m eval.run_eval eval/labels.json eval/repos.txt
```

Raw predictions: [predictions.json](predictions.json).
