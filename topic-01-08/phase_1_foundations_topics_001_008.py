#!/usr/bin/env python3
"""Phase 1A: AI evaluation foundations, PDF Topics 001-008.

This practical combines the lesson, mock AI systems, grader, evaluation
runner, release decision, and tests. It loads cases from dataset.jsonl and
uses only the Python standard library.

The JSONL dataset contains regression and capability cases across four
severity levels. It includes ordinary requests, missing information,
distracting numbers, capitalization, whitespace, hashes, numeric IDs, and
alphanumeric IDs. Expected values belong to the evaluator, not the agent.

TOPIC 001 - WHAT EVALS ARE
An eval is a repeatable experiment:
    input -> system under test -> observed evidence -> grader -> score
Keep the system under test separate from the measurement system.

TOPIC 002 - WHY AI SYSTEMS NEED EVALS
AI behavior can change with prompts, context, sampling, and model versions.
Evaluate changes across a dataset instead of trusting a few good demos.

TOPIC 003 - SOFTWARE TESTS VS AI EVALUATIONS
Traditional tests often assert one exact deterministic result. AI evals may
accept several semantically correct outputs and measure quality, behavior, or
safety. The grader itself still needs ordinary deterministic tests.

TOPIC 004 - MODEL, APPLICATION, AGENT, AND SYSTEM EVALS
Choose the evaluation level explicitly:
    model       raw response quality
    application prompt + retrieval + formatting
    agent       decisions, tool calls, state, and final answer
    system      end-to-end behavior including services and humans
This lab evaluates agent-level structured decisions.

TOPIC 005 - EVALUATION LIFECYCLE
Define the decision, create cases, run a versioned system, grade evidence,
analyze failures, make a release decision, and add discoveries to the suite.

TOPIC 006 - CAPABILITY VS REGRESSION EVALS
Capability cases ask what the system can do and expose its boundary.
Regression cases protect behavior that already works from breaking later.

TOPIC 007 - DEFINING SUCCESS CRITERIA
Set thresholds before seeing candidate results. This lab requires a minimum
pass rate and zero critical failures. Averages must not hide severe failures.

TOPIC 008 - SELECTING WHAT TO EVALUATE
Prioritize behavior with high impact, likely failure, and uncertainty. Do not
spend most of the budget measuring what is easiest instead of what is risky.

Run:
    python3 phase_1_foundations_topics_001_008.py --lesson
    python3 phase_1_foundations_topics_001_008.py --run
    python3 phase_1_foundations_topics_001_008.py --test

PRACTICE SOP
1. Run --lesson and explain each topic without looking at the text.
2. Run --run and investigate the v1 critical failure.
3. Run --test; these tests validate the grader and release logic.
4. Add one regression case and one capability case to CASES.
5. Break agent_v2 deliberately and confirm the evaluation catches the bug.
6. Restore it, then raise or lower the predeclared release threshold.
7. Write what this tiny synthetic evaluation cannot prove about production.
"""

from __future__ import annotations

import argparse
import json
import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    user_input: str
    expected_action: str
    expected_order_id: str | None
    suite: str
    severity: str


DATASET_PATH = Path(__file__).with_name("dataset.jsonl")


def load_cases(path: Path = DATASET_PATH) -> tuple[EvalCase, ...]:
    """Load evaluator-owned JSONL cases from disk."""

    cases = []
    with path.open(encoding="utf-8") as dataset:
        for line_number, line in enumerate(dataset, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                cases.append(EvalCase(**row))
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(f"Invalid dataset row at line {line_number}: {error}") from error
    return tuple(cases)


CASES = load_cases()


def agent_v1(user_input: str) -> dict[str, Any]:
    """A flawed baseline that treats the first number as the order ID."""

#   User 456 wants to cancel order 123
#   agent_v1() selects 456 because it is the first number.
#   That is wrong. The correct order ID is 123.
#   This flawed implementation represents the baseline system.

    match = re.search(r"\b\d+\b", user_input)
    return _choose_action(user_input, match.group(0) if match else None)


def agent_v2(user_input: str) -> dict[str, Any]:
    """A candidate that extracts an identifier specifically after 'order'."""

#  User 456 wants to cancel order 123
#   the captured group is 123, not 456.
#   For:
#   Cancel order #AB-123
#   the captured group is AB-123.
#   match.group(1) returns the content inside the parentheses. In agent_v1(), group(0) returns the complete match.

    match = re.search(r"\border\s+#?([A-Za-z0-9-]+)\b", user_input, re.IGNORECASE)
    return _choose_action(user_input, match.group(1) if match else None)


def _choose_action(user_input: str, order_id: str | None) -> dict[str, Any]:
    lower = user_input.lower()
    if "cancel" in lower and order_id is not None:
        action = "cancel_order"
    elif "track" in lower and order_id is not None:
        action = "track_order"
    else:
        action = "ask_clarification"
    return {"action": action, "order_id": order_id}

# This makes matching case-insensitive.
#   The decision rules are:
#   contains "cancel" + has order ID → cancel_order
#   contains "track" + has order ID  → track_order
#   otherwise                        → ask_clarification
#   The output is structured evidence:
#   {
#       "action": "cancel_order",
#       "order_id": "123"
#   }

def grade(case: EvalCase, actual: Any) -> dict[str, Any]:
    """ this will compare with the actual accepted answer and the agent's answer."""

    if not isinstance(actual, dict):
        return {"status": "error", "passed": False, "reasons": ["output is not an object"]}

    missing = [field for field in ("action", "order_id") if field not in actual]
    if missing:
        return {
            "status": "error",
            "passed": False,
            "reasons": [f"missing evidence fields: {', '.join(missing)}"],
        }

    expected = {"action": case.expected_action, "order_id": case.expected_order_id}
    reasons = [
        f"{field}: expected {expected[field]!r}, got {actual[field]!r}"
        for field in expected
        if actual[field] != expected[field]
    ]
    return {"status": "graded", "passed": not reasons, "reasons": reasons}


def evaluate(
    version: str, system: Callable[[str], dict[str, Any]]
) -> dict[str, Any]:
    """This function will help to mark the result. The `greater` function will give `correct` or `false`, and the `evaluate` function will give the mark."""

    results = []
    for case in CASES:
        actual = system(case.user_input)
        result = grade(case, actual)
        results.append(
            {
                "case_id": case.case_id,
                "suite": case.suite,
                "severity": case.severity,
                "actual": actual,
                **result,
            }
        )

    graded = [row for row in results if row["status"] == "graded"]
    passes = sum(row["passed"] for row in graded)
    critical_failures = sum(
        not row["passed"] and row["severity"] == "critical" for row in graded
    )
    return {
        "version": version,
        "results": results,
        "pass_rate": passes / len(graded) if graded else 0.0,
        "critical_failures": critical_failures,
        "evaluation_errors": len(results) - len(graded),
    }


def release_decision(
    report: dict[str, Any], minimum_pass_rate: float = 1.0
) -> dict[str, Any]:
    """the rule: pass or fail the student."""

    reasons = []
    if report["pass_rate"] < minimum_pass_rate:
        reasons.append("pass rate below threshold")
    if report["critical_failures"]:
        reasons.append("critical failure")
    if report["evaluation_errors"]:
        reasons.append("invalid evaluation evidence")
    return {"ship": not reasons, "reasons": reasons}


def prioritize_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank candidate behaviors by impact x likelihood x uncertainty."""

    ranked = [
        {
            **target,
            "priority": target["impact"] * target["likelihood"] * target["uncertainty"],
        }
        for target in targets
    ]
    return sorted(ranked, key=lambda target: target["priority"], reverse=True)


class FoundationTests(unittest.TestCase):
    def test_jsonl_dataset_loads_real_cases(self):
        loaded = load_cases()
        self.assertEqual(len(loaded), 10)
        self.assertEqual(loaded[0].case_id, "track-basic")
        self.assertEqual(loaded[5].expected_order_id, "AB-123")

    def test_dataset_has_unique_ids_and_broad_coverage(self):
        case_ids = [case.case_id for case in CASES]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertGreaterEqual(len(CASES), 10)
        self.assertEqual({case.suite for case in CASES}, {"capability", "regression"})
        self.assertEqual(
            {case.severity for case in CASES},
            {"low", "medium", "high", "critical"},
        )

    def test_known_correct_behavior_passes(self):
        case = CASES[0]
        result = grade(case, {"action": "track_order", "order_id": "123"})
        self.assertEqual((result["status"], result["passed"]), ("graded", True))

    def test_wrong_order_is_a_product_failure(self):
        case = CASES[2]
        result = grade(case, {"action": "cancel_order", "order_id": "456"})
        self.assertEqual((result["status"], result["passed"]), ("graded", False))

    def test_missing_evidence_is_an_evaluation_error(self):
        result = grade(CASES[1], {"action": "cancel_order"})
        self.assertEqual((result["status"], result["passed"]), ("error", False))

    def test_v1_fails_the_distractor_case(self):
        report = evaluate("v1", agent_v1)
        distractor = next(row for row in report["results"] if row["case_id"] == "cancel-distractor")
        self.assertFalse(distractor["passed"])

    def test_v2_passes_all_cases(self):
        report = evaluate("v2", agent_v2)
        self.assertEqual(report["pass_rate"], 1.0)

    def test_critical_failure_blocks_release_even_if_threshold_is_low(self):
        decision = release_decision(evaluate("v1", agent_v1), minimum_pass_rate=0.5)
        self.assertFalse(decision["ship"])
        self.assertIn("critical failure", decision["reasons"])

    def test_risky_behavior_is_evaluated_first(self):
        targets = [
            {"name": "answer tone", "impact": 1, "likelihood": 2, "uncertainty": 2},
            {"name": "authorization", "impact": 5, "likelihood": 3, "uncertainty": 4},
        ]
        ranked = prioritize_targets(targets)
        self.assertEqual(ranked[0]["name"], "authorization")
        self.assertEqual(ranked[0]["priority"], 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--lesson", action="store_true", help="print Topics 001-008")
    mode.add_argument("--run", action="store_true", help="compare mock agent versions")
    mode.add_argument("--test", action="store_true", help="test the evaluation system")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.test:
        unittest.main(argv=[__file__], verbosity=2, exit=False)
    elif args.run:
        for version, system in (("v1", agent_v1), ("v2", agent_v2)):
            report = evaluate(version, system)
            decision = release_decision(report)
            print(f"\n{version}: pass_rate={report['pass_rate']:.0%}, ship={decision['ship']}")
            for row in report["results"]:
                label = "PASS" if row["passed"] else row["status"].upper()
                print(f"  {label:6} {row['case_id']} [{row['suite']}/{row['severity']}]")
                for reason in row["reasons"]:
                    print(f"         - {reason}")
            if decision["reasons"]:
                print(f"  Release blocked: {', '.join(decision['reasons'])}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
