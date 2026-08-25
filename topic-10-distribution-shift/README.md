# Topic 10 — Distribution Shift Evals

This is the next production step after `topic-09-datasets`: the same real Azure OpenAI tool-selection eval, but cases live in a SQLite event store and are split into two realistic traffic windows.

The database is created locally from `production_events.jsonl` the first time you run the harness. The seed data is intentionally synthetic and PII-free, but its schema and workflow mirror a production evaluation pipeline:

```
production events → SQLite snapshot → stratified eval → shift + quality report → saved run artifact
```

## Run it

```bash
cd topic-10-distribution-shift
python3 shift_eval.py --agent keyword             # free baseline + shift report
python3 shift_eval.py --agent llm                 # real Azure OpenAI calls
python3 shift_eval.py --agent llm --window current
python3 shift_eval.py --agent llm --slice language_es
python3 shift_eval.py --agent llm --gate 0.80
```

Copy `../topic-09-datasets/.env.example` to `../topic-09-datasets/.env` and fill it in before using `--agent llm`. The harness imports Topic 9's agent, tools, graders, cache, retries, and Azure configuration; there is one agent specification rather than a forked copy.

## What to read in the report

1. **Input distribution** — baseline vs current traffic composition. It tells you whether the population moved.
2. **Quality by window** — evaluates both windows with the same system and grader. It tells you whether behavior differs.
3. **Quality by slice** — finds the concrete group that needs attention.
4. **Weighted quality** — reweights oversampled risk cases to their production traffic share. Do not use a raw, intentionally oversampled score as your estimate of customer experience.

The seed contains a deliberate shift: baseline traffic is English and current traffic is Hindi. The simple keyword agent understands the English keywords but not Hindi. Your task is to distinguish a changed model from a changed population.

## Rule-based grader

The evaluator uses simple rules to decide whether an answer passes:

1. Did the bot choose the expected action (`track_order` or `cancel_order`)?
2. Did the bot extract the correct order number?

For example, for `where is my order #101?`, the only passing answer is:

```text
action: track_order
order id: 101
```

This is called a **rule-based grader** because normal Python comparisons decide pass or fail. No second AI model is used to grade the answer.

## Database model

`evals.db` is a local SQLite database generated at runtime. The main `production_events` table holds the scrubbed input, gold outcome, provenance, policy version, timestamp, traffic window, and slice fields. `eval_runs` and `eval_records` preserve run evidence for later comparison.

Useful commands:

```bash
python3 shift_eval.py --reset-db                 # rebuild only the local database
sqlite3 evals.db '.schema production_events'     # inspect the production-shaped schema
sqlite3 evals.db 'select traffic_window, count(*) from production_events group by 1'
```

Never put real customer messages into a shared eval database without PII scrubbing, retention rules, access control, and a documented labeling process.
