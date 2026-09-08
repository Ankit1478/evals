#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("pairwise", os.path.join(HERE, "pairwise.py"))
pairwise = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pairwise)


def candidate(action="track_order", order_id="101", message="I will track order 101."):
    return {"action": action, "order_id": order_id, "message": message}


def sample_pair(pair_id="pair-human", candidate_a=None, candidate_b=None):
    return {
        "pair_id": pair_id,
        "input": "Where is order #101?",
        "candidate_a": candidate_a or candidate(),
        "candidate_b": candidate_b or candidate(message="I can track order 101 for you."),
        "model_a": "current",
        "model_b": "candidate",
        "expected_action": "track_order",
        "expected_order_id": "101",
        "must_include": ["track"],
        "must_not_include": ["cancelled"],
        "rubric": "Prefer the clearer response when both are correct and safe.",
        "rubric_version": "2026-09",
        "risk": "low",
        "source": "handwritten",
    }


class PairwiseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "pairwise.db")
        self.seed_path = os.path.join(self.tmp.name, "pairs.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def write_seed(self, rows):
        with open(self.seed_path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, os.path.join(HERE, "pairwise.py"), *args],
            text=True, capture_output=True, check=False)

    def test_hard_gate_accepts_correct_safe_candidate(self):
        self.assertEqual(pairwise.grade_candidate(sample_pair(), "candidate_a"),
                         {"passed": True, "reasons": []})

    def test_hard_gate_reports_every_failure(self):
        bad = candidate("cancel_order", "999", "Order cancelled.")
        result = pairwise.grade_candidate(sample_pair(candidate_b=bad), "candidate_b")
        self.assertFalse(result["passed"])
        self.assertEqual(result["reasons"], [
            "wrong action: expected track_order",
            "wrong order id: expected 101",
            "message must include: track",
            "message must not include: cancelled",
        ])

    def test_invalid_json_fails_absolute_gate(self):
        row = sample_pair(candidate_b="not json")
        self.assertEqual(pairwise.grade_candidate(row, "candidate_b"), {
            "passed": False, "reasons": ["output is not valid JSON"]})

    def test_automatic_outcome_defers_only_when_both_pass(self):
        self.assertIsNone(pairwise.automatic_outcome(sample_pair()))
        self.assertEqual(
            pairwise.automatic_outcome(sample_pair(candidate_b="not json")),
            "candidate_a")
        self.assertEqual(
            pairwise.automatic_outcome(sample_pair(
                candidate_a="not json", candidate_b="not json")),
            "both_fail")

    def test_blind_order_is_stable_and_uses_both_positions(self):
        self.assertEqual(pairwise.blind_order("pair-001"), pairwise.blind_order("pair-001"))
        orders = {pairwise.blind_order("pair-%03d" % n) for n in range(40)}
        self.assertEqual(orders, {
            ("candidate_a", "candidate_b"),
            ("candidate_b", "candidate_a"),
        })

    def test_bootstrap_auto_decides_hard_gate_and_queues_both_pass(self):
        auto = sample_pair("pair-auto", candidate_b="not json")
        human = sample_pair("pair-human")
        self.write_seed([auto, human])
        created = pairwise.bootstrap(self.db_path, self.seed_path)
        self.assertEqual(created, 2)
        self.assertEqual(pairwise.get_next_pair(self.db_path)["pair_id"], "pair-human")
        outcomes = pairwise.list_pairs(self.db_path)
        self.assertEqual(outcomes[0]["winner"], "candidate_a")
        self.assertEqual(outcomes[0]["decision_source"], "automatic")
        self.assertEqual(outcomes[1]["status"], "pending")

    def test_displayed_choice_maps_to_original_candidate(self):
        self.write_seed([sample_pair()])
        pairwise.bootstrap(self.db_path, self.seed_path)
        task = pairwise.get_next_pair(self.db_path)
        pairwise.record_decision(
            self.db_path, task["pair_id"], "a", "ankit", "Clearer answer.")
        saved = pairwise.list_pairs(self.db_path)[0]
        self.assertEqual(saved["winner"], task["display_a_key"])
        self.assertEqual(saved["decision_source"], "human")

    def test_decision_requires_metadata_and_cannot_overwrite(self):
        self.write_seed([sample_pair()])
        pairwise.bootstrap(self.db_path, self.seed_path)
        with self.assertRaisesRegex(ValueError, "reviewer and notes are required"):
            pairwise.record_decision(self.db_path, "pair-human", "tie", "", "")
        pairwise.record_decision(
            self.db_path, "pair-human", "tie", "ankit", "Equivalent answers.")
        with self.assertRaisesRegex(ValueError, "already has a decision"):
            pairwise.record_decision(
                self.db_path, "pair-human", "tie", "ankit", "Second review.")

    def test_stats_keep_both_fail_out_of_decisive_preference(self):
        rows = [
            sample_pair("pair-a", candidate_b="not json"),
            sample_pair("pair-b", candidate_a="not json"),
            sample_pair("pair-fail", candidate_a="not json", candidate_b="not json"),
            sample_pair("pair-tie"),
            sample_pair("pair-pending"),
        ]
        self.write_seed(rows)
        pairwise.bootstrap(self.db_path, self.seed_path)
        pairwise.record_decision(
            self.db_path, "pair-tie", "tie", "ankit", "Equivalent answers.")
        stats = pairwise.calculate_stats(self.db_path)
        self.assertEqual(stats, {
            "total": 5,
            "completed": 4,
            "pending": 1,
            "candidate_a": 1,
            "candidate_b": 1,
            "tie": 1,
            "both_fail": 1,
            "automatic": 3,
            "human": 1,
            "decisive_preference_a": 0.5,
        })

    def test_export_preserves_model_identity_and_blinding_audit(self):
        self.write_seed([sample_pair()])
        pairwise.bootstrap(self.db_path, self.seed_path)
        task = pairwise.get_next_pair(self.db_path)
        pairwise.record_decision(
            self.db_path, task["pair_id"], "a", "ankit", "Clearer answer.")
        path = os.path.join(self.tmp.name, "preferences.jsonl")
        self.assertEqual(pairwise.export_preferences(self.db_path, path), 1)
        with open(path, encoding="utf-8") as fh:
            record = json.loads(fh.read())
        self.assertEqual(record["winner"], task["display_a_key"])
        self.assertEqual(record["reviewer"], "ankit")
        self.assertEqual(record["model_a"], "current")
        self.assertEqual(record["display_order"], {
            "a": task["display_a_key"], "b": task["display_b_key"]})

    def test_cli_bootstrap_next_list_and_stats(self):
        self.write_seed([
            sample_pair("pair-auto", candidate_b="not json"),
            sample_pair("pair-human"),
        ])
        common = ("--db", self.db_path, "--seed", self.seed_path)
        result = self.run_cli("--bootstrap", *common)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("created 2 pairs", result.stdout)

        result = self.run_cli("--next", *common)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pair-human", result.stdout)
        self.assertIn("Response A", result.stdout)
        self.assertNotIn("current", result.stdout)
        self.assertNotIn("candidate\n", result.stdout)

        result = self.run_cli("--list", *common)
        self.assertIn("candidate_a", result.stdout)
        self.assertIn("pending", result.stdout)

        result = self.run_cli("--stats", *common)
        self.assertIn("Decisive preference for original candidate A: 100.0%", result.stdout)
        self.assertIn("both fail", result.stdout.lower())

    def test_cli_records_noninteractive_blinded_choice(self):
        self.write_seed([sample_pair()])
        common = ("--db", self.db_path, "--seed", self.seed_path)
        self.run_cli("--bootstrap", *common)
        result = self.run_cli(
            "--choose", "tie", "--pair", "pair-human", "--reviewer", "ankit",
            "--notes", "Both are equally good.", *common)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pair-human", result.stdout)
        self.assertIn("tie", result.stdout)

    def test_cli_rejects_decision_without_reviewer_metadata(self):
        self.write_seed([sample_pair()])
        common = ("--db", self.db_path, "--seed", self.seed_path)
        self.run_cli("--bootstrap", *common)
        result = self.run_cli("--choose", "a", "--pair", "pair-human", *common)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reviewer and notes are required", result.stderr)

    def test_default_lesson_seed_creates_four_pairs_with_two_human_reviews(self):
        created = pairwise.bootstrap(self.db_path, pairwise.DEFAULT_SEED)
        self.assertEqual(created, 4)
        stats = pairwise.calculate_stats(self.db_path)
        self.assertEqual(stats["automatic"], 2)
        self.assertEqual(stats["pending"], 2)
        self.assertEqual(stats["both_fail"], 1)


if __name__ == "__main__":
    unittest.main()
