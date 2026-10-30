# Head-to-head evaluation (30 Oct 2026)

This is the setup defined in [GUARDRAILS.md](../GUARDRAILS.md). Every method was scored on the same data with the same metrics.

## Setup

- **Data:** 9 real entries to the Nebius x NVIDIA Global AI Hackathon, each pinned to a commit ([repos.txt](repos.txt)). ShipCheck's own repo and the deliberately broken demo repo are excluded.
- **Requirements:** 7 checkable-from-repo requirements from the hackathon's rules (R1, R2, R5–R9). We used one frozen extraction for every method.
- **Ground truth:** 63 pass/fail labels ([labels.json](labels.json)), 10 of them fails.
  - The labels came from independent reviewers (separate Claude Opus agents) that never saw ShipCheck's code or outputs. They read the repos at the pinned commits through the GitHub API only.
  - 55 of 63 labels are high-confidence. The 8 low-confidence ones are judgment calls such as "does the README *highlight* Token Factory usage" or "is the repo complete enough to run".
  - The set was built in two batches: 4 repos (28 labels) first, then 5 more (35 labels) found and labeled blind later the same day. Labels were never edited after the reviewer wrote them.

**The methods:**

| Method | What it is |
|---|---|
| **ShipCheck** | The full pipeline: deterministic checks, per-file Nano evidence, Super verdicts, grounding, code-usage check. |
| **Keyword baseline** | The dumb baseline: a LICENSE file exists, the README mentions install/run, the repo text names the platform/model. No AI. ([shipcheck/baseline.py](../shipcheck/baseline.py)) |
| **One model call** | The incumbent ("paste it into a chatbot"). The same Nemotron Super model gets the requirements, file list, README and up to 60K characters of source in one call, plus GitHub's detected-license field (generous). |
| **One model call, no license field** | The same, without the license field: what a pasted repo realistically gives a chatbot. |

## Results (final run, the code as shipped)

| Method | Accuracy | Macro-F1 | **False-pass rate** (of 10 true fails) | Unclear | High-confidence labels only |
|---|---|---|---|---|---|
| **ShipCheck** | **92%** (58/63) | **0.90** | 20% (2/10) | 3% | **100%** (55/55), 0 false passes |
| One model call | 90% (57/63) | 0.84 | **10%** (1/10) | 2% | 95% (52/55), 0 false passes |
| One model call, no license field | 79% (50/63) | 0.72 | 20% (2/10) | 2% | 82% (45/55), 0 false passes |
| Keyword baseline | 81% (51/63) | 0.78 | 30% (3/10) | 14% | 85% (47/55), 1 false pass |

"Unclear" counts as wrong for accuracy and F1. The false-pass rate is the share of truly failing requirements reported as PASS: the error that gets entrants disqualified.

**What this shows:**
- ShipCheck is the most accurate method, and on the 55 labels the reviewer was confident about it made no errors at all.
- Every ShipCheck error is on a low-confidence label.
- **ShipCheck does not beat a single model call on false passes across all labels.** Both false passes ShipCheck made are on one weak repo's two judgment-call labels (nemoforge R6 and R9). Between our two runs, ShipCheck and the single call each scored 10% and 20%. With 10 true fails, one item is 10 points: the difference is noise.
- The keyword baseline's false passes include a real entry with a truncated MIT license (GitHub can't identify it, so the rules count it as unlicensed) and two README "highlights Token Factory" requirements it passed on keywords alone.

## Two runs, and what changed between them

The first run on the expanded set exposed two ShipCheck bugs. Both were fixed and the whole eval was rerun.

| | Accuracy | Macro-F1 | False-pass rate | High-confidence |
|---|---|---|---|---|
| ShipCheck, run 1 (before fixes) | 94% (59/63) | 0.91 | 10% (1/10) | 98% (54/55) |
| ShipCheck, run 2 (shipped) | 92% (58/63) | 0.90 | 20% (2/10) | 100% (55/55) |

- **Fixed: a bare `## Run` README heading wasn't recognised as setup instructions** (nemoforge R8, a wrong FAIL). The heading regex now accepts it.
- **Fixed: a correct pass could be downgraded to "unclear" when the Nano summary of the cited file failed** (akashkolte R2, the one high-confidence error in run 1). Files with grep hits now count as files ShipCheck read.
- Run 2's overall numbers are slightly lower because of run-to-run variance on the low-confidence labels (README "highlights", repo completeness), not because of the fixes: the two fixed items are correct in run 2.

## ShipCheck's errors in the final run

| Repo | Req | ShipCheck | Reviewer (confidence) | Why |
|---|---|---|---|---|
| nemoforge | R6 complete repo | pass | fail (low) | The reviewer failed it because its model IDs (`nvidia/nemotron-ultra`) aren't real Token Factory IDs, so the code wouldn't run. ShipCheck doesn't validate model IDs against the catalogue. |
| nemoforge | R9 README highlights usage | pass | fail (low) | The README names the models and "Built With Nebius Token Factory" but doesn't say how it accelerated the work. A judgment call. |
| LightTry | R6 complete repo | fail | pass (low) | The README says weights and sample photos aren't bundled. ShipCheck read that as incomplete. |
| docpilot | R9 | unclear | pass (low) | Judgment call on "highlight". |
| akashkolte | R9 | unclear | pass (low) | Same. |

## Read this with care

- **The sample is still small:** 9 repos, 63 labels, 10 true fails. One item moves the false-pass rate by 10 points.
- **The ground truth comes from AI reviewers** working blind, not human judges.
- **Two repos aren't fully unseen:** the ShipCheck builder spot-checked tradeflow earlier while fixing file selection, and the two fixes above came from errors on nemoforge and akashkolte in run 1. The other repos' results weren't used to change ShipCheck.
- **LLM outputs vary between runs,** for every method except the keyword baseline.

Beyond accuracy, ShipCheck also cites `path:line` evidence and gives a fix for each failure. The single call returns verdicts only.

## Reproduce

```bash
python -m eval.run_eval eval/labels.json eval/repos.txt
```

Raw predictions from the final run: [predictions.json](predictions.json).
