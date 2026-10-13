# Assignment rubric -> where each line is satisfied (70 points)

Source: "DSO 429 Project 1 Benchmarking Final Deliverable.pdf". Status as of 2026-10-12, before the real run.
DONE = built and tested offline. RUN = needs the OpenRouter key. TEAM = needs a human.

## Implementation and reproducibility (15)
| Line | Pts | Where | Status |
|---|---|---|---|
| Every deviation named with its reason | 4 | `DEVIATIONS.md` (16 rows) | DONE, **team must confirm defaults** |
| Run conditions: exact model IDs, run dates, runs per item, context given | 4 | `README.md` table + `results/final/run_manifest.json` (written by `analyze`) | DONE |
| Archive holds eval set + held-out split, grader, output sample, README | 4 | `bench.py package` -> `slogan-benchmark-archive.zip` | DONE after RUN |
| Another team can re-run from README | 3 | `README.md` (1 page), stdlib-only runner, `selftest` | DONE |

## Results (15)
| Line | Pts | Where | Status |
|---|---|---|---|
| Same items and conditions for every model; more than one run per item | 3 | n = 5 runs, identical prompt; T1 coverage note | RUN |
| Headline numbers carry a spread; models within noise not ranked | 4 | T1 (mean ± SD [min–max], CI, rank letters), T6 | RUN |
| Criteria separate, not one score | 2 | T1, T2, T5 (no composite exists anywhere) | RUN |
| Edge cases broken out from normal cases | 2 | T3, T3b, fig2 | RUN |
| At least one labelled figure with units | 2 | fig1-fig5 (checked visually on mock data) | RUN |
| Median latency per call and total $ of full run, per model | 2 | T4, fig3 | RUN |

## Analysis and interpretation (20)
| Line | Pts | Where | Status |
|---|---|---|---|
| Results against the acceptable-failure line; decision changed is named | 4 | T1 "Clears the line?" + margin; fig1. **The "decision" sentence is yours to write.** | RUN + TEAM |
| Failure classified model-wrong vs missing-input, with evidence | 5 | T7 (mode, whose fault), T8 (sparse -> rich counterfactual) | RUN |
| Instrument questioned: a P4 weakness that bit; a score your reading disputes | 5 | `disputes.md` (A-D), T9a, T5 contamination, human `audit/` sheet. **A disputed score needs a human reading.** | RUN + TEAM |
| Contamination and construct mismatch addressed directly | 3 | T5 (memorisation), fig4; construct: originality != persuasiveness, say so in report | RUN + TEAM |
| Judge self-preference check reported | 3 | T9b, fig5 | RUN |

## Report (10) and Presentation (10)
Report <= 3 pages + 2 appendix pages, four sections, claims not summaries; deck <= 6 slides in the order task ->
instrument -> (15 s "call it" card) -> results -> interpretation, then one "break it" line from other teams.
Appendices: item sample (`items.csv`), judge rubric (`prompts/judge.txt`), full results (T10), cost accounting (T4).
Not started: waits for real numbers.

## Submission checklist (from the PDF)
deck (.pptx/.pdf) · report (.pdf) · eval set with held-out marked (`data/items.json`) · grader/judge prompt (in archive) ·
raw outputs >= 10 per model (all of them are in `raw/`) · README ≤ 1 page · peer input forms (posted after submission).
