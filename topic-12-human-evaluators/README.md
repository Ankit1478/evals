# Topic 12 — Human Evaluators

Use this project to learn how a human reviews AI answers before they become trusted evaluation data.

This is a local, production-shaped workflow:

```text
AI output → review queue → human decision → audit trail → approved eval dataset
```

## Start

```bash
cd /Users/ankitraj/Developer/evals-roadmap/topic-12-human-evaluators
python3 review.py --bootstrap
python3 review.py --next
```

`--next` shows one unanswered review task. Read the customer question and the AI answer.

## Interactive terminal mode

For an easier review experience, run:

```bash
python3 review.py --interactive
```

The terminal asks for your name, shows a task, and lets you press `a` to approve, `r` to reject, `e` to escalate, `s` to skip, or `q` to quit. It also asks you to write a short reason for every decision.

## Make your decision

Approve a good and safe answer:

```bash
python3 review.py --approve task-001 --reviewer ankit --notes "Correct action and order id."
```

Reject an incorrect or unsafe answer:

```bash
python3 review.py --reject task-002 --reviewer ankit --notes "Wrong order id."
```

Escalate an ambiguous case when the policy does not make the correct answer clear:

```bash
python3 review.py --escalate task-003 --reviewer ankit --notes "Policy does not cover this case."
```

Then check progress:

```bash
python3 review.py --stats
python3 review.py --list
```

Export only approved records as an eval dataset:

```bash
python3 review.py --export-approved approved_dataset.jsonl
```

## What the human is judging

For each task, decide these things:

1. **Correctness:** Did the AI choose the right action?
2. **Safety:** Did it avoid an unsafe action?
3. **Policy:** Is the decision supported by the written policy?
4. **Label quality:** Is the task clear enough to become a future test case?

“Escalate” is important. A reviewer should not guess when the policy is unclear. A good review system turns disagreement into a policy or labeling task.

## Production implementation

This lesson uses local SQLite so it is easy to run. A real production system needs:

- Authenticated reviewers and role-based access.
- An append-only review audit log: reviewer, time, decision, rubric version, and notes.
- PII redaction before tasks reach reviewers.
- Double review for high-risk tasks; disagreements go to an adjudicator.
- Random quality-control tasks with known answers to measure reviewer quality.
- A versioned rubric. If policy changes, label the policy version.
- Sampling rules: random production samples for realism plus oversampling of risky cases.
- Clear retention and access policies for customer data.

The database created here has the same core separation: `review_tasks` contains the work queue, and `reviews` contains the audit trail. A task can receive only one decision in this small lesson; production systems commonly allow multiple independent reviews.
