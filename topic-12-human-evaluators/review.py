#!/usr/bin/env python3
"""Local human-evaluation queue with an append-only decision audit trail."""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "human_evals.db")
SEED_PATH = os.path.join(HERE, "review_tasks.jsonl")

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_tasks (
    task_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, customer_question TEXT NOT NULL,
    ai_answer TEXT NOT NULL, expected_action TEXT, policy_version TEXT NOT NULL,
    risk TEXT NOT NULL, rubric TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL UNIQUE,
    decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected', 'escalated')),
    reviewer TEXT NOT NULL, notes TEXT NOT NULL, reviewed_at TEXT NOT NULL,
    rubric_version TEXT NOT NULL, FOREIGN KEY(task_id) REFERENCES review_tasks(task_id)
);
"""


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def bootstrap():
    conn = db(); conn.executescript(SCHEMA)
    if conn.execute("SELECT count(*) FROM review_tasks").fetchone()[0]:
        print("human_evals.db already exists."); return
    with open(SEED_PATH, encoding="utf-8") as fh:
        tasks = [json.loads(line) for line in fh if line.strip()]
    conn.executemany("INSERT INTO review_tasks VALUES (:task_id, :created_at, :customer_question, :ai_answer, :expected_action, :policy_version, :risk, :rubric)", tasks)
    conn.commit(); print("created human_evals.db with %d review tasks" % len(tasks))


def get_next_task():
    conn = db()
    return conn.execute("""SELECT t.* FROM review_tasks t LEFT JOIN reviews r ON r.task_id=t.task_id
                           WHERE r.task_id IS NULL ORDER BY CASE t.risk WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END, t.created_at LIMIT 1""").fetchone()


def next_task():
    task = get_next_task()
    if not task:
        print("No unanswered tasks. Run --stats to see the completed review queue."); return
    print_task(task)


def print_task(task):
    print("\n%s  risk=%s  policy=%s" % (task["task_id"], task["risk"], task["policy_version"]))
    print("Customer: %s" % task["customer_question"])
    print("AI answer: %s" % task["ai_answer"])
    print("Rubric: %s" % task["rubric"])
    print("\nChoose: --approve, --reject, or --escalate %s" % task["task_id"])


def decide(task_id, decision, reviewer, notes):
    if not reviewer or not notes:
        sys.exit("A reviewer name and notes are required for an auditable decision.")
    conn = db()
    if not conn.execute("SELECT 1 FROM review_tasks WHERE task_id=?", (task_id,)).fetchone():
        sys.exit("Unknown task id: %s" % task_id)
    try:
        conn.execute("INSERT INTO reviews(task_id, decision, reviewer, notes, reviewed_at, rubric_version) VALUES (?,?,?,?,?,?)", (task_id, decision, reviewer, notes, now(), "2026-08"))
        conn.commit()
    except sqlite3.IntegrityError:
        sys.exit("This task already has a decision. In production, send a correction through an adjudication workflow.")
    print("Saved: %s → %s by %s" % (task_id, decision, reviewer))


def list_tasks():
    conn = db()
    rows = conn.execute("""SELECT t.task_id, t.risk, COALESCE(r.decision, 'pending') decision, r.reviewer
                           FROM review_tasks t LEFT JOIN reviews r ON r.task_id=t.task_id ORDER BY t.task_id""").fetchall()
    print("%-10s %-10s %-11s %s" % ("task", "risk", "status", "reviewer"))
    for r in rows: print("%-10s %-10s %-11s %s" % (r["task_id"], r["risk"], r["decision"], r["reviewer"] or "-"))


def stats():
    conn = db(); total = conn.execute("SELECT count(*) FROM review_tasks").fetchone()[0]
    rows = conn.execute("SELECT decision, count(*) n FROM reviews GROUP BY decision").fetchall()
    counts = {r["decision"]: r["n"] for r in rows}
    done = sum(counts.values())
    print("Review progress: %d/%d completed" % (done, total))
    for label in ("approved", "rejected", "escalated"):
        print("  %-10s %d" % (label, counts.get(label, 0)))
    print("  pending    %d" % (total - done))


def export_approved(path):
    conn = db(); rows = conn.execute("""SELECT t.* FROM review_tasks t JOIN reviews r ON r.task_id=t.task_id
                                      WHERE r.decision='approved' ORDER BY t.task_id""").fetchall()
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"id": r["task_id"], "input": r["customer_question"], "expected_action": r["expected_action"], "source": "human_approved", "policy_version": r["policy_version"]}) + "\n")
    print("Exported %d approved records to %s" % (len(rows), path))


def interactive_review():
    """Review one task at a time through simple terminal questions."""
    print("\nHuman evaluator terminal mode. Type q at any time to stop.")
    reviewer = input("Your reviewer name: ").strip()
    if not reviewer or reviewer.lower() == "q":
        print("No review started."); return
    while True:
        task = get_next_task()
        if not task:
            print("All tasks are reviewed."); return
        print_task(task)
        choice = input("Decision [a]pprove / [r]eject / [e]scalate / [s]kip / [q]uit: ").strip().lower()
        if choice == "q":
            print("Review session ended."); return
        if choice == "s":
            print("Skipped %s." % task["task_id"]); continue
        decisions = {"a": "approved", "r": "rejected", "e": "escalated"}
        if choice not in decisions:
            print("Please choose a, r, e, s, or q."); continue
        notes = input("Why did you choose this? ").strip()
        if not notes:
            print("A note is required. Task was not changed."); continue
        decide(task["task_id"], decisions[choice], reviewer, notes)


def main():
    parser = argparse.ArgumentParser(description="Human evaluation review queue")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--next", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--interactive", action="store_true",
                        help="review tasks with terminal prompts")
    parser.add_argument("--approve")
    parser.add_argument("--reject")
    parser.add_argument("--escalate")
    parser.add_argument("--reviewer")
    parser.add_argument("--notes")
    parser.add_argument("--export-approved")
    args = parser.parse_args()
    bootstrap()
    if args.bootstrap: return
    choices = [("approved", args.approve), ("rejected", args.reject), ("escalated", args.escalate)]
    selected = [(decision, task) for decision, task in choices if task]
    if len(selected) > 1: sys.exit("Choose only one decision at a time.")
    if selected: decide(selected[0][1], selected[0][0], args.reviewer, args.notes)
    elif args.interactive: interactive_review()
    elif args.next: next_task()
    elif args.list: list_tasks()
    elif args.stats: stats()
    elif args.export_approved: export_approved(args.export_approved)
    else: parser.print_help()


if __name__ == "__main__":
    main()
