# Addendum: verbalized-sampling follow-up (post-hoc, exploratory)

Written 2026-10-12 after the main benchmark was complete and **before any List or VS output was collected**.
The subset and prompt hashes are in `results/vs_prereg.json` (written by `bench.py vs-freeze`; `vs-run` refuses
to start if a prompt changed). This is a follow-up to the main study, not part of its frozen design.

## Question
Does verbalized sampling (VS-Standard, Zhang et al. 2026) give more distinct, valid slogan ideas than asking for a
plain list of the same size, and than five independent direct calls, without lowering originality?

## Design
- **Items:** 12 of the 38 held-out companies (6 standard, 3 constraint, 3 stress), drawn with a fixed seed, never
  inspected. Small on purpose (cost); results are exploratory and the intervals are wide.
- **Models:** the same five generators, same sampling settings (sent only where accepted), same reasoning setting.
- **Conditions, equal budget of 5 candidates per (model, item):**
  - *Direct*: the 5 independent single-slogan calls already collected in `results/final` (runs 1-5).
  - *List*: one call asking for 5 slogans as JSON (`prompts/list_user.txt`).
  - *VS*: one call asking for 5 slogans with a probability for each (`prompts/vs_user.txt`).
  List and VS differ **only** in the probability field. Probabilities are never used in scoring.
- **Grading:** identical rules and primary judge (Grok 4.7) as the main study; no probe judge. A candidate missing
  from a reply counts as a failure.

## Metrics and rule (frozen)
- Primary: distinct valid ideas among the 5 candidates (judge-formed groups, as in the main study).
- Also: validity %, originality, embedding diversity, real-slogan reproduction, cost per item, call latency.
- **VS counts as beneficial for a model** (the proposal's rule, scaled from 2-in-20 to 0.5-in-5) iff: VS − List in
  distinct valid ideas ≥ 0.5 with a paired item-bootstrap 95% CI above zero; originality drop ≤ 0.25; cost per
  distinct valid idea ≤ 1.25× List. Reported per model; a null or negative result is a result.

## Not claimed
No claim is made that mode collapse caused the main study's misses (the misses were a word-limit slip, flat
originality, and memorisation). This test only asks whether VS changes diversity and quality for this task.
