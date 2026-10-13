| Model | Median latency / call, s | Range of per-run medians, s | p95 latency, s | Total generation cost, USD | USD per 1,000 outputs | Mean output tokens | Mean reasoning tokens | Calls | Errors |
|---|---|---|---|---|---|---|---|---|---|
| Claude Sonnet 5.5 | 1.47 | 1.44–1.48 | 2.13 | $0.160 | $0.602 | 18 | 0 | 265 | 0 |
| Gemini 3.8 Flash | 2.04 | 1.86–2.24 | 7.88 | $0.185 | $0.697 | 160 | 152 | 265 | 0 |
| GPT-6.1 Sol | 3.21 | 2.99–3.51 | 5.12 | $0.252 | $0.951 | 69 | 54 | 265 | 0 |
| Mistral Large 4 | 20.33 | 19.64–21.65 | 45.38 | $0.856 | $3.230 | 1503 | 1547 | 265 | 0 |
| DeepSeek V4.1 Flash | 2.70 | 2.59–3.03 | 12.48 | $0.091 | $0.343 | 458 | 447 | 265 | 0 |

Generation cost = billed USD for every generation call in the full run (all items incl. rich-brief variants, all runs), from the provider's reported usage.cost. Latency = wall-clock seconds per successful call, measured client-side with 6 concurrent requests. Evaluation cost (reported separately, not part of a model's cost): anthropic/claude-opus-5.5 (judging) $6.570; x-ai/grok-4.7 (judging) $4.756; x-ai/grok-4.7 (idea grouping) $1.905; openai/text-embedding-3-small (embeddings) $0.000.
