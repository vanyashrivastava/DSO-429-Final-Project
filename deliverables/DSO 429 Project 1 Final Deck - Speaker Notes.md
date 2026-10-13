# Speaker Notes — Benchmarking Ad Slogan Writing in LLMs

Oct 13, 2026 · Project 1, Phase 2 final deliverable · six-minute slot, questions included

**Timing plan:** about 5:05 of talking plus the 15-second call-it pause, which leaves roughly 40 seconds for questions; if you run long, cut the follow-up paragraph on slide 6 to one sentence. The
suggested speaker split below is a default: change the names freely, but whoever presents a slide should also be able to
answer questions about the others (the assignment requires it for every team member).

## Slide 1 — Cover — Milan Jha (0:30)

Good morning. We're Milan, Shahir, Vanya, Samira, James and Kirti. Our proposal was to benchmark joke creativity. After
our professor's feedback we moved to a task with a clearer business use: writing an advertising slogan from a company
brief. The question is simple. Five current language models each write slogans for the same fifty companies. Which ones
write slogans that are valid and original enough to use, and does any of them clear the line we committed to before we
saw a single output?

## Slide 2 — The task — Shahir Ali (0:45)

The task is one slogan per company brief. We have fifty real companies in three tiers. Twenty-eight are standard briefs:
a company, an industry and a description. Twelve add hard constraints a rule can check, such as a word limit, a required
word or a banned phrase; for example Nike, with six words maximum and the phrase "just do it" banned. Ten are edge cases:
a description of only a few words, sensitive industries like tobacco and defense, a description buried in irrelevant
meeting minutes, and an instruction injected into the description.

Twelve items are dev items we were allowed to look at while building. Thirty-eight are held-out and carry every headline
number. Five models, one identical prompt, fresh context each call, five independent runs per item: 1,325
outputs, run on October 12. What we could not hold fixed is sampling: Sonnet 5.5 and GPT-6.1 Sol do not accept a
temperature setting, so we say that plainly rather than pretend the conditions were identical.

## Slide 3 — The instrument — Samira Mustapha (1:00, then the call-it pause)

Grading has three layers. First, rules with no model involved: one line, within the word limit, every required word
present, no banned word, not a refusal. A missing output counts as a failure. Second, a blinded judge, Grok 4.7, which
never generates slogans and sees only the slogan. It answers yes or no on coherence, relevance, compliance and whether the
slogan makes an unsupported factual claim, and gives originality from one to five: one is stock, three is a new twist,
five is a standout. Third, checks on the judge itself: a second judge from the Claude family re-scores held-out outputs
to test self-preference, a list of real slogans measures memorization, and a blinded human sheet is ready.

The line at the bottom was frozen before we collected anything and carried over from the proposal: at least ninety-five
percent valid, mean originality at least three out of five, and at least ninety percent of constraint briefs met.

**Pause here.** Ask the room to take fifteen seconds and write on their card which model they expect to score highest and
whether any model clears the line. Do not show slide 4 until they have written it down.

## Slide 4 — Results — Vanya Shrivastava (1:00)

Here is the answer. No model clears the line. Look at the dashed lines: four of the five models pass validity and
constraints, and every model misses originality. The best originality is 2.65 and the worst is 2.37
against a line of three.

Two things matter about how to read this. First, the whiskers are one standard deviation across five runs, and where two
models differ by less than that run-to-run noise we do not rank them. Gemini, GPT, Mistral and DeepSeek are tied on
validity and constraints. Second, there is one real separation: Sonnet falls to 85.8% valid
and 78% on constraints, and that comes from a single failure, breaking a stated word
limit in 25 of 190 outputs. On the right, cost and speed are results too: DeepSeek V4.1 Flash is
cheapest at $0.09 for its whole run, and Mistral Large 4 is slowest at 20 seconds a slogan
because it does a lot of hidden reasoning.

## Slide 5 — Where it breaks — James Kyles (0:50)

This slide separates a model being wrong from a model never being given what it needed. Sonnet's word-limit failures are
model-wrong: the limit was in the prompt. The originality shortfall is partly missing input. On the three sparse items, when
we gave the full description instead of one clause, generic outputs fell from 53–73% to
0–27% and originality rose 0.6 to 1.1 points. It is only three items, so
it is evidence, not proof.

On the right is where our own instrument bit. Memorization: Mistral reproduced a real company slogan in
20% of outputs, and the judge gave a verbatim Coke slogan four out of five, so originality is
inflated; we report a supplementary score without those outputs. The yes/no criteria saturate, so validity differences
come from our rules. And we looked for self-preference: the Claude judge minus the neutral judge, for Claude's own family
against the others, is -0.12 with an interval of -0.24 to +0.00, so we found none.

## Slide 6 — Interpretation — Kirti Subramanian (1:05)

What this means: every model writes a valid slogan, and none writes a distinctive one. Against our own line, four models
pass validity and constraints and all five miss originality. So on Monday, treat these as first-draft tools. Choose a model
on reliability and cost, add a simple length check before human review, and put a differentiator in the brief, because that
was our cheapest originality gain.

We also ran a follow-up on verbalized sampling, the method from the paper our proposal was built on, on 12 held-out companies. Asking for five slogans in one call lifted distinct ideas from 1.9 to 3.1 out of five with separate calls, to 3.2 to 3.6 with a plain list and 3.3 to 3.8 with verbalized sampling. The part that is specific to verbalized sampling, asking for probabilities, added between -0.25 and +0.50 ideas over the list, every interval includes zero, and originality did not go up. So by our own rule it is not beneficial for any model: the gain is from list-style prompting.

The limits matter. We have not yet validated the judge against people, we used one primary judge family, fifty companies
and one prompt, and originality is a rating, not evidence a slogan sells. The one change we would make with two more weeks
is blinded human ratings of about two hundred slogans. And now, break it: write on your card one item you think this
benchmark would get wrong.

## Questions to be ready for (everyone)

- **Why did you drop the joke project and verbalized sampling?** Professor feedback moved us to a model-versus-model
  business task. One prompt condition made five models, five runs and a held-out split feasible before the deadline.
  The proposal's "VS is beneficial" thresholds are retired (see DEVIATIONS.md).
- **What is the held-out split for?** Twelve dev items were used to tune prompts and parsing in a pilot; the headline
  numbers use only the other 38, which were not looked at before the freeze.
- **Why is Sonnet's validity so low?** Rule check: it broke the stated word limit in 25 of 190
  held-out outputs. Every other failure was rare. It is an instruction-following slip, not a creativity gap.
- **Is the judge biased toward its own family?** We checked with a second judge from the Claude family. The difference
  between the two judges, for Claude's output against the others, was -0.12 (CI -0.24 to +0.00).
  We found none, but only one family was probed.
- **Why did nobody reach 3.0 originality?** Most slogans were scored 2 or 3. Part is missing input (sparse briefs gain
  0.6 to 1.1 points with a fuller description) and part is that these are competent but generic lines. We did not
  change the line after seeing the scores.
- **What does memorization do to the score?** It inflates originality (a verbatim Coke slogan scored 4/5). We report
  memorization separately and a supplementary originality without those outputs.
- **Why Mistral and not Muse Spark?** Muse Spark was blocked by an account age confirmation, so we replaced it after the
  pilot and before the freeze.
- **What did it cost?** $14.77 in total: $1.54 generating and $13.23
  grading. Generation is cheap; evaluation dominates.
- **Did you try verbalized sampling, and did it work?** Yes, as a follow-up on 12 held-out companies with a plain-list
  control. Any one-call list raised distinct ideas; the probability request added little (all intervals include zero)
  and did not raise originality. It was pre-registered afterwards and is exploratory.
- **Does mode collapse explain the low originality?** Not on our evidence. Repetition exists (15-31% exact duplicates
  across five direct calls) but the model that repeats most (Sonnet) scores highest on originality.
- **What went wrong in the follow-up run?** A burst of credit-reservation errors (HTTP 402) rejected 82 judge and grouping
  calls; we detected it, retried only those, and checked 298 of 298 judgments and 60 of 60 groupings were complete.
- **What could still be wrong?** The human audit has not been scored, sampling parameters differed by model, and the
  stress subtypes have two or three items each.
