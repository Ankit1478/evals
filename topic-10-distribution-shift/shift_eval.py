#!/usr/bin/env python3
"""Topic 10: production-shaped distribution-shift evaluation, stdlib only.

Uses Topic 9's real Azure OpenAI agent and graders. This file owns the
production event store, temporal windows, and shift-aware reporting.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "evals.db")
SEED = os.path.join(HERE, "production_events.jsonl")
RESULTS = os.path.join(HERE, "results")
TOPIC9 = os.path.join(HERE, "..", "topic-09-datasets", "eval.py")


def topic9():
    spec = importlib.util.spec_from_file_location("topic9_eval", TOPIC9)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


SCHEMA = """
CREATE TABLE IF NOT EXISTS production_events (
  event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, traffic_window TEXT NOT NULL,
  input TEXT NOT NULL, expected_tool TEXT, expected_args_json TEXT NOT NULL,
  arg_match_json TEXT NOT NULL, reply_contains_json TEXT NOT NULL,
  slices_json TEXT NOT NULL, source TEXT NOT NULL, policy_version TEXT NOT NULL,
  traffic_weight REAL NOT NULL, why TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_runs (
  run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, agent TEXT NOT NULL,
  filter_window TEXT, filter_slice TEXT, dataset_fingerprint TEXT NOT NULL,
  strict_rate REAL, scored_count INTEGER, errored_count INTEGER
);
CREATE TABLE IF NOT EXISTS eval_records (
  run_id TEXT NOT NULL, event_id TEXT NOT NULL, strict_ok INTEGER,
  tool_ok INTEGER, errored INTEGER, predicted_tool TEXT, latency_ms INTEGER,
  PRIMARY KEY (run_id, event_id), FOREIGN KEY (run_id) REFERENCES eval_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_events_window ON production_events(traffic_window);
"""


def bootstrap(reset=False):
    if reset and os.path.exists(DB):
        os.remove(DB)
    db = connect()
    db.executescript(SCHEMA)
    if db.execute("SELECT count(*) FROM production_events").fetchone()[0]:
        db.close(); return
    with open(SEED, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    for r in rows:
        db.execute("""INSERT INTO production_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            r["event_id"], r["occurred_at"], r["traffic_window"], r["input"], r["expected_tool"],
            json.dumps(r.get("expected_args", {})), json.dumps(r.get("arg_match", {})),
            json.dumps(r.get("reply_contains", [])), json.dumps(r.get("slices", [])), r["source"],
            r["policy_version"], r["traffic_weight"], r["why"]))
    db.commit(); db.close()
    print("created evals.db with %d scrubbed production-shaped events" % len(rows))


def load_cases(window=None, slice_name=None):
    sql, params = "SELECT * FROM production_events", []
    if window:
        sql += " WHERE traffic_window=?"; params.append(window)
    rows = connect().execute(sql, params).fetchall()
    cases = []
    for r in rows:
        tags = json.loads(r["slices_json"])
        if slice_name and slice_name not in tags:
            continue
        cases.append({"id": r["event_id"], "input": r["input"], "expected_tool": r["expected_tool"],
                      "expected_args": json.loads(r["expected_args_json"]), "arg_match": json.loads(r["arg_match_json"]),
                      "reply_contains": json.loads(r["reply_contains_json"]), "tags": tags,
                      "source": r["source"], "traffic_window": r["traffic_window"],
                      "traffic_weight": r["traffic_weight"], "policy_version": r["policy_version"]})
    return cases


def rate(records):
    scored = [r for r in records if not r["errored"]]
    return (sum(bool(r["strict_ok"]) for r in scored) / len(scored)) if scored else 0.0


def fingerprint(cases):
    material = [{k: c[k] for k in ("id", "input", "expected_tool", "expected_args", "arg_match")}
                for c in sorted(cases, key=lambda c: c["id"])]
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:12]


def rule_based_grade(case, prediction):
    """A simple, deterministic grader.

    Rule 1: the action must exactly match the expected action.
    Rule 2: when an action is correct, every expected argument (such as the
    order id) must exactly match. No LLM/judge call is needed for these rules.
    """
    if prediction.get("error"):
        return {"tool_ok": None, "args_ok": None, "strict_ok": None,
                "errored": True}
    tool_ok = prediction["predicted_tool"] == case["expected_tool"]
    if not tool_ok:
        return {"tool_ok": False, "args_ok": None, "strict_ok": False,
                "errored": False}
    actual_args = prediction.get("predicted_args") or {}
    expected_args = case.get("expected_args") or {}
    args_ok = actual_args == expected_args
    return {"tool_ok": True, "args_ok": args_ok, "strict_ok": args_ok,
            "errored": False}


def composition(cases):
    out = defaultdict(float)
    for c in cases:
        for tag in c["tags"]:
            out[tag] += c["traffic_weight"]
    return out


def print_drift(baseline, current):
    a, b = composition(baseline), composition(current)
    keys = sorted(set(a) | set(b), key=lambda k: abs(b[k] - a[k]), reverse=True)
    print("\nINPUT DISTRIBUTION  (traffic-weight proxy; large movement needs review)")
    print("  %-20s %10s %10s %10s" % ("slice", "baseline", "current", "change"))
    for key in keys:
        if abs(b[key] - a[key]) >= .03:
            print("  %-20s %9.1f%% %9.1f%% %+9.1fpp" % (key, 100*a[key], 100*b[key], 100*(b[key]-a[key])))


def print_quality(records):
    by_window, by_slice = defaultdict(list), defaultdict(list)
    for r in records:
        by_window[r["traffic_window"]].append(r)
        for t in r["tags"]: by_slice[t].append(r)
    print("\nQUALITY BY WINDOW")
    for name, rs in sorted(by_window.items()):
        print("  %-12s strict %5.1f%%  n=%d" % (name, 100*rate(rs), len(rs)))
    print("\nQUALITY BY SLICE  (worst first)")
    for name, rs in sorted(by_slice.items(), key=lambda pair: rate(pair[1])):
        print("  %-20s strict %5.1f%%  n=%d" % (name, 100*rate(rs), len(rs)))
    weighted = [r for r in records if not r["errored"]]
    denom = sum(r["traffic_weight"] for r in weighted)
    score = sum(r["traffic_weight"] * bool(r["strict_ok"]) for r in weighted) / denom if denom else 0
    print("\n  weighted strict score: %.1f%%  (use with slice results, never instead of them)" % (100*score))


def persist(agent, window, slice_name, cases, records):
    run_id = time.strftime("run-%Y%m%d-%H%M%S")
    db = connect(); errored = sum(bool(r["errored"]) for r in records)
    db.execute("INSERT INTO eval_runs VALUES (?,?,?,?,?,?,?,?,?)", (run_id, time.strftime("%Y-%m-%dT%H:%M:%SZ"), agent, window, slice_name, fingerprint(cases), rate(records), len(records)-errored, errored))
    db.executemany("INSERT INTO eval_records VALUES (?,?,?,?,?,?,?)", [(run_id, r["id"], int(bool(r["strict_ok"])), int(bool(r["tool_ok"])), int(bool(r["errored"])), r["predicted_tool"], r["latency_ms"]) for r in records])
    db.commit(); db.close(); return run_id


def main():
    p = argparse.ArgumentParser(description="Production-shaped distribution-shift eval")
    p.add_argument("--agent", choices=("keyword", "llm"), default="llm")
    p.add_argument("--window", choices=("baseline", "current"))
    p.add_argument("--slice", dest="slice_name")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--gate", type=float)
    p.add_argument("--reset-db", action="store_true")
    args = p.parse_args()
    bootstrap(args.reset_db)
    if args.reset_db: return
    all_cases = load_cases(); cases = load_cases(args.window, args.slice_name)
    if not cases: sys.exit("no events matched the requested window/slice")
    baseline, current = load_cases("baseline"), load_cases("current")
    print("\nTOPIC 10 — DISTRIBUTION SHIFT EVALS")
    print("events=%d  fingerprint=%s  agent=%s" % (len(cases), fingerprint(cases), args.agent))
    if not args.window and not args.slice_name: print_drift(baseline, current)
    lesson = topic9(); agent_fn = lesson.AGENTS[args.agent]
    records = []
    for c in cases:
        result = lesson.run_case(agent_fn, c, args.repeat, not args.no_cache and args.repeat == 1, 0.0)
        result.update({k: c[k] for k in ("traffic_window", "traffic_weight", "policy_version")})
        # Topic 9 gives us the real agent response. Grade that response here
        # with the two explicit rules above, so this lesson is easy to inspect.
        result.update(rule_based_grade(c, result))
        records.append(result)
    print_quality(records)
    run_id = persist(args.agent, args.window, args.slice_name, cases, records)
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, run_id + ".json"), "w") as fh: json.dump(records, fh, indent=2)
    print("\nsaved %s to SQLite and results/%s.json" % (run_id, run_id))
    if args.gate is not None:
        ok = rate(records) >= args.gate and not any(r["errored"] for r in records)
        print("GATE %s: %.3f vs %.3f" % ("PASS" if ok else "FAIL", rate(records), args.gate)); sys.exit(0 if ok else 1)


if __name__ == "__main__": main()
