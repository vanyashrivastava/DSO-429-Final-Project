| Failure mode (first that applies) | Whose fault? | Claude Sonnet 5.5 | Gemini 3.8 Flash | GPT-6.1 Sol | Mistral Large 4 | DeepSeek V4.1 Flash |
|---|---|---|---|---|---|---|
| api_error | infrastructure | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| refusal | model declined | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| followed_injection | model wrong | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| format_violation | model wrong | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| word_limit | model wrong | 25 (13.2%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 1 (0.5%) |
| missing_required | model wrong | 0 (0.0%) | 1 (0.5%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| used_banned | model wrong | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| incoherent_or_irrelevant | model wrong | 1 (0.5%) | 5 (2.6%) | 2 (1.1%) | 3 (1.6%) | 0 (0.0%) |
| noncompliant | model wrong | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| unfaithful | see counterfactual (T8) | 1 (0.5%) | 0 (0.0%) | 0 (0.0%) | 1 (0.5%) | 2 (1.1%) |
| valid but generic | quality flag (output is valid) | 53 (27.9%) | 84 (44.4%) | 87 (45.8%) | 111 (58.4%) | 87 (45.8%) |
| valid and reproduces real slogan | quality flag (output is valid) | 8 (4.2%) | 10 (5.3%) | 0 (0.0%) | 29 (15.3%) | 20 (10.5%) |
| valid, clean | quality flag (output is valid) | 102 (53.7%) | 89 (47.1%) | 101 (53.2%) | 46 (24.2%) | 80 (42.1%) |

Held-out split, all runs, counts (share of outputs). 'model wrong' = the instruction or constraint was in the prompt and the output still broke it. Generic and unfaithful outputs are attributed using the sparse-vs-rich counterfactual in T8.
