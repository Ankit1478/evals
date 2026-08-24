#!/usr/bin/env python3
"""Triage helper for production_logs.jsonl.

You have 30 logs. You cannot label all of them, and you should not want to --
boring successful chats teach you nothing. This script sorts them so the
interesting ones float to the top.

  python3 inspect_logs.py               # everything, riskiest first
  python3 inspect_logs.py --risky       # only rows worth labelling
  python3 inspect_logs.py --show tr_005 # full detail on one trace
  python3 inspect_logs.py --pii         # rows that need scrubbing
"""

import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "production_logs.jsonl")

# Cheap PII detectors. Real systems use a proper scrubber; the point here is
# that you must LOOK before a log line becomes a committed test case.
PII_PATTERNS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.]+",
    "phone": r"\+?\d[\d\s-]{8,}\d",
    "card": r"\b(?:\d{4}[\s-]?){3}\d{4}\b",
    "person_addr": r"\b\d+\s+[A-Z][a-z]+\s+(Street|Road|Salai|Drive|Marg)\b",
}


def find_pii(row):
    blob = "%s %s" % (row.get("user_message") or "", row.get("assistant_reply") or "")
    return [k for k, pat in PII_PATTERNS.items() if re.search(pat, blob)]


def risk_score(row):
    """Higher = more worth your labelling time."""
    s = row.get("signals", {})
    score = 0
    if s.get("thumbs") == "down":
        score += 3
    if s.get("escalated"):
        score += 3
    if s.get("repeat_contact"):
        score += 2
    if s.get("note"):
        score += 4          # a human already flagged it
    if row.get("error"):
        score += 2
    if s.get("csat") in (1, 2):
        score += 2
    if len(row.get("tool_calls") or []) > 1:
        score += 2          # unusual: multiple calls in one turn
    if find_pii(row):
        score += 1
    # money- or deletion-touching tools are high consequence even when they pass
    for c in row.get("tool_calls") or []:
        if c["name"] in ("cancel_order", "refund_status"):
            score += 1
    return score


def flags(row):
    s, out = row.get("signals", {}), []
    if s.get("thumbs") == "down":
        out.append("THUMBS_DOWN")
    if s.get("escalated"):
        out.append("ESCALATED")
    if s.get("repeat_contact"):
        out.append("REPEAT")
    if row.get("error"):
        out.append("ERROR")
    if s.get("note"):
        out.append("FLAGGED")
    if len(row.get("tool_calls") or []) > 1:
        out.append("MULTI_CALL")
    pii = find_pii(row)
    if pii:
        out.append("PII:" + "/".join(pii))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--risky", action="store_true", help="only rows with risk >= 3")
    p.add_argument("--pii", action="store_true", help="only rows containing PII")
    p.add_argument("--show", default=None, help="print one trace in full")
    args = p.parse_args()

    rows = [json.loads(l) for l in open(LOGS, encoding="utf-8") if l.strip()]

    if args.show:
        for r in rows:
            if r["trace_id"] == args.show:
                print(json.dumps(r, indent=2, ensure_ascii=False))
                print("\nrisk=%d  flags=%s" % (risk_score(r), flags(r) or ["-"]))
                return
        return print("no such trace_id")

    if args.pii:
        rows = [r for r in rows if find_pii(r)]
    if args.risky:
        rows = [r for r in rows if risk_score(r) >= 3]

    rows.sort(key=risk_score, reverse=True)
    print("%-8s %-4s %-3s %-26s %-16s %s" % (
        "trace", "risk", "trn", "user said", "tool called", "flags"))
    print("-" * 118)
    for r in rows:
        calls = ",".join(c["name"] for c in (r.get("tool_calls") or [])) or "-none-"
        print("%-8s %-4d %-3d %-26s %-16s %s" % (
            r["trace_id"], risk_score(r), r.get("turn", 1),
            (r.get("user_message") or "")[:26], calls[:16],
            " ".join(flags(r))))
    print("\n%d rows shown. Label the top ones first." % len(rows))


if __name__ == "__main__":
    main()
