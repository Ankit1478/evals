# Topic 13 — Pairwise Comparison

Pairwise comparison asks which of two AI responses is better. It is useful when
several answers can be correct and an exact reference answer would be too rigid.

This lesson uses a **hybrid grader**:

```text
two candidate responses
        │
        ▼
deterministic hard gates
  ├─ only one passes → automatic winner
  ├─ neither passes  → both fail
  └─ both pass       → blinded human comparison
```

Pairwise preference never replaces correctness or safety. A fluent response
with the wrong order id must not defeat a less polished correct response.

## Start

```bash
cd /Users/ankitraj/Developer/evals-roadmap/topic-13-pairwise-comparison
python3 pairwise.py --bootstrap
python3 pairwise.py --next
```

The seed has four comparisons. Two are resolved automatically by the hard
gates, while two require a human preference.

## Review interactively

```bash
python3 pairwise.py --interactive
```

The reviewer sees only Response A and Response B. Model identities are hidden,
and their display order is stable but shuffled independently for each pair.
Choose `a`, `b`, `t` for tie, `f` when both fail, `s` to skip the pair for this
session, or `q` to stop. Every saved human decision requires a reviewer name
and a reason.

You can also record a decision directly:

```bash
python3 pairwise.py --choose a --pair pair-001 \
  --reviewer ankit --notes "More direct and does not overclaim."
```

`a` and `b` refer to the **displayed** positions. The audit trail maps that
choice back to the original candidate while preserving the display order.

## Inspect and export

```bash
python3 pairwise.py --list
python3 pairwise.py --stats
python3 pairwise.py --export preferences.jsonl
python3 pairwise.py --reset-db
```

The report keeps these outcomes separate:

- original candidate A wins;
- original candidate B wins;
- ties;
- both fail;
- automatic versus human decisions;
- pending comparisons;
- decisive preference rate, which excludes ties and both-fail outcomes.

The decisive preference rate answers “which candidate wins more often when a
winner exists?” It does **not** answer “is either candidate good enough?” Read
it together with the hard-gate and both-fail results.

## What is reference-based here?

The hard gates use references: expected action, order id, and required or
prohibited phrases. These assertions protect objective behavior.

The human comparison is reference-free: once both responses meet the absolute
requirements, the reviewer applies a rubric for clarity and helpfulness without
comparing either response with one ideal answer.

## Production extensions

This local lesson permits one decision per pair. A production workflow should
also use multiple independent reviewers, adjudication for disagreements,
reviewer-quality checks, randomized rather than merely stable display order,
PII controls, access policies, rubric versioning, and confidence intervals.

Run the tests with:

```bash
python3 -m unittest test_pairwise.py -v
```
