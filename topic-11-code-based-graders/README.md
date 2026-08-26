# Topic 11 — Code-Based Graders

A **code-based grader** is Python code that checks whether an AI answer follows rules.

For this lesson, the AI output must be JSON like this:

```json
{"action": "track_order", "order_id": "101", "message": "I will track your order."}
```

The grader checks:

1. Is the output valid JSON?
2. Is `action` one of the allowed actions?
3. Is `order_id` correct?
4. Does the message include required words?
5. Does the message avoid unsafe words?

Run it:

```bash
cd /Users/ankitraj/Developer/evals-roadmap/topic-11-code-based-graders
python3 evaluate.py
```

The output shows **PASS** or **FAIL** for every test case and explains the reason.

## Difference from a rule-based grader

A rule-based grader may check one simple rule, such as `action == "track_order"`.

A code-based grader is the whole Python function that can combine many checks: JSON validation, exact values, regex checks, length limits, safety rules, and calculations. It is deterministic: the same input always produces the same result.
