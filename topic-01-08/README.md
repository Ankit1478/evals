# Topics 001-008 — Foundations

A single-file practical lab covering PDF topics 001-008: what evals are, why AI
systems need them, how they differ from software tests, and the anatomy of a
measurement system.

| file | what it is |
|---|---|
| `phase_1_foundations_topics_001_008.py` | lesson notes, mock system under test, grader, runner, release decision, and tests |
| `dataset.jsonl` | 10 evaluation cases, one JSON object per line |

Run it with the standard library only, no API keys required:

```bash
python3 topic-01-08/phase_1_foundations_topics_001_008.py
```

## Why JSONL for eval datasets

- Each case is independent.
- New cases can be appended easily.
- Git produces understandable line-based diffs.
- Large datasets can be processed one line at a time.
- A single malformed case can be reported with its line number.

## Dataset coverage

The 10 cases cover basic tracking, basic cancellation, distracting numbers,
missing order IDs, uppercase inputs, IDs beginning with `#`, alphanumeric IDs,
ambiguous actions, leading zeros, and extra whitespace.

Expected values must be evaluator-owned. The agent must never generate its own
expected result.
