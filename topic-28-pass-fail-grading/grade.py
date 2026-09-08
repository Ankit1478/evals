#!/usr/bin/env python3
"""Topic 28 -- pass/fail (binary) grading.

Every case gets exactly one verdict: PASS or FAIL. No 1-5 scale, no partial
credit. The interesting part is not the boolean, it is everything you have to
decide in order to produce it honestly:

  * what the bar is, written down as named criteria
  * which criteria block a release and which are only advice
  * what a non-deterministic answer scores when it passes 3 times out of 5
  * whether the grader itself agrees with a human

Dependency-free. Outputs are pre-recorded in cases.jsonl, so this is free,
instant and deterministic -- the lesson is about the grader, not the agent.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases.jsonl")

# The order criteria are reported in: cheapest and most fundamental first.
CRITERIA = ["valid_json", "schema", "action", "order_id",
            "must_not_include", "must_include", "max_chars"]

# Blocking criteria are correctness and safety: failing one means you do not
# ship, whatever the headline pass rate says. The rest are advisory. This split
# is a policy decision, not a technical one -- it belongs in review, in writing.
BLOCKING = {"valid_json", "schema", "action", "order_id", "must_not_include"}

REQUIRED_FIELDS = ("action", "order_id", "message")
NO_ACTION = {None, "", "none", "null"}


# ----------------------------------------------------------------- the grader

def check(name, passed, detail=""):
    return {"name": name, "passed": passed, "detail": detail,
            "blocking": name in BLOCKING}


def grade_output(text, expect):
    """Return a list of per-criterion checks. Never returns a bare boolean:
    'it failed' is not a finding, 'it failed order_id' is."""
    checks = []

    try:
        answer = json.loads(text)
        if not isinstance(answer, dict):
            raise ValueError("not an object")
    except (ValueError, TypeError) as exc:
        # Short-circuit. If the output will not parse, every downstream check
        # would fail for the same single reason and inflate the failure counts.
        return [check("valid_json", False, "not parseable JSON (%s)" % exc)]
    checks.append(check("valid_json", True))

    missing = [f for f in REQUIRED_FIELDS if f not in answer]
    checks.append(check("schema", not missing,
                        ("missing: " + ", ".join(missing)) if missing else ""))

    action = answer.get("action")
    action_norm = action.lower() if isinstance(action, str) else action
    if "allowed_actions" in expect:
        # Disjunctive: several answers are acceptable. Pinning one expected
        # value here would fail a correct response.
        allowed = expect["allowed_actions"]
        ok = action_norm in [a.lower() for a in allowed]
        checks.append(check("action", ok,
                            "" if ok else "got %r, allowed %s" % (action, allowed)))
    elif expect.get("action") is None:
        ok = action_norm in NO_ACTION
        checks.append(check("action", ok,
                            "" if ok else "acted (%r) when it should not have" % action))
    else:
        # NOTE: raw string comparison. See exercise 3.
        ok = action == expect["action"]
        checks.append(check("action", ok,
                            "" if ok else "got %r, expected %r" % (action, expect["action"])))

    # Arguments are graded only when the action was right. The order id of a
    # wrongly chosen action is a meaningless number (same rule as Topic 9).
    action_ok = checks[-1]["passed"]
    if expect.get("order_id") is not None and action_ok:
        got = answer.get("order_id")
        ok = str(got) == str(expect["order_id"])
        checks.append(check("order_id", ok,
                            "" if ok else "got %r, expected %r" % (got, expect["order_id"])))

    message = str(answer.get("message", ""))
    low = message.lower()

    banned = [w for w in expect.get("must_not_include", []) if w.lower() in low]
    if expect.get("must_not_include"):
        checks.append(check("must_not_include", not banned,
                            ("found: " + ", ".join(banned)) if banned else ""))

    absent = [w for w in expect.get("must_include", []) if w.lower() not in low]
    if expect.get("must_include"):
        checks.append(check("must_include", not absent,
                            ("missing: " + ", ".join(absent)) if absent else ""))

    if expect.get("max_chars"):
        ok = len(message) <= expect["max_chars"]
        checks.append(check("max_chars", ok,
                            "" if ok else "%d chars > %d" % (len(message), expect["max_chars"])))

    return checks


def verdict(checks, mode):
    """Collapse many booleans into the one boolean. Do this LAST, and keep the
    checks -- the verdict tells you a case failed, the checks tell you why."""
    relevant = checks if mode == "strict" else [c for c in checks if c["blocking"]]
    return all(c["passed"] for c in relevant)


def grade_case(case, mode, flaky_policy):
    if case.get("error"):
        return {"id": case["id"], "errored": True, "error": case["error"],
                "checks": [], "verdict": None, "flaky": False,
                "human": case.get("human_verdict"), "case": case}

    outputs = case.get("samples") or [case["output"]]
    per_sample = [grade_output(o, case["expect"]) for o in outputs]
    verdicts = [verdict(c, mode) for c in per_sample]

    passes = sum(verdicts)
    if flaky_policy == "any":
        final = passes > 0
    elif flaky_policy == "majority":
        final = passes * 2 > len(verdicts)
    else:                                    # "all" -- one flake is a failure
        final = passes == len(verdicts)

    # Report the checks from the first failing sample, so a flaky case shows a
    # real reason rather than the reason from a run that happened to work.
    idx = next((i for i, v in enumerate(verdicts) if not v), 0)
    return {"id": case["id"], "errored": False, "checks": per_sample[idx],
            "verdict": final, "flaky": len(set(verdicts)) > 1,
            "samples": len(verdicts), "sample_passes": passes,
            "human": case.get("human_verdict"), "case": case}


# ------------------------------------------------------------------ reporting

def wilson(successes, n, z=1.96):
    """95% CI for a proportion. A pass rate is a proportion, so it always comes
    with an interval. 12/15 is not '80%', it is '80%, could be 55%-93%'."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / float(n)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def pct(x):
    return "%5.1f%%" % (100.0 * x)


def build_report(records, meta):
    errored = [r for r in records if r["errored"]]
    scored = [r for r in records if not r["errored"]]
    n = len(scored)
    passed = sum(1 for r in scored if r["verdict"])
    lo, hi = wilson(passed, n) if n else (0.0, 0.0)

    lines = []
    add = lines.append
    add("=" * 74)
    add(" PASS/FAIL REPORT  mode=%s  flaky-policy=%s  n=%d scored%s" % (
        meta["mode"], meta["flaky_policy"], n,
        (" (+%d errored)" % len(errored)) if errored else ""))
    add(" blocking criteria: %s" % ", ".join(sorted(BLOCKING)))
    add("=" * 74)

    if errored:
        add("")
        add("  !! %d case(s) produced no output and are EXCLUDED from every number" % len(errored))
        add("     below: %s" % ", ".join("%s (%s)" % (r["id"], r["error"]) for r in errored))
        add("     An infrastructure failure is not a model failure. Scoring it as")
        add("     FAIL invents a bug; scoring it as PASS hides one.")

    add("")
    add("HEADLINE")
    add("  pass rate ............ %s  (%d/%d)" % (pct(passed / float(n)) if n else "  n/a", passed, n))
    add("  95%% CI ............... [%s, %s]" % (pct(lo).strip(), pct(hi).strip()))
    blocked = [r for r in scored
               if any(not c["passed"] and c["blocking"] for c in r["checks"])]
    add("  blocking failures .... %d  <- gate on this, not on the pass rate" % len(blocked))

    # ---- which criterion is actually doing the work ----
    add("")
    add("CRITERION ACTIVITY  (applicable / fired = failed)")
    for name in CRITERIA:
        app = [r for r in scored if any(c["name"] == name for c in r["checks"])]
        fired = [r for r in app
                 if not next(c for c in r["checks"] if c["name"] == name)["passed"]]
        note = ""
        if app and not fired:
            note = "  <- never fires. Tripwire, or dead weight?"
        elif app and len(fired) == len(app):
            note = "  <- fails everything. Miscalibrated?"
        add("  %-18s %2d / %2d   %s%s" % (
            name, len(fired), len(app),
            "blocking" if name in BLOCKING else "advisory", note))

    # ---- per-case verdicts ----
    add("")
    add("VERDICTS")
    for r in scored:
        fails = [c for c in r["checks"] if not c["passed"]]
        tail = ""
        if r.get("flaky"):
            tail = "  [flaky %d/%d samples passed]" % (r["sample_passes"], r["samples"])
        shown = fails if not r["verdict"] else []
        add("  %s  %-8s %s%s" % ("PASS" if r["verdict"] else "FAIL", r["id"],
                                 ", ".join(c["name"] for c in shown) or "-", tail))
        for c in shown:
            if c["detail"]:
                add("           %s%s: %s" % (
                    "" if c["blocking"] else "(advisory) ", c["name"], c["detail"]))
        if r["verdict"] and r.get("flaky"):
            # Passed only because the policy tolerates flakes. Say so out loud.
            add("           passed under --flaky-policy=%s; %d sample(s) failed on: %s"
                % (meta["flaky_policy"], r["samples"] - r["sample_passes"],
                   ", ".join(c["name"] for c in fails)))

    # ---- the punchline: grade the grader ----
    audit = [r for r in scored if r["human"] in ("pass", "fail")]
    if audit:
        tp = [r for r in audit if not r["verdict"] and r["human"] == "fail"]
        fp = [r for r in audit if not r["verdict"] and r["human"] == "pass"]
        fn = [r for r in audit if r["verdict"] and r["human"] == "fail"]
        tn = [r for r in audit if r["verdict"] and r["human"] == "pass"]
        agree = len(tp) + len(tn)
        prec = len(tp) / float(len(tp) + len(fp)) if (tp or fp) else 0.0
        rec = len(tp) / float(len(tp) + len(fn)) if (tp or fn) else 0.0
        add("")
        add("GRADER vs HUMAN  (the grader is a classifier -- so evaluate it)")
        add("  agreement ............ %s  (%d/%d)" % (
            pct(agree / float(len(audit))), agree, len(audit)))
        add("  precision on FAIL .... %s  (of the fails it called, how many were real)" % pct(prec))
        add("  recall on FAIL ....... %s  (of the real fails, how many it caught)" % pct(rec))
        if fp:
            add("  FALSE FAILS  (grader says FAIL, human says PASS) -- these erode trust")
            for r in fp:
                add("    %-8s %s" % (r["id"], r["case"]["why"]))
        if fn:
            add("  FALSE PASSES (grader says PASS, human says FAIL) -- these ship")
            for r in fn:
                add("    %-8s %s" % (r["id"], r["case"]["why"]))

    return "\n".join(lines), {
        "n": n, "passed": passed,
        "pass_rate": (passed / float(n)) if n else 0.0,
        "ci": [lo, hi], "errored": len(errored),
        "blocking_failures": len(blocked)}


def main():
    p = argparse.ArgumentParser(description="Topic 28 pass/fail grading")
    p.add_argument("--mode", default="strict", choices=["strict", "blocking"],
                   help="strict = every criterion must pass. "
                        "blocking = only correctness/safety criteria count.")
    p.add_argument("--flaky-policy", default="all", choices=["all", "majority", "any"],
                   help="how to score a case with several samples (default: all)")
    p.add_argument("--id", default=None, help="comma-separated case ids")
    p.add_argument("--tag", default=None, help="comma-separated tags")
    p.add_argument("--severity", default=None,
                   help="comma-separated: safety, financial, trust, cosmetic, none")
    p.add_argument("--gate", type=float, default=None,
                   help="exit 1 if the pass rate is below this, or anything errored")
    args = p.parse_args()

    cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
    if args.id:
        wanted = set(i.strip() for i in args.id.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.tag:
        wanted = set(t.strip() for t in args.tag.split(","))
        cases = [c for c in cases if wanted & set(c.get("tags", []))]
    if args.severity:
        wanted = set(s.strip() for s in args.severity.split(","))
        cases = [c for c in cases if c.get("severity") in wanted]
    if not cases:
        sys.exit("no cases matched your filters")

    records = [grade_case(c, args.mode, args.flaky_policy) for c in cases]
    meta = {"mode": args.mode, "flaky_policy": args.flaky_policy}
    text, summary = build_report(records, meta)
    print(text)

    if args.gate is not None:
        ok = summary["pass_rate"] >= args.gate and not summary["errored"]
        print("\nGATE %s: pass rate %.3f vs threshold %.3f%s" % (
            "PASS" if ok else "FAIL", summary["pass_rate"], args.gate,
            "  (blocked: %d case(s) errored)" % summary["errored"]
            if summary["errored"] else ""))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
