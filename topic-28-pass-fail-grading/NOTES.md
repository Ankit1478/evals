# Notes — Topic 28: Pass/Fail Grading

## Core idea
One verdict per case: **PASS or FAIL**. No scale, no partial credit.

The boolean is trivial. What it forces you to decide is the topic:
where the bar is, which failures block, what a flaky answer scores, and
whether the grader is right.

```
output ──► [criterion, criterion, criterion] ──► all() ──► PASS | FAIL
                        │
                        └─► keep these. The verdict says "failed";
                            only the checks say "failed on order_id".
```

## Why binary at all
- A release decision **is** binary. Ship / don't ship. A 3.7 does not decide it.
- Two people agree on "did it call the right tool" far more than on "rate 1–5".
- A pass rate is a proportion → Wilson CI → you can reason about n.
- It composes: pass rates slice, average, and gate. Scores need a rubric first.

**The cost:** a near-miss and a catastrophe both score 0. Recover the lost
information with `severity` + blocking criteria, not with a scale.

## Compute many booleans, collapse last
`grade_output()` returns named checks. `verdict()` ANDs them at the very end.
Collapse early and you have a red build with nothing to debug.

Two rules:
- **Short-circuit on unparseable output.** One failure, not five. Otherwise your
  criterion counts are fiction.
- **Grade args only when the action was right.** The order id of a wrong action
  is a meaningless number. (Same rule as Topic 9.)

## Blocking vs advisory
```python
BLOCKING = {"valid_json","schema","action","order_id","must_not_include"}
```
Correctness + safety block. Style advises. **This is policy, not code** — it
needs an owner and a written justification.

| mode | pass rate | agreement w/ human |
|---|---|---|
| strict | 26.7% | 73.3% |
| blocking | 40.0% | **86.7%** |

Same outputs, same grader. **The stricter mode is the less accurate one.**
A pass rate means nothing without the mode and criteria list printed beside it.

## Gate on blocking failures, not the headline
95% pass rate with one leaked address does not ship. The gate should read the
blocking-failure count and the severity field, not the average.

## A ✗ has TWO meanings (again)
Topic 9 said a failure might be a bad label. Here it might be a **bad grader**.

| direction | grader | human | cost |
|---|---|---|---|
| false fail | FAIL | PASS | team stops trusting the eval, ignores red builds |
| false pass | PASS | FAIL | **it ships** |

Grade the grader. Treat FAIL as the positive class:
```
agreement 73.3%   precision-on-FAIL 72.7%   recall-on-FAIL 88.9%
```
Without `human_verdict` in the dataset, none of this is computable and a green
grader looks trustworthy.

## The hole code graders cannot close
`pf-008`: right action, right id, contains "track", no banned words, under the
length cap. **Every criterion passes.** It invented a tracking number.

`pf-016`: same shape — caught only because someone had already thought to put
the leaked name in `must_not_include`.

No change of *mode* finds these. The criteria set has a hole, and only a human
reading the reply found it. That is the boundary where LLM-as-a-judge starts.

## Criterion activity
Print, per criterion: how often it applied, how often it fired.
- **fires never** → tripwire (keep) or dead weight (delete). You cannot tell
  from the number. Try to break it on purpose.
- **fires on everything** → miscalibrated.

Nobody builds this report line. It is the cheapest way to find out that half
your rubric does nothing.

## Flakiness forces the question
`pf-013`: 5 samples, 3 pass.

| policy | verdict |
|---|---|
| `all` | FAIL ← default |
| `majority` | PASS |
| `any` | PASS |

Same data, opposite answers. `all` for anything touching money: a system that
cancels the wrong order 40% of the time is broken. "It usually works" is not a
passing grade. When a lenient policy carries a case, **say so on the line**.

## Errors are not failures
`pf-012` timed out. Excluded from the denominator.
FAIL invents a bug. PASS hides one. (Topic 9 learned this the hard way.)

## Thresholding is pass/fail in disguise
Cutting a 1–5 judge at ≥4 *is* a binary grader with a hidden, unstable knob.
Fine — but report the knob and how the rate moves at 3 and 5.

## Numbers from this folder
```
16 cases → 15 scored + 1 errored
strict    26.7% (4/15)  CI [10.9%, 52.0%]  9 blocking failures
blocking  40.0% (6/15)  CI [19.8%, 64.3%]
false fails  strict: pf-005, pf-007, pf-009   blocking: pf-005 only
false pass   pf-008 — survives every mode
```
n=15 → the CI spans 41 points. This is a smoke test, not a measurement.

---
**Commands**
```bash
python3 grade.py                          # strict
python3 grade.py --mode blocking          # safety-only bar
python3 grade.py --flaky-policy majority
python3 grade.py --severity safety,financial
python3 grade.py --id pf-008              # debug one case
python3 grade.py --gate 0.80              # exit 1 if below
```
