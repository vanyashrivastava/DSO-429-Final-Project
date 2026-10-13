# Slogan benchmark (DSO 429 Project 1, Phase 2)

Benchmarks five LLMs on writing one advertising slogan from a company brief: 50 real companies x 5 models x 5
independent runs, graded by programmatic rules plus an LLM judge. Another team can re-run it from this page.

## Re-run it
```
cp .env.example .env              # paste an OpenRouter key after OPENROUTER_API_KEY=   (python 3.9+)
python3 bench.py selftest         # 21 offline tests, no network
python3 bench.py estimate         # cost estimate from the live model listing, no spend
python3 bench.py run --phase pilot --confirm     # dev items only, 1 run: check parsing
python3 bench.py freeze           # hash items, prompts, grading code, config
python3 bench.py run --phase final --confirm     # full run; resumable; budget cap --max-usd (default 25)
python3 bench.py analyze --phase final           # tables + figures (needs: pip install numpy matplotlib)
```
Reproducing the numbers **without** an API key: `results/final/raw/*.jsonl` holds every raw output and judgment;
`python3 bench.py analyze --phase final` rebuilds every table and figure from them.

## What was run
| | |
|---|---|
| Items | 50 companies (`data/items.json`, `.csv`): 28 standard, 12 contextual, 10 stress; split column marks 12 `dev` / 38 `heldout` |
| Runs per item | **5** per model (fresh context each call); sparse items run twice (sparse and full description) |
| Generators | `anthropic/claude-sonnet-5.5`, `google/gemini-3.8-flash`, `openai/gpt-6.1-sol`, `mistralai/mistral-large-4-0`, `deepseek/deepseek-v4.1-flash` |
| Judges | primary `x-ai/grok-4.7` (temp 0); self-preference probe `anthropic/claude-opus-5.5`; embeddings `openai/text-embedding-3-small` |
| Run date | **2026-10-12**, 15:10-17:42 PDT (frozen 15:10:25; first 5 companies run first, rest resumed). Canonical slugs, providers and per-model timestamps: `results/final/run_manifest.json` |
| Context given | Identical to every model: `prompts/generator_system.txt` + `generator_user.txt` filled from the item (company, industry, description, optional brief, requirements). No examples, rubric or known slogans. |
| Held fixed | Prompt, items, run count, order randomised with seed 429, max 8,000 tokens for generators / 4,000 for judges (hidden reasoning counts), reasoning effort low (accepted by all models; actual reasoning tokens still differ) |
| Varied | Model only. Temperature 0.7 / top_p 1.0 / seed are sent only where the model accepts them; `run_manifest.json` lists what each received (Claude Sonnet 5.5 and GPT-6.1 Sol accept no temperature) |

## Where things are
- `PREREGISTRATION.md` definitions, acceptable-failure line, ranking rule (frozen before the run). `DEVIATIONS.md` changes vs the proposal.
- `prompts/judge.txt` is the exact judge prompt and rubric; `bench/checks.py` + `bench/merge.py` are the grading code.
- `results/final/raw/` generations, judgments, idea groupings, embeddings (unedited). `outputs_sample.csv`: 12 raw outputs per model.
- `PREREGISTRATION_VS.md`, `results/list/`, `results/vs/`: post-hoc verbalized-sampling follow-up on 12 held-out items (`bench.py vs-freeze`, `vs-run`, `vs-analyze`); Direct baseline = `results/final`.
- `results/final/tables/` T1-T10 (`.md` and `.csv`), `figures/` fig1-fig5, `disputes.md`, `audit/` (blinded human sheet).

## Notes
Costs and latencies are measured from the provider's usage record and client-side timing; evaluation cost is separate.
`bench.py` refuses a final run if frozen inputs changed. `--mock` runs an offline fake provider for testing only.
