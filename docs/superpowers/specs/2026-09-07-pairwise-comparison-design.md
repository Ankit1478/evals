# Pairwise Comparison Lesson Design

## Purpose

Add a dependency-free lesson that demonstrates how to compare two AI responses without replacing objective correctness and safety checks. The lesson will live in `topic-13-pairwise-comparison/` and will not modify the earlier topics.

## Files

- `README.md` explains reference-free pairwise comparison, the hybrid grading flow, CLI commands, bias controls, and interpretation of results.
- `pairs.jsonl` contains small, PII-free Nimbus support examples with one prompt, two candidate responses, structured expected behavior, a rubric, model labels, and a rubric version.
- `pairwise.py` implements validation, deterministic hard gates, blinded display order, a SQLite-backed review queue, decisions, audit evidence, export, and aggregate reporting.
- `test_pairwise.py` exercises hard-gate outcomes, deterministic blinding, displayed-choice mapping, decision validation, queue ordering, and statistics.
- `.gitignore` excludes the generated SQLite database and exported preference data.

## Evaluation Flow

Each candidate response is JSON containing `action`, `order_id`, and `message`. A deterministic gate validates JSON, the expected action, the expected order ID, required text, and prohibited text.

The pair outcome is resolved as follows:

1. If exactly one candidate passes the hard gate, that candidate wins automatically.
2. If both candidates fail, the outcome is `both_fail` automatically.
3. If both candidates pass, they enter the human review queue.
4. The reviewer sees the two responses as A and B without model names. Their order is derived from a stable hash so it is balanced, reproducible, and testable.
5. The reviewer chooses A, B, `tie`, or `both_fail` and must provide their name and notes.
6. The stored audit record maps the displayed choice back to the original candidate identity while also preserving display order.

Automated outcomes and human decisions remain distinguishable in storage and reporting.

## Storage and CLI

SQLite keeps source pairs separate from append-only decisions. One decision per pair is sufficient for this lesson; the README will explain that production systems should support multiple independent reviews and adjudication.

Commands will support:

- creating or rebuilding the local database;
- showing the next unresolved pair;
- interactive review;
- recording a blinded decision non-interactively;
- listing queue state;
- reporting candidate wins, ties, both-fail outcomes, and decisive preference rate;
- exporting completed preference records as JSONL.

Database writes use parameterized statements. Invalid pair IDs, choices, missing reviewer metadata, and attempts to overwrite a decision produce explicit errors.

## Reporting

The report separates:

- automatic hard-gate decisions;
- human-reviewed decisions;
- candidate A wins;
- candidate B wins;
- ties;
- both-fail outcomes;
- unresolved comparisons;
- decisive preference rate, calculated only from A/B wins.

This preserves the distinction between relative preference and absolute quality: a candidate can win a pair while both candidates remain unacceptable.

## Verification

Implementation will follow test-driven development. Tests will use temporary databases and the real grading and persistence functions. Final verification will run the complete unit-test file plus representative read-only CLI commands against a temporary database.
