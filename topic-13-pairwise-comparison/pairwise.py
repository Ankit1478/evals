#!/usr/bin/env python3
"""Hybrid hard-gate and blinded pairwise evaluation lesson."""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, "pairwise.db")
DEFAULT_SEED = os.path.join(HERE, "pairs.jsonl")


SCHEMA = """
CREATE TABLE IF NOT EXISTS pairs (
    pair_id TEXT PRIMARY KEY,
    input TEXT NOT NULL,
    candidate_a_json TEXT NOT NULL,
    candidate_b_json TEXT NOT NULL,
    model_a TEXT NOT NULL,
    model_b TEXT NOT NULL,
    expected_action TEXT NOT NULL,
    expected_order_id TEXT,
    must_include_json TEXT NOT NULL,
    must_not_include_json TEXT NOT NULL,
    rubric TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    risk TEXT NOT NULL,
    source TEXT NOT NULL,
    display_a_key TEXT NOT NULL,
    display_b_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT NOT NULL UNIQUE,
    winner TEXT NOT NULL CHECK(winner IN
        ('candidate_a', 'candidate_b', 'tie', 'both_fail')),
    decision_source TEXT NOT NULL CHECK(decision_source IN ('automatic', 'human')),
    displayed_choice TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    notes TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    display_a_key TEXT NOT NULL,
    display_b_key TEXT NOT NULL,
    FOREIGN KEY(pair_id) REFERENCES pairs(pair_id)
);
"""


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _answer(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError("output is not valid JSON")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("output is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("output is not a JSON object")
    return parsed


def grade_candidate(pair, candidate_key):
    """Apply absolute, deterministic checks to one response."""
    try:
        answer = _answer(pair[candidate_key])
    except (KeyError, ValueError) as exc:
        return {"passed": False, "reasons": [str(exc)]}

    reasons = []
    for field in ("action", "order_id", "message"):
        if field not in answer:
            reasons.append("missing field: %s" % field)

    if answer.get("action") != pair["expected_action"]:
        reasons.append("wrong action: expected %s" % pair["expected_action"])

    expected_id = pair.get("expected_order_id")
    actual_id = answer.get("order_id")
    id_matches = actual_id is None if expected_id is None else str(actual_id) == str(expected_id)
    if not id_matches:
        reasons.append("wrong order id: expected %s" % expected_id)

    message = str(answer.get("message", "")).lower()
    for phrase in pair.get("must_include", []):
        if phrase.lower() not in message:
            reasons.append("message must include: %s" % phrase)
    for phrase in pair.get("must_not_include", []):
        if phrase.lower() in message:
            reasons.append("message must not include: %s" % phrase)
    return {"passed": not reasons, "reasons": reasons}


def automatic_outcome(pair):
    """Return an absolute-gate result, or None when human preference is needed."""
    a_passes = grade_candidate(pair, "candidate_a")["passed"]
    b_passes = grade_candidate(pair, "candidate_b")["passed"]
    if a_passes and b_passes:
        return None
    if a_passes:
        return "candidate_a"
    if b_passes:
        return "candidate_b"
    return "both_fail"


def blind_order(pair_id):
    """Return stable display positions without exposing model identities."""
    swap = hashlib.sha256(pair_id.encode("utf-8")).digest()[0] % 2
    if swap:
        return "candidate_b", "candidate_a"
    return "candidate_a", "candidate_b"


def _load_seed(seed_path):
    rows = []
    seen = set()
    with open(seed_path, encoding="utf-8") as fh:
        for line_number, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row["pair_id"] in seen:
                raise ValueError("duplicate pair_id on line %d" % line_number)
            seen.add(row["pair_id"])
            rows.append(row)
    return rows


def bootstrap(db_path, seed_path, reset=False):
    """Create the local queue and pre-record deterministic gate outcomes."""
    if reset and os.path.exists(db_path):
        os.remove(db_path)
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    if conn.execute("SELECT count(*) FROM pairs").fetchone()[0]:
        conn.close()
        return 0

    rows = _load_seed(seed_path)
    for row in rows:
        display_a, display_b = blind_order(row["pair_id"])
        conn.execute(
            """INSERT INTO pairs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["pair_id"], row["input"], json.dumps(row["candidate_a"]),
             json.dumps(row["candidate_b"]), row["model_a"], row["model_b"],
             row["expected_action"], row.get("expected_order_id"),
             json.dumps(row.get("must_include", [])),
             json.dumps(row.get("must_not_include", [])), row["rubric"],
             row["rubric_version"], row.get("risk", "low"), row["source"],
             display_a, display_b))

        winner = automatic_outcome(row)
        if winner is not None:
            gate_evidence = {
                "candidate_a": grade_candidate(row, "candidate_a"),
                "candidate_b": grade_candidate(row, "candidate_b"),
            }
            conn.execute(
                """INSERT INTO decisions(
                    pair_id, winner, decision_source, displayed_choice, reviewer,
                    notes, reviewed_at, rubric_version, display_a_key, display_b_key
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (row["pair_id"], winner, "automatic", "automatic", "system",
                 json.dumps(gate_evidence, sort_keys=True), now(),
                 row["rubric_version"], display_a, display_b))
    conn.commit()
    conn.close()
    return len(rows)


def get_next_pair(db_path, excluded=None):
    """Return the highest-risk pending pair with candidates blinded."""
    excluded = set(excluded or [])
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT p.* FROM pairs p
           LEFT JOIN decisions d ON d.pair_id=p.pair_id
           WHERE d.pair_id IS NULL
           ORDER BY CASE p.risk WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END,
                    p.pair_id""").fetchall()
    conn.close()
    for row in rows:
        if row["pair_id"] in excluded:
            continue
        answers = {
            "candidate_a": json.loads(row["candidate_a_json"]),
            "candidate_b": json.loads(row["candidate_b_json"]),
        }
        return {
            "pair_id": row["pair_id"],
            "input": row["input"],
            "rubric": row["rubric"],
            "risk": row["risk"],
            "display_a_key": row["display_a_key"],
            "display_b_key": row["display_b_key"],
            "response_a": answers[row["display_a_key"]],
            "response_b": answers[row["display_b_key"]],
        }
    return None


def list_pairs(db_path):
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT p.pair_id, p.risk, d.winner, d.decision_source
           FROM pairs p LEFT JOIN decisions d ON d.pair_id=p.pair_id
           ORDER BY p.pair_id""").fetchall()
    conn.close()
    return [{
        "pair_id": row["pair_id"],
        "risk": row["risk"],
        "status": "completed" if row["winner"] else "pending",
        "winner": row["winner"],
        "decision_source": row["decision_source"],
    } for row in rows]


def record_decision(db_path, pair_id, displayed_choice, reviewer, notes):
    """Save one human decision and preserve its blinded-position mapping."""
    if not reviewer or not reviewer.strip() or not notes or not notes.strip():
        raise ValueError("reviewer and notes are required")
    if displayed_choice not in ("a", "b", "tie", "both_fail"):
        raise ValueError("choice must be a, b, tie, or both_fail")

    conn = connect(db_path)
    row = conn.execute("SELECT * FROM pairs WHERE pair_id=?", (pair_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("unknown pair id: %s" % pair_id)
    if conn.execute("SELECT 1 FROM decisions WHERE pair_id=?", (pair_id,)).fetchone():
        conn.close()
        raise ValueError("pair already has a decision")

    winner = {
        "a": row["display_a_key"],
        "b": row["display_b_key"],
        "tie": "tie",
        "both_fail": "both_fail",
    }[displayed_choice]
    conn.execute(
        """INSERT INTO decisions(
            pair_id, winner, decision_source, displayed_choice, reviewer, notes,
            reviewed_at, rubric_version, display_a_key, display_b_key
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (pair_id, winner, "human", displayed_choice, reviewer.strip(), notes.strip(),
         now(), row["rubric_version"], row["display_a_key"], row["display_b_key"]))
    conn.commit()
    conn.close()
    return winner


def calculate_stats(db_path):
    conn = connect(db_path)
    total = conn.execute("SELECT count(*) FROM pairs").fetchone()[0]
    rows = conn.execute(
        "SELECT winner, decision_source, count(*) n FROM decisions GROUP BY 1,2"
    ).fetchall()
    conn.close()

    counts = {key: 0 for key in (
        "candidate_a", "candidate_b", "tie", "both_fail", "automatic", "human")}
    for row in rows:
        counts[row["winner"]] += row["n"]
        counts[row["decision_source"]] += row["n"]
    completed = counts["automatic"] + counts["human"]
    decisive = counts["candidate_a"] + counts["candidate_b"]
    return {
        "total": total,
        "completed": completed,
        "pending": total - completed,
        "candidate_a": counts["candidate_a"],
        "candidate_b": counts["candidate_b"],
        "tie": counts["tie"],
        "both_fail": counts["both_fail"],
        "automatic": counts["automatic"],
        "human": counts["human"],
        "decisive_preference_a": (
            counts["candidate_a"] / float(decisive) if decisive else None),
    }


def export_preferences(db_path, output_path):
    conn = connect(db_path)
    rows = conn.execute(
        """SELECT p.*, d.winner, d.decision_source, d.displayed_choice,
                  d.reviewer, d.notes, d.reviewed_at,
                  d.display_a_key AS audited_display_a,
                  d.display_b_key AS audited_display_b
           FROM pairs p JOIN decisions d ON d.pair_id=p.pair_id
           ORDER BY p.pair_id""").fetchall()
    conn.close()
    with open(output_path, "w", encoding="utf-8") as fh:
        for row in rows:
            record = {
                "pair_id": row["pair_id"],
                "input": row["input"],
                "candidate_a": json.loads(row["candidate_a_json"]),
                "candidate_b": json.loads(row["candidate_b_json"]),
                "model_a": row["model_a"],
                "model_b": row["model_b"],
                "winner": row["winner"],
                "decision_source": row["decision_source"],
                "displayed_choice": row["displayed_choice"],
                "display_order": {
                    "a": row["audited_display_a"],
                    "b": row["audited_display_b"],
                },
                "reviewer": row["reviewer"],
                "notes": row["notes"],
                "reviewed_at": row["reviewed_at"],
                "rubric": row["rubric"],
                "rubric_version": row["rubric_version"],
                "source": row["source"],
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(rows)


def print_pair(task):
    if not task:
        print("No pairs need human review. Run --stats for the completed queue.")
        return
    print("\n%s  risk=%s" % (task["pair_id"], task["risk"]))
    print("Prompt: %s" % task["input"])
    print("\nResponse A\n%s" % json.dumps(
        task["response_a"], indent=2, ensure_ascii=False))
    print("\nResponse B\n%s" % json.dumps(
        task["response_b"], indent=2, ensure_ascii=False))
    print("\nRubric: %s" % task["rubric"])
    print("Choose A, B, tie, or both fail. Model identities are hidden.")


def print_list(db_path):
    print("%-14s %-10s %-10s %-13s %s" % (
        "pair", "risk", "status", "source", "winner"))
    for row in list_pairs(db_path):
        print("%-14s %-10s %-10s %-13s %s" % (
            row["pair_id"], row["risk"], row["status"],
            row["decision_source"] or "-", row["winner"] or "-"))


def print_stats(db_path):
    stats = calculate_stats(db_path)
    print("Pairwise evaluation: %d/%d completed; %d pending" % (
        stats["completed"], stats["total"], stats["pending"]))
    print("  original candidate A wins  %d" % stats["candidate_a"])
    print("  original candidate B wins  %d" % stats["candidate_b"])
    print("  ties                       %d" % stats["tie"])
    print("  both fail                  %d" % stats["both_fail"])
    print("  automatic decisions        %d" % stats["automatic"])
    print("  human decisions            %d" % stats["human"])
    preference = stats["decisive_preference_a"]
    if preference is None:
        print("Decisive preference for original candidate A: n/a")
    else:
        print("Decisive preference for original candidate A: %.1f%%" % (
            100 * preference))
    print("Preference is relative; 'both fail' is the absolute-quality warning.")


def interactive_review(db_path):
    print("\nBlinded pairwise review. Type q to stop.")
    reviewer = input("Reviewer name: ").strip()
    if not reviewer or reviewer.lower() == "q":
        print("No review started.")
        return
    skipped = set()
    while True:
        task = get_next_pair(db_path, excluded=skipped)
        if not task:
            print("No more unreviewed pairs in this session.")
            return
        print_pair(task)
        choice = input(
            "Decision [a] / [b] / [t]ie / both [f]ail / [s]kip / [q]uit: "
        ).strip().lower()
        if choice == "q":
            print("Review session ended.")
            return
        if choice == "s":
            skipped.add(task["pair_id"])
            print("Skipped %s for this session." % task["pair_id"])
            continue
        choices = {"a": "a", "b": "b", "t": "tie", "f": "both_fail"}
        if choice not in choices:
            print("Choose a, b, t, f, s, or q.")
            continue
        notes = input("Reason: ").strip()
        if not notes:
            print("A reason is required; no decision was saved.")
            continue
        winner = record_decision(
            db_path, task["pair_id"], choices[choice], reviewer, notes)
        print("Saved %s → %s" % (task["pair_id"], winner))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Hybrid hard-gate and blinded pairwise evaluation")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--bootstrap", action="store_true")
    actions.add_argument("--reset-db", action="store_true")
    actions.add_argument("--next", action="store_true")
    actions.add_argument("--interactive", action="store_true")
    actions.add_argument("--list", action="store_true")
    actions.add_argument("--stats", action="store_true")
    actions.add_argument("--choose", choices=("a", "b", "tie", "both_fail"))
    actions.add_argument("--export")
    parser.add_argument("--pair")
    parser.add_argument("--reviewer")
    parser.add_argument("--notes")
    args = parser.parse_args(argv)

    try:
        created = bootstrap(args.db, args.seed, reset=args.reset_db)
        if args.bootstrap or args.reset_db:
            if created:
                print("created %d pairs in %s" % (created, args.db))
            else:
                print("database already contains pairs: %s" % args.db)
            return 0
        if args.next:
            print_pair(get_next_pair(args.db))
        elif args.interactive:
            interactive_review(args.db)
        elif args.list:
            print_list(args.db)
        elif args.stats:
            print_stats(args.db)
        elif args.choose:
            if not args.pair:
                raise ValueError("--pair is required with --choose")
            winner = record_decision(
                args.db, args.pair, args.choose,
                args.reviewer or "", args.notes or "")
            print("Saved: %s → %s" % (args.pair, winner))
        elif args.export:
            count = export_preferences(args.db, args.export)
            print("Exported %d completed comparisons to %s" % (count, args.export))
        else:
            parser.print_help()
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
