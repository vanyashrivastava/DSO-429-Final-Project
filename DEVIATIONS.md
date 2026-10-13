# Deviations from the Phase 1 proposal (joke creativity / mode collapse)

DRAFT for the team to confirm. Each row is a change from what the proposal (presented Sep 22) said we would do,
and why. Only the pivot to slogans and the 50 companies were stated by the team; every other row is a default I
chose while building and needs a yes or a change from the team before the freeze.

| # | Proposal said | Built | Reason | Status |
|---|---|---|---|---|
| 1 | Benchmark creativity of short jokes | Benchmark ad **slogan** generation from a company brief | Pivot after professor feedback | you asked |
| 2 | 3 prompting conditions: Direct, List, Verbalized Sampling; tests whether VS beats List | **One** condition (one slogan per call); the VS hypothesis and its "VS is beneficial" thresholds are retired | The question became a model-vs-model comparison; 3 conditions x 5 models x 5 runs was not feasible before the deadline | my default, **confirm** |
| 3 | 60 prompts (30 everyday / 20 contextual / 10 stress), 20 outputs per prompt per condition | **50** companies (28 standard / 12 contextual / 10 stress), **5** runs per item per model | 50 companies requested for the new domain; 5 independent runs give a run-to-run SD as the assignment requires | 50 companies: you asked; 5 runs and the tier split: my default, **confirm** |
| 4 | GPT-4.1, GPT-4.1 mini, Gemini 3.5 Flash | Claude Sonnet 5.5, Gemini 3.8 Flash, GPT-6.1 Sol, **Mistral Large 4**, DeepSeek V4.1 Flash | Current models on OpenRouter at run time; 5 families and a price range from $0.04 to $2 per M input tokens. Mistral replaced Muse Spark 1.3 (your call) because Muse is gated behind an 18+ account confirmation | my default, **confirm** |
| 5 | Judge `claude-sonnet-5`, never a generator | Primary judge `x-ai/grok-4.7`; `claude-opus-5.5` as a probe judge for self-preference only | Sonnet 5.5 is now a generator, so keeping "judge is never a generator" and "no judge shares a family with a generator" needs a different primary; the probe makes the self-preference check measurable | my default, **confirm** |
| 6 | Validity = coherent, relevant, complies | Adds **faithful** (no unsupported factual claim) and deterministic programmatic checks (single line, word limit, required/banned phrases) | Slogans about real companies can fabricate facts; constraints are checkable without a judge, which also audits the judge | my default, **confirm** |
| 7 | Originality anchors for jokes | Anchors rewritten for slogans (`prompts/judge.txt`); scale and thresholds unchanged | Same construct, new domain | my default, **confirm** |
| 8 | Acceptable-failure line: >=95% valid, originality >=3/5, >=90% on required details | **Unchanged**, applied to slogans | Re-tuning the line after seeing slogan scores would be moving the goalposts | my default, **confirm** |
| 9 | Ideas grouped by strict pairwise premise-and-punchline test over 20 jokes | The judge partitions the (up to 5) valid slogans of a (model, item) into idea groups | Only 5 outputs per item now | my default, **confirm** |
| 10 | Human audit: 2 blinded raters, 10% of outputs + 200 duplicate-pair decisions | ~60-output blinded sheet (`bench.py audit`) plus a `disputes.md` of judge-vs-rule and judge-vs-judge conflicts | Scale and time. **Status: sheet is built; raters have not filled it in yet** | **to do** |
| 11 | One concurrent request, temperature 0.7, top_p 1.0 "where supported" | 6 concurrent requests, randomised interleaved order; sampling parameters sent only where the model accepts them | Deadline; per OpenRouter's listing, Sonnet 5.5 accepts no temperature/top_p/seed and GPT-6.1 Sol accepts no temperature/top_p | disclosed |
| 12 | 40-word limit per joke | 10-word default per slogan, item-level overrides in contextual items | Slogan length | my default, **confirm** |
| 13 | Bootstrap resamples whole prompts | Resamples whole items; **adds** run-to-run SD and a paired ranking rule | Assignment: "one run is not a measurement" | my default, **confirm** |
| 14 | No held-out split | 12 dev items (pilot only) and 38 held-out items; headline numbers use held-out | Assignment D3 requires a marked held-out split | my default, **confirm** |
| 15 | Contamination handled by "fresh contextual details" | Measured: known real slogans per company, judge recognition, and contextual items that ban the company's own slogan | Famous companies make memorisation likely and testable | my default, **confirm** |
| 16 | Hidden reasoning not discussed | Reasoning effort fixed to "low" and excluded from the returned text | Hidden reasoning tokens change cost and latency; held at the same setting where accepted | my default, **confirm** |

## Things that are not deviations but should be said out loud
- The 50 companies were chosen for recognisability and sector coverage, **not** drawn from a published ranking.
  Descriptions were written fresh and kept evergreen (no figures or recent events); known slogans come from general
  knowledge and should be skimmed by the team.
- Items marked stress-subtype have 2-3 items each; they are anecdotes, not estimates.
- Dev-split pilot outputs may be used to fix prompt wording or parsing before the freeze; any such change is listed
  below and the final run uses only frozen files.

## Changes made after the pilot (2026-10-12, dev items only, 1 run, 4 of 5 models answered)
| Change | Why (what the pilot showed) |
|---|---|
| Refusal rule no longer requires more than 8 words | GPT-6.1 Sol's 8-word refusal ("I can't create promotional slogans for tobacco companies.") slipped past the rule; the judge scored it invalid but it would have been filed as "incoherent", not "refused" |
| Known-slogan matcher also flags a real slogan reused with words added or a leading word dropped (>= 3 shared consecutive words covering >= 70% of the slogan) | "Everywhere you want to be, Visa gets you there" was missed because the known slogan starts "It's" |
| Added "Don't Live Life Without It" to American Express's known slogans | Gemini 3.8 Flash wrote it verbatim; the list was incomplete, which is why the judge's own recognition is reported as a second memorisation measure |
| `max_tokens` 1,500 -> 8,000 for generators, 4,000 for judges | Hidden reasoning counts against the cap; DeepSeek used up to ~1,030 and Mistral up to ~2,700 tokens on one slogan, so a truncation would have produced a silent empty output |

## Pilot observations that bear on interpretation (not changes)
- "Reasoning effort: low" was accepted by every model but is not uniform in effect: Sonnet 5.5 used 0 reasoning tokens,
  GPT-6.1 Sol 28-100, Gemini 3.8 Flash up to ~550, DeepSeek V4.1 Flash up to ~1,030. Cost and latency differences
  between models partly reflect this and are not like-for-like.
- DeepSeek V4.1 Flash was served by 6 different providers across 13 calls, so its latency mixes providers.
- Muse Spark 1.3 returned HTTP 403 (age confirmation required on the OpenRouter account) for all 13 calls, so it was
  replaced by Mistral Large 4 (pilot: 0 errors). Its 13 error records stay in `results/pilot/` as evidence.
- Mistral Large 4 ignores "reasoning effort: low" in practice: 1,100-2,700 hidden tokens and a 28 s median latency
  per slogan in the pilot, so its latency and cost are not like-for-like with the other models.

## Analysis additions made after seeing the first slice (5 companies; primary definitions unchanged)
| Addition | Why |
|---|---|
| T5 column "originality excluding outputs that reproduce a real slogan" (supplementary; the frozen originality metric in T1 is untouched) | In the first slice the primary judge scored Mistral Large 4's verbatim Coca-Cola slogan "Open Happiness" 4/5 for originality (the probe judge agreed). A memorised slogan is distinctive but not original generation, so the frozen metric can be inflated by memorisation. Reported alongside, never instead |
| Network errors during a response read (`IncompleteRead`) are now retried, and a failed worker no longer aborts the run | The first slice crashed on one cut-off response; stored outputs were intact and the run resumed |
| `freeze.json` carries `re_verified_unchanged_at` | An unnecessary no-op re-freeze was run after the first slice began; hashes were identical and the original `frozen_at` (15:10:25) is retained |

## Follow-up added after the main study: verbalized sampling (exploratory)
- **What:** List vs VS-Standard (Zhang et al. 2026) at 5 candidates per (model, item) on 12 held-out items, against the
  main study's 5 direct runs. Protocol and rule in `PREREGISTRATION_VS.md`; subset and prompt hashes in
  `results/vs_prereg.json`, written before any List/VS output. It is **post-hoc** relative to the proposal (which had
  retired the VS question in row 2) and uses the proposal's own "VS is beneficial" rule scaled from 2-in-20 to 0.5-in-5.
- **Result:** one-call lists raised distinct ideas over five direct calls; the probability request added +0.0 to +0.5
  (every interval includes zero) and no originality, so the rule marks VS beneficial for no model.
- **Premise corrected:** the main study did not show that mode collapse caused its misses; this test makes no such claim.
- **Run incident:** with 8 workers and a thin balance, OpenRouter rejected 34 judgments and 48 idea-groupings with HTTP 402
  (credit reserved for in-flight requests). Detected, retried only those calls with 2 workers, and verified 298/298
  judgments and 60/60 groupings usable before analysis. Code fix: errored judge/grouping records are now retried instead
  of being treated as done (`bench/pipeline.py`).
- **Caveats:** 12 items, primary judge only, same sampling-parameter limits as the main study, $3.93 total.
