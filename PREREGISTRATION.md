# Pre-registration: slogan benchmark (frozen before the final run)

Written 2026-10-12, before any generation call was made. The only network calls so far are reads of OpenRouter's
public model listing. `python3 bench.py freeze` hashes the eval set, prompts, grading code and this configuration;
the final run refuses to start if any of them changed since the freeze.

## Question
For short advertising slogans written from a company brief, how do five LLMs compare on validity, originality,
ability to follow explicit constraints, repetition, memorisation of real slogans, latency and cost, and does any model
clear the acceptable-failure line we committed to in the proposal?

## Design
- **Items:** 50 real companies, one item each, three tiers: 28 standard, 12 contextual (explicit, machine-checkable
  constraints), 10 stress (3 sparse description, 3 sensitive industry, 2 long irrelevant context, 2 injected
  instruction). `data/items.json`; split marked per item (12 dev, 38 held-out). Headline numbers use held-out only.
- **Models (5):** `anthropic/claude-sonnet-5.5`, `google/gemini-3.8-flash`, `openai/gpt-6.1-sol`,
  `mistralai/mistral-large-4-0`, `deepseek/deepseek-v4.1-flash`, via OpenRouter.
- **Condition:** one prompt (`prompts/generator_*.txt`), one slogan per call, fresh context, no tools. Identical for
  every model. n = 5 independent runs of every item per model.
- **Sampling:** temperature 0.7, top_p 1.0, reasoning effort "low", and a per-(item, run) seed, each sent only if the
  model's live OpenRouter listing says it accepts that parameter. Parameters that are not accepted are not
  sent, and the run manifest records what each model actually received.

## Definitions (implemented once, in `bench/merge.py` and `bench/checks.py`)
- **Programmatic check** passes iff: an answer exists (no API error, refusal or empty output); it is a single line with
  no label/preamble (surrounding quotes and bold are tolerated); word count <= the item's limit (default 10); every
  required word/phrase is present; no banned phrase is present; the output is not the injected token.
- **Valid** = programmatic check passes AND primary judge says coherent, relevant, complies and faithful (no
  unsupported factual claim). Failures are kept as failures: an output that does not exist is invalid, not dropped.
- **Originality** = primary judge's 1-5 rating (anchors in `prompts/judge.txt`), averaged over valid outputs.
- **Contextual compliance** = programmatic check passes AND judge says complies, over contextual-tier outputs.
- **Memorisation** = output matches a known real slogan of that company (normalised equality, containment, or
  similarity >= 0.85); secondarily, the judge says it recognises the slogan.
- **Repetition** = distinct idea groups among the valid outputs of one (model, item) across the 5 runs, divided by the
  number of valid outputs; the judge forms the groups. Secondary: 1 - mean cosine similarity of
  `openai/text-embedding-3-small` embeddings (negatives clipped to 0), as in the proposal.
- **Latency** = client-side wall-clock seconds of the successful call. **Cost** = billed USD from the provider's
  usage record for every generation call; evaluation cost is reported separately.

## Acceptable-failure line (carried over unchanged from the proposal, not re-tuned for slogans)
A model clears the line only if, on the held-out split, **all three** hold on the mean over runs:
valid outputs >= 95%, mean originality >= 3.0 of 5, contextual-brief compliance >= 90%.
The margin by which each is cleared or missed is reported.

## Uncertainty and ranking (frozen)
- Run-to-run spread: mean, SD and min-max of the 5 run means (same items, fresh samples).
- Item sampling: 95% bootstrap CI resampling whole items (2,000 resamples, seed 429), pairing models on the same items.
- Two models are **ranked** on a metric only if |difference| exceeds the run-to-run SD of either model AND the paired
  item-bootstrap CI of the difference excludes zero. Otherwise they are reported as indistinguishable.
- Criteria are reported separately. No composite score is computed. Tier results are reported separately.

## Instrument checks planned
- Primary judge: `x-ai/grok-4.7`, temperature 0, never a generator, and in a family with no generator. It sees the
  slogan only (no model, run or condition).
- Self-preference probe: `anthropic/claude-opus-5.5` re-scores held-out base outputs. Self-preference is estimated as
  the probe's lift for its own family's generator (Claude Sonnet 5.5) over the primary judge's, minus the same lift for
  the other generators (difference-in-differences, bootstrap CI over items).
- Judge-vs-programmatic conflicts and judge-vs-judge gaps are listed in `disputes.md` for human reading.
- Missing-input diagnosis: the 3 sparse items are run with a one-clause description and again with a full description.
- Human audit: a blinded sheet (`bench.py audit`) for team raters; agreement is reported if it is completed.

## What will be reported whatever happens
A null result (no model separable from another, or no model clearing the line) is a result and will be reported as
such. Any change to the items, prompts or grading after the freeze invalidates the run and is logged in DEVIATIONS.md.
