# Notes — Topic 9: Evaluation Datasets

## Core idea
An eval dataset is a **list of questions with pre-written correct answers**.
Like an exam answer key. You write it *before* the model runs.

```
dataset.jsonl ──► eval.py ──► LLM ──► answer
                     │                   │
                     └──── compare ──────┘
                             ↓
                          ✓ or ✗
```
Verification is literally one line: `pred["tool"] == case["expected_tool"]`

## A dataset is not a test suite
- Test suite = "this must be true"
- Eval = **a sample of user behavior**. The score is an *estimate* with error bars.
- 21/24 is not "87.5%". It is "87.5%, could be 69%–96%".

## Anatomy of one row
| field | note |
|---|---|
| `id` | never reuse or renumber — you track failures by id for months |
| `input` | the **real** user message, typos and all |
| `expected_tool` | `null` = "do nothing". 12 of my 27 rows are `null`. |
| `expected_args` | graded **only if the tool was right** |
| `tags` | the slices — where the real value is |
| `source` | handwritten / production_log / red_team / synthetic |
| `why` | the policy line justifying the label. Can't write it? Row is ambiguous. |

## The 3 verdicts per row (not 1)
1. **tool** — did it pick the right action?
2. **args** — right parameters? (only scored if tool was right)
3. **reply** — did it say the right thing? (for `null` rows this is all you have)

Collapsing these into one boolean throws away the diagnosis.
Wrong tool ≠ right tool with wrong id. Different bugs, different fixes.

## Where cases come from (best → worst)
1. **Production logs** — real distribution, unbeatable
2. **Bug reports** — a real failure becomes a permanent row (the flywheel)
3. **Handwritten** — how you bootstrap with no traffic
4. **Synthetic** — good for *perturbing* existing rows (typos, casing, translation);
   bad for inventing intents (LLMs generate what they already handle → fake score)
5. **Red team** — deliberately hostile

**Inputs can be automated. Labels cannot.** Labelling is the irreducible human work.

## Coverage: build a grid, not a list
Not "write 20 examples." Fill cells:
`happy / negation / out-of-scope / typo / casing / missing-arg / ambiguous / multi-intent / injection`

The two cells beginners always skip:
- **negative cases** — correct answer is *do nothing*. Without them, "always call a tool" scores well.
- **out-of-scope** — must refuse or escalate.

## One idea → a family of rows
Test the *rule*, not a point. My example:
```
no id, no address  → must ask for both
id, no address     → must ask for the address
id + address       → must act
```
The interesting behavior is always at the boundary.

## Reading a report — in this order
1. `!! N cases errored` → **stop.** Incomplete run ≠ result.
2. **BY SLICE** (worst first) → your work queue
3. **CONFUSION** → *what* it said instead. `update_address → no_tool` ≠ `→ track_order`
4. **FAILURES** → read every one
5. **Headline + CI** → last, always with the interval

**The headline number is the least useful line in the report.**
87.5% overall hid `address: 0%`.

## A ✗ has TWO meanings
1. The LLM is wrong
2. **Your answer key is wrong**

My 3 failures triaged:
| case | fault | why |
|---|---|---|
| sup-004 | **model** | address WAS in the message, it asked anyway |
| sup-017 | **my dataset** | no address given, tool requires one → asking is correct |
| sup-013 | **my spec** | policy never covered "I want my money back" |

~⅓ of early failures are bad labels. Fix a model to match a wrong label and
the number goes up while the system gets worse.

## Traps
- **Labelling after the fact** — writing `expected` by looking at the output.
  That measures "does the model agree with itself."
- **Errors scored as results** — my harness marked the injection case PASS because
  the API call *failed* and returned no tool call, on a row expecting no tool call.
  A silent false pass. Infra failures must leave the denominator.
- **Aggregate accuracy** — hides everything. Slices or nothing.
- **Near-duplicates** — 40 paraphrases of one intent is n=1 in a wig, and it
  silently reweights the average.
- **Unbalanced labels** — if 90% of rows are one tool, a constant predictor "wins".
- **No holdout** — tuning prompts against every row overfits to them.
- **Stale labels** — product changed, dataset didn't. Datasets need owners + versions.

## Size
"10–20 to start" = smoke test. What matters is **n per slice**, not n total.
- ~10/slice → detect gross breakage
- ~30/slice → trust the percentage
- always print the CI so you can't fool yourself

4/4 looked perfect. CI said `[51%, 100%]`. **Small n makes you confident, not correct.**

## Always ship a baseline
| agent | strict |
|---|---|
| keyword regex | 45.8% |
| gpt-5.6-luna | 87.5% |

42-point gap = a real product. A 5-point gap = an expensive regex.
Never publish an LLM score without a dumb baseline beside it.

## Passing tests are tripwires
Don't delete a row because it passes. It exists so that when someone edits the
prompt next week, the thing that used to work doesn't silently break.

---
**Commands**
```bash
python3 eval.py --agent keyword          # free baseline
python3 eval.py --agent llm              # real run (cached after first)
python3 eval.py --agent llm --id sup-017 # debug one case
python3 eval.py --agent llm --tag negation
python3 eval.py --agent llm --repeat 3 --temperature 1.0   # flakiness
python3 eval.py --agent llm --gate 0.85  # CI: exit 1 if below
python3 eval.py --agent llm --no-cache   # after editing SYSTEM_PROMPT
```
