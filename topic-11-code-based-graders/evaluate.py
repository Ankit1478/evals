#!/usr/bin/env python3
"""A small, dependency-free example of a code-based grader."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def grade(case):
    """Return PASS/FAIL plus every reason. This function is the grader."""
    reasons = []
    try:
        answer = json.loads(case["model_output"])
    except json.JSONDecodeError:
        return False, ["output is not valid JSON"]

    # Check 1: output has the required JSON fields.
    for field in ("action", "order_id", "message"):
        if field not in answer:
            reasons.append("missing field: %s" % field)

    # Check 2: action is valid and correct for this test case.
    allowed_actions = {"track_order", "cancel_order"}
    if answer.get("action") not in allowed_actions:
        reasons.append("action is not allowed")
    elif answer.get("action") != case["expected_action"]:
        reasons.append("wrong action: expected %s" % case["expected_action"])

    # Check 3: the model extracted the right order number.
    if str(answer.get("order_id")) != str(case["expected_order_id"]):
        reasons.append("wrong order id: expected %s" % case["expected_order_id"])

    # Check 4 and 5: message must contain and must not contain certain words.
    message = str(answer.get("message", "")).lower()
    for word in case.get("must_include", []):
        if word.lower() not in message:
            reasons.append("message must include: %s" % word)
    for word in case.get("must_not_include", []):
        if word.lower() in message:
            reasons.append("message must not include: %s" % word)

    return not reasons, reasons


def main():
    path = os.path.join(HERE, "cases.jsonl")
    cases = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    passed = 0
    for case in cases:
        ok, reasons = grade(case)
        passed += ok
        print("%s  %s" % ("PASS" if ok else "FAIL", case["id"]))
        for reason in reasons:
            print("  - " + reason)
    print("\nScore: %d/%d passed" % (passed, len(cases)))


if __name__ == "__main__":
    main()
