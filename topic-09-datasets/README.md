# Topic 9 — Evaluation Datasets

Two files matter here:

| file | what it is |
|---|---|
| `dataset.jsonl` | **the asset.** 24 labelled test cases. You will edit this constantly. |
| `eval.py` | the harness. Read it once, then mostly leave it alone. |

Everything runs on real Azure OpenAI (`gpt-5.6-luna`), no pip installs.

---

## Run it

```bash
python3 eval.py --agent keyword          # dumb baseline, free, instant
python3 eval.py --agent llm              # the real thing
python3 eval.py --agent llm --tag negation      # one slice only
python3 eval.py --agent llm --id sup-004        # one case, for debugging
python3 eval.py --agent llm --repeat 3 --temperature 1.0   # flakiness check
python3 eval.py --agent llm --gate 0.85         # CI mode: exit 1 if below
python3 eval.py --agent llm --no-cache          # force fresh calls
```

Responses are cached in `.cache/` keyed by the exact request, so re-running an
unchanged dataset is free and instant. Change the prompt or the input and only
the affected rows re-call.

---

## Anatomy of a row

```json
{
  "id": "sup-006",
  "input": "Don't cancel my order - I just want to know where it is. It's #111",
  "expected_tool": "track_order",
  "expected_args": {"order_id": "111"},
  "arg_match": {"new_address": "fuzzy"},
  "tags": ["negation"],
  "source": "production_log",
  "why": "Policy: act on final intent, not on earlier words."
}
```

| field | purpose |
|---|---|
| `id` | stable handle. Never reuse or renumber — you track failures by id over months. |
| `input` | the real user turn, not a cleaned-up version of it |
| `expected_tool` | `null` means **"call no tool"**. 9 of 24 rows are like this on purpose. |
| `expected_args` | graded **only when the tool was right**. Wrong-tool args are a meaningless number. |
| `arg_match` | per-field grader: `exact` (default), `fuzzy` (free text), `ignore` |
| `tags` | the slices. This is where the value is. |
| `source` | `handwritten` / `production_log` / `red_team` / `synthetic` — provenance for auditing labels |
| `why` | the policy line that justifies the label. **If you can't write this, the row is ambiguous.** |

The `why` field is not decoration. `eval.py`'s `SYSTEM_PROMPT` is the spec;
every label must be defensible from it. A label you can't justify is an opinion,
and you'll spend weeks arguing about it later.

---

## What the report actually tells you

The headline number is the **least** useful line. Read in this order:

1. **`!! N cases errored`** — if present, stop. An incomplete run is not a result.
2. **BY SLICE** — sorted worst-first. This is your work queue.
3. **CONFUSION** — *what* it says instead. `update_address -> no_tool` is a very
   different bug from `update_address -> track_order`.
4. **FAILURES** — read every single one. This is non-optional.
5. **HEADLINE + CI** — last, and always with the interval attached.

---

## The exercises

**1. Baseline vs. model.** Run both agents. The keyword agent scores ~46%, the
LLM ~88%. If that gap were 5 points instead of 42, you wouldn't have an AI
product — you'd have an expensive regex. Always publish the baseline.

**2. Triage the 3 failures — are they model bugs or dataset bugs?**
This is the core skill of the topic. Two of the three are arguably *your* fault:

- `sup-004` — the address **is** in the message; the model asked for it anyway.
  → model bug.
- `sup-017` — no new address was given, and `update_address` *requires* one.
  Asking is correct. → **dataset bug: the label is wrong.**
- `sup-013` — "I want my money back" when no refund exists. The policy never
  says what to do. → **spec bug: fix `SYSTEM_PROMPT`, then relabel.**

Roughly a third of early eval failures are bad labels. If you "fix" the model to
match a wrong label, you have made the system worse and the number better.

**3. Fix the spec, not the score.** Edit `SYSTEM_PROMPT` to cover the refund
case. Re-run. Did other slices regress? That's the real question.

**4. Grow the dataset from failures.** Every failure becomes 2–3 new rows: the
original, plus variations that probe the same weakness. `sup-004` should spawn
rows with the address at the start, mid-sentence, and in a second sentence.

**5. Check the interval.** `--tag negation` gives you 100%… on n=2, CI
`[43.8%, 100%]`. That is not evidence of anything. Get each slice you care about
to n≥10 before you believe its number.

**6. Break the grader on purpose.** Set every `expected_tool` to `cancel_order`
and watch accuracy jump. Any metric that rewards a constant predictor is broken.

---

## The traps this file is built to teach

- **Labeling after the fact.** Never write `expected` by looking at the output.
  That measures "does the model agree with itself."
- **No negative cases.** Without the 9 `expected_tool: null` rows, "always call
  a tool" would score well.
- **Aggregate accuracy.** 88% hides `address: 0%`. Slices or nothing.
- **Errors scored as results.** This harness originally marked `sup-016` as
  PASS because the API call *failed* and returned no tool call — on a row that
  expects no tool call. Infrastructure failures must leave the denominator.
- **Near-duplicates.** 40 paraphrases of one intent is n=1 in a wig, and it
  silently reweights your average.
- **No holdout.** Tuning prompts against all 24 rows overfits to them. Split off
  a holdout you touch rarely.

---

## Next

Topic 5 (graders) — `grade_args` currently does exact/fuzzy string matching.
That breaks the moment expectations stop being strings, which is where
LLM-as-a-judge comes in.
