"""Gemini evidence and Voiskey editor wired into the Grok desk. Offline: Gemini calls are faked."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from backend.gemini import config as gconfig
from backend.gemini.schemas import DefenderOut, EditorOut, JudgeOut, ProsecutorOut
from backend.main import create_app
from backend.society_service import EpisodeManager


def fixture(name, model):
    return model.model_validate_json((gconfig.FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


async def fake_analyze(image, mime, claim, ctx, live):
    return ((fixture("prosecutor", ProsecutorOut), "cached"), (fixture("defender", DefenderOut), "cached"),
            (fixture("judge", JudgeOut), "cached"), "abc123")


class GeminiDeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = TestClient(create_app(EpisodeManager(Path(self.temp.name))))
        self.addCleanup(self.client.close)
        patcher = mock.patch("backend.gemini.routes.analyze", fake_analyze)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, path, data=None, status=None):
        r = self.client.post(path, json=data or {})
        if status:
            self.assertEqual(r.status_code, status, r.text)
        else:
            self.assertLess(r.status_code, 300, r.text)
        return r.json()

    def verified_episode(self):
        view = self.post("/api/episodes", {"mode": "fixture"})
        out = self.post(f"/api/gemini/episodes/{view['id']}/evidence")
        return out["view"]

    def test_gemini_packet_becomes_episode_evidence(self):
        view = self.verified_episode()
        ev = view["evidence"]
        self.assertEqual(ev["source"], "gemini")
        self.assertEqual(ev["verdict"], "False")
        self.assertTrue(any(f["box_2d"] for f in ev["findings"]))
        self.assertTrue(ev["verified_facts"])
        self.assertIsNone(view["drafts"], "new evidence must clear stale drafts")
        steps = {p["agent"]: p for p in view["pipeline"]}
        self.assertEqual(steps["prosecutor"]["model"], "gemini")
        self.assertEqual(steps["prosecutor"]["status"], "done")
        self.assertIn("91% confident", steps["judge"]["summary"])

    def test_full_episode_runs_on_gemini_evidence(self):
        view = self.verified_episode()
        base = f"/api/episodes/{view['id']}"
        view = self.post(base + "/drafts")
        self.assertEqual(len(view["drafts"]["framings"]), 3)
        view = self.post(base + "/advance")
        view = self.post(base + "/advance")
        self.assertEqual(view["status"], "awaiting_approval")
        view = self.post(base + "/intervention", {"framing_key": "B", "text_en": "No new orders. Stay off the roads.",
                                                  "text_es": "No hay nuevas órdenes.", "target_groups": [0, 1]})
        p = view["pending_intervention"]
        view = self.post(base + "/approve", {"revision": p["revision"], "content_hash": p["content_hash"]})
        view = self.post(base + "/advance")
        view = self.post(base + "/advance")
        self.assertEqual(view["status"], "complete")
        # Evidence is frozen once a correction is approved.
        self.post(f"/api/gemini/episodes/{view['id']}/evidence", status=409)

    def test_unknown_episode_spends_no_quota(self):
        with mock.patch("backend.gemini.routes.analyze", side_effect=AssertionError("called Gemini")):
            self.assertEqual(self.client.post("/api/gemini/episodes/0000-dead/evidence", json={}).status_code, 404)

    def test_voice_note_returns_editor_copy_and_targets(self):
        demo = json.loads((gconfig.FIXTURES / "editor_demo.json").read_text(encoding="utf-8"))

        async def fake_editor(*args, **kwargs):
            self.assertTrue(kwargs["voiskey_clean"])
            return EditorOut.model_validate(demo)

        with mock.patch("backend.gemini.routes.editor.run", fake_editor):
            r = self.client.post("/api/voice", data={"text": "Kill it. Do Spanish too.", "source": "voiskey",
                                                     "framing_key": "B", "text_en": "Draft copy", "text_es": "Borrador"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["target_groups"], [0, 1])
        self.assertEqual(r.json()["intent"]["action"], "approve")

    def test_voice_needs_copy_and_input(self):
        self.assertEqual(self.client.post("/api/voice", data={"text": "approve"}).status_code, 409)
        self.assertEqual(self.client.post("/api/voice", data={"text_en": "x"}).status_code, 400)

    def test_analyze_rejects_non_images(self):
        r = self.client.post("/api/analyze", files={"image": ("a.txt", b"hello", "text/plain")}, data={"claim": "x"})
        self.assertEqual(r.status_code, 415)

    def test_scenario_spanish_text_reads_as_utf8(self):
        manager = EpisodeManager(Path(self.temp.name))
        self.assertEqual(manager.scenario["replies"][2]["text"], "¿y Ramona? ¿también?")


if __name__ == "__main__":
    unittest.main()
