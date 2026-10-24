import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.agents.society import recommend
from backend.schemas import SocietyOut
from tests.test_agents import society_output

ROOT = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    def run_demo(self, *args):
        result = subprocess.run([sys.executable, "scripts/run_grok.py", *args], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_offline_demo_warms_and_replays_all_four_agents_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            args = ["--fixtures", "--approve", "--cache-dir", directory]
            live = self.run_demo(*args, "--mode", "live")
            replay = self.run_demo(*args, "--mode", "replay")
            self.assertEqual(live["source"], "synthetic_fixtures")
            self.assertTrue(live["synthetic_scenario"])
            self.assertEqual(live["scout"]["payload"]["post_count"], 24)
            self.assertEqual(len(live["broadcast"]["payload"]["posts"]), 2)
            self.assertEqual(len(live["broadcast"]["payload"]["replies"]), 3)
            for key in ["scout", "drafter", "broadcast"]:
                self.assertEqual(live[key]["status"], "done")
                self.assertEqual(replay[key]["status"], "cached")
            self.assertEqual([v["status"] for v in replay["society"].values()], ["cached"] * 3)

    def test_demo_waits_for_explicit_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            data = self.run_demo("--fixtures", "--cache-dir", directory)
            self.assertIsNone(data["broadcast"])
            self.assertEqual(data["broadcast_status"], "waiting_for_approval")

    def test_recommendation_uses_scores_rather_than_fixed_demo_winner(self):
        outputs = []
        for key, score in [("A", .9), ("B", .2), ("C", .5)]:
            data = society_output(key)
            for row in data["scores"]:
                row["belief_drop"] = score
            outputs.append(SocietyOut(**data))
        self.assertEqual(recommend(outputs), "A")
        with self.assertRaises(ValueError):
            recommend(outputs[:2])


if __name__ == "__main__":
    unittest.main()
