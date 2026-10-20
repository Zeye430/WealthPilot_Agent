# Evaluation reports

Every run of the scenario evaluation writes a Markdown report and a matching JSON file with every reply, check and judge verdict, including the failures. Reports are kept as a record of how the system improved, not just the final result.

## Latest results (2026-10-20)

Same 25 scenarios per language, 3 runs each, same prompts, Kimi as the fixed judge.

| Model | Chinese | English |
|---|---|---|
| Kimi K2.6 (default) | [73/75](scenarios-2026-10-20.md) | [72/75](scenarios-en-2026-10-20.md) |
| DeepSeek Flash | [72/75](scenarios-2026-10-20-deepseek.md) | [69/75](scenarios-en-2026-10-20-deepseek.md) |
| Qwen Plus | [54/75](scenarios-2026-10-20-qwen.md) | [64/75](scenarios-en-2026-10-20-qwen.md) |

## Earlier runs

- `scenarios-2026-10-17-*`: the first rounds while building the gate, recommendations, rewards and sales rules. Failures there led to new rules (for example the unsourced-figure and false-action rules).
- `scenarios-2026-10-18*`, `scenarios-en-2026-10-18`: after the English UI was added.
- `scenarios-2026-10-19*`: after reliability work and the amount-grounding rule.
- Files ending in scenario IDs (for example `-R01-C01`) are partial runs used to check a specific fix.

## Load tests

`load-2026-10-18-*` measure throughput and latency against a fake model (system overhead only) and with the real model at low concurrency. `fake-release-conn` and `fake-pool-tuned` show the effect of releasing the database connection while waiting for the model (40 concurrent users: 7 → 16 requests per second).

## Reproduce

```bash
cd backend
uv run python ../evaluations/run_scenarios.py --repeat 3              # Chinese suite
uv run python ../evaluations/run_scenarios.py --suite en --repeat 3   # English suite
```

Needs a model API key in `.env` and the database running. A full suite costs about $2 with Kimi.
