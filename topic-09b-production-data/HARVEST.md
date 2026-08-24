# Exercise — turn production logs into eval rows

You have `production_logs.jsonl`: **30 real-looking traces** from the Nimbus
support bot. Your job is to mine them into eval test cases.

Nobody labels all 30. Boring successful chats teach you nothing.

---

## Step 1 — Triage

```bash
python3 inspect_logs.py --risky     # 14 rows worth your time
python3 inspect_logs.py --pii       # rows that must be scrubbed
python3 inspect_logs.py --show tr_005
```

The risk score is just a sum of signals: thumbs-down, escalated, repeat contact,
human-flagged note, error, multiple tool calls, low CSAT, money-touching tool.
**None of that says the bot was wrong** — it says a human should look.

## Step 2 — For each trace, decide

Ask three questions, in order:

1. **Was the bot actually wrong?** A thumbs-down often means the *answer* was
   correct but the customer was unhappy about reality (tr_022: the parcel really
   is delayed). Not every complaint is a bug.
2. **What should it have done?** Justify it from `SYSTEM_PROMPT` in
   `../topic-09-datasets/eval.py`. If no policy line covers it, you found a
   **spec gap** — fix the policy first, then label.
3. **Does this belong in the dataset?** Skip near-duplicates of rows you already
   have (tr_017, tr_018 add nothing over tr_001).

## Step 3 — Scrub before you save

Never commit real customer data.

```
before: "Priya Sharma, priya.sharma@gmail.com, +91 98800 12345, 14 Church Street"
after:  "[NAME], [EMAIL], [PHONE], [ADDRESS]"
```

Keep order ids — they're not personal and the test needs them. Replace names,
emails, phones, cards, and street addresses. `tr_030` has a card number in the
*user message*; `tr_023` has another customer's address in the *bot's reply*.
Check both sides.

## Step 4 — Write the row

```json
{
  "id": "prod-003",
  "input": "<the scrubbed user message>",
  "expected_tool": "cancel_order",
  "expected_args": {"order_id": "7001"},
  "tags": ["self_correction", "regression"],
  "source": "production_failure",
  "trace_id": "tr_024",
  "actual_tool": "cancel_order",
  "why": "<the policy line that makes your label correct>"
}
```

- `trace_id` — links back to the original log. Always keep it.
- `actual_tool` — what the bot did on the day you found it. Never graded; it's
  the fossil that explains why this row exists.
- `why` — **if you cannot write this, do not save the row.**

Two rows are already done for you in `dataset_from_logs.jsonl`
(from `tr_004` and `tr_008`). Match that shape.

## Step 5 — Run it

```bash
python3 ../topic-09-datasets/eval.py --agent llm --dataset dataset_from_logs.jsonl
```

Expect some to fail. That's the point — these came from real failures.

---

## Target

**10–14 rows.** Make sure you cover these, because each teaches something
different:

| what to look for | traces to check |
|---|---|
| a plain wrong tool | tr_004 ✅ done |
| a successful prompt injection | tr_008 ✅ done |
| the bot invented information | tr_029 |
| the bot leaked another customer's data | tr_023 |
| a destructive action on a guess | tr_005 |
| self-correction ignored | tr_024 |
| a tool called with an empty argument | tr_025 |
| out of scope, but the bot acted anyway | tr_020 |
| intent with no keyword | tr_014 |
| typos with no `#` on the id | tr_026 |
| an infrastructure error, not a model error | tr_013 |
| PII in the input | tr_030 |
| a complaint where the bot was **right** | tr_022 |

## Traps to avoid

- **Don't label from `tool_calls`.** Copying what the bot did as the expected
  answer means testing that the bot agrees with itself. Decide independently.
- **A single turn from a conversation is not a test case.** `tr_010` is
  `"cancel it"` — meaningless alone. It needs turn 1 as context, which our
  single-turn harness can't hold. Note it and skip it (that's Topic 13).
- **Don't harvest only disasters.** If every row is a catastrophe, your score
  looks terrible even when the bot is fine. Keep a few ordinary successes.
- **`tr_012` isn't a wrong-tool bug** — the tool was right, it was called twice.
  Your harness records that as `extra_tool_calls` but doesn't grade it yet.
  Different bug class, needs a different field (`max_tool_calls`).

---

When you're done, open `ANSWER_KEY.md` and argue with me. Some of my labels are
defensible rather than certain, and I've marked which.
