# Eval dataset fields — production reference

Legend: ✅ our `eval.py` reads it · ⬜ not implemented yet · 👤 humans only

Nobody uses all of these. Start with the ✅ set, add a group when you feel the pain.

---

## 1. Identity & lifecycle
| field | meaning |
|---|---|
| ✅ `id` | stable unique name. Never renumber — you cite it in tickets for months. |
| ⬜ `split` | `dev` (tune against) vs `holdout` (touch rarely). Prevents overfitting. |
| ⬜ `enabled` / `skip` | turn a row off without deleting it |
| ⬜ `quarantine` | known-flaky: run it, report it, don't let it fail the build |
| ⬜ `known_failure` | expected to fail today. Alerts you when it starts *passing*. |
| ⬜ `deprecated_at` | product changed; row kept for history |
| 👤 `created_at` / `updated_at` | when written / last relabelled |
| 👤 `owner` | who to ask when this row is disputed |

## 2. Input
| field | meaning |
|---|---|
| ✅ `input` | the user message (single turn) |
| ⬜ `messages` | full conversation for multi-turn evals (Topic 13) |
| ⬜ `context` / `retrieved_docs` | documents the model was given (RAG evals, Topic 9→10) |
| ⬜ `tool_state` / `fixtures` | starting world state: which orders exist, DB seed |
| ⬜ `user_profile` | tier, locale, permissions — behavior often depends on it |
| ⬜ `attachments` | image/audio/file inputs (multimodal) |
| ⬜ `seed` | for reproducible sampling |

## 3. Expected behaviour — actions
| field | meaning |
|---|---|
| ✅ `expected_tool` | the one tool to call. `null` = call nothing. |
| ✅ `expected_args` | argument values |
| ✅ `arg_match` | per-field strictness: `exact` / `fuzzy` / `ignore` |
| ⬜ `expected_tools` | ordered **sequence** for multi-step agents (trajectory, Topic 12) |
| ⬜ `allowed_tools` | any of these is acceptable |
| ⬜ `forbidden_tools` | must never be called — the safety rail |
| ⬜ `max_tool_calls` | budget; catches loops |
| ⬜ `must_not` | side effects that must not happen (Topic 39) |

## 4. Expected behaviour — text
| field | meaning |
|---|---|
| ✅ `reply_contains` | these words must appear |
| ✅ `reply_not_contains` | these words must never appear |
| ⬜ `reply_regex` | pattern match |
| ⬜ `expected_output` | reference answer (graded fuzzy / embedding / judge) |
| ⬜ `acceptable_outputs` | list of valid answers |
| ⬜ `expected_citations` | which sources must be cited (RAG) |
| ⬜ `expected_refusal` | must decline, and roughly why |
| ⬜ `json_schema` | structured output must validate against this |

## 5. Grading config
| field | meaning |
|---|---|
| ⬜ `grader` | `code` / `llm_judge` / `human` — how this row is scored |
| ⬜ `rubric` | scoring guide for a judge (Topic 6) |
| ⬜ `judge_model` | pin the judge; changing it changes your scores |
| ⬜ `threshold` | pass mark when scoring is a scale, not pass/fail |
| ⬜ `weight` | some rows matter more (a wrongly cancelled order ≠ a typo) |
| ⬜ `partial_credit` | allow 0.5 instead of only 0/1 |

## 6. Slicing (the field group that earns its keep)
| field | meaning |
|---|---|
| ✅ `tags` | free-form slices: `negation`, `injection`, `typo`… |
| ⬜ `category` / `intent` | primary bucket, exactly one per row |
| ⬜ `difficulty` | `easy` / `medium` / `hard` — track the hard slice separately |
| ⬜ `severity` | how bad is failure here: `cosmetic` → `financial` → `safety` |
| ⬜ `language` | measure non-English separately or it hides in the average |
| ⬜ `customer_tier` | enterprise failures cost more than free-tier ones |

## 7. Provenance & governance (Topic 44)
| field | meaning |
|---|---|
| ✅ `source` | `handwritten` / `production_log` / `synthetic` / `red_team` |
| ✅ `why` | the policy line justifying the label. **Can't write it → drop the row.** |
| ⬜ `source_trace_id` | link back to the real production trace |
| ⬜ `labeled_by` | which human decided this |
| ⬜ `label_confidence` | flag rows annotators argued about |
| ⬜ `reviewed_by` / `reviewed_at` | audit trail |
| ⬜ `policy_ref` | the doc/section this label comes from |
| ⬜ `contains_pii` | scrub before sharing (Topic 44) |
| ⬜ `regression_of` | the bug/ticket this row was born from |

## 8. Performance budgets (Topic 16)
| field | meaning |
|---|---|
| ⬜ `max_latency_ms` | fail if slower — correctness isn't the only requirement |
| ⬜ `max_cost_usd` | fail if too expensive |
| ⬜ `max_tokens` | catch runaway generation |
| ⬜ `timeout_ms` | per-row override |

---

## Start here
```json
{
  "id": "sup-006",
  "input": "Don't cancel my order - I just want to know where it is. It's #111",
  "expected_tool": "track_order",
  "expected_args": {"order_id": "111"},
  "tags": ["negation"],
  "source": "production_log",
  "why": "Policy: act on final intent, not on earlier words."
}
```
7 fields. Add more only when a real problem demands it.

## Add next, in this order
1. `split` — the moment you start tuning prompts against the dataset
2. `severity` + `weight` — so a wrongly cancelled order outranks a typo
3. `forbidden_tools` / `must_not` — side effects cost real money
4. `expected_tools` (sequence) — when the agent takes more than one step
5. `grader` + `rubric` — when `==` stops working and you need a judge

## Trap
Unknown fields are **silently ignored**. Writing `expected_arguments` instead of
`expected_args` produces a *fake failure* on a perfectly good answer. Whatever
harness you use, verify which names it actually reads.
