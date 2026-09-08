# AI Evals Mastery Plan

This repository is the practical companion to the 228-topic *AI Evals
Engineering Handbook*. The goal is not to merely finish the PDF. The goal is
to produce evidence that you can design, implement, test, interpret, and ship
evaluations.

## The six-stage route

| Stage | PDF topics | Practical milestone |
|---|---:|---|
| 1. Measurement basics | 001-036 | A reviewed dataset and a tested layered grader |
| 2. Honest analysis | 037-059 | Confusion matrix, uncertainty estimate, and decomposed rubric |
| 3. Reliable agents | 060-114 | RAG diagnosis, state verification, tool recovery, and attack tests |
| 4. Production decisions | 115-168 | Cost/latency report, reproducible harness, release gates, incident feedback |
| 5. Specialization | 169-218 | A narrow benchmark and one task-specific evaluation |
| 6. Demonstrate skill | 219-228 | A reproducible portfolio project and honest technical case study |

## SOP for every topic

Use the same learning loop for all 228 topics:

1. **Recall** - explain the topic in your own words before reading.
2. **Define** - write the evaluation target and the decision the score informs.
3. **Specify evidence** - state exactly what the harness must observe.
4. **Implement** - build the smallest runnable example without external APIs.
5. **Test the grader** - include at least one known pass, known product failure,
   and malformed-evidence case when applicable.
6. **Run and inspect** - read case-level reasons, not only the aggregate score.
7. **Modify** - introduce one realistic bug and confirm the evaluation catches it.
8. **Explain limitations** - write what the evaluation does *not* prove.
9. **Record mastery** - check the topic only if you can reproduce the work
   without copying it.

## Definition of mastery

A topic is mastered when you can answer all five questions:

- What intended outcome are we measuring?
- What trusted evidence proves it?
- What must never happen?
- How can the grader itself be wrong?
- What engineering or release decision will the result change?

Reading is not mastery. A high score is also not mastery unless the cases,
grader, environment, and interpretation are defensible.

## Recommended working rhythm

For one session, spend approximately 15 minutes recalling/revising, 25 minutes
studying two or three related topics, and 20-40 minutes coding and investigating
a failure. Prefer depth over a fixed daily topic count.

Each practical topic folder should contain:

```text
topic-NNN-name/
├── README.md          # concept, SOP, commands, interpretation, exercises
├── cases.jsonl        # versionable evaluation cases
├── evaluate.py        # system-under-test + grader + report (initial lessons)
└── test_evaluate.py   # tests of the measurement system
```

Later lessons will split the system, harness, graders, fixtures, and reporting
into separate modules as the architecture becomes more realistic.

## Progress tracker

- [x] Topics 001-008 - Foundations (single-file practical lab)
- [ ] Topics 009-021 - Evaluation datasets
- [ ] Topics 022-036 - Graders and rubrics
- [ ] Topics 037-048 - Metrics and statistics
- [ ] Topics 049-059 - LLM output evaluation
- [ ] Topics 060-070 - RAG evaluation
- [ ] Topics 071-090 - Agent evaluation
- [ ] Topics 091-099 - Multi-agent evaluation
- [ ] Topics 100-114 - Safety and security
- [ ] Topics 115-125 - Performance and business metrics
- [ ] Topics 126-135 - Evaluation environments
- [ ] Topics 136-145 - Offline and online evaluation
- [ ] Topics 146-155 - Observability and debugging
- [ ] Topics 156-168 - Production engineering
- [ ] Topics 169-179 - Benchmarks
- [ ] Topics 180-193 - Specialized evaluations
- [ ] Topics 194-207 - Advanced research
- [ ] Topics 208-218 - Tools and frameworks
- [ ] Topics 219-228 - Career and portfolio projects

Existing folders in this repository contain useful work from earlier sessions.
The new three-digit folder names follow the PDF's exact numbering so that topic
numbers remain unambiguous.
