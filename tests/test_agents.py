import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.agents import broadcaster, drafter, scout, society
from backend.agents.runner import AgentRunner
from backend.cache import CacheMiss, DiskCache
from backend.schemas import (BroadcastInput, DraftInput, DrafterOut, Framing, GROUPS, ScoutInput,
                             SocietyInput, SocietyOut)


class FixtureProvider:
    identity = "unit-test-fixture"

    def __init__(self, output):
        self.output = output
        self.calls = []

    def generate(self, system, user, schema, *, model):
        self.calls.append((json.loads(user), model))
        return schema.model_validate(self.output)


def draft_input(verdict="False"):
    return DraftInput(claim="The photo shows a fire on I-15.", verdict=verdict,
        verified_facts=["The pictured sign identifies a different road."],
        safety_action="Check official updates before sharing.", official_source="https://www.readysandiego.org/")


def draft_output():
    return {"framings": [{"key": key, "name": name,
        "text_en": "This photo does not establish the fire location. Check official updates.",
        "text_es": "Esta foto no confirma dónde está el incendio. Consulta los avisos oficiales."}
        for key, name in zip("ABC", ["Fact check", "Action first", "Neighbor voice"])]}


def society_input():
    return SocietyInput(claim="Fire crossed I-15.", framing=Framing(**draft_output()["framings"][1]),
        groups=[{"group_id": i, "name": name, "personas": [
            {"name": f"Person {i}-{j}", "age": 35, "platform": "WhatsApp",
             "trust_in_government": "med", "language": "es" if i == 1 else "en"}
            for j in range(4 if i < 2 else 3)]} for i, name in enumerate(GROUPS)])


def society_output(key="B"):
    return {"framing_key": key, "scores": [
        {"group_id": i, "belief_drop": p, "reaction": "I will check the source."}
        for i, p in enumerate([.8, .6, .4, .5, .9, .2])], "es_group_en_only_drop": .15}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = DiskCache(Path(self.tmp.name))

    def runner(self, output, **kwargs):
        provider = FixtureProvider(output)
        return AgentRunner(provider, self.cache, model="test-model", **kwargs)

    def scout_input(self):
        return ScoutInput(incident_id="SD-1024", posts=[
            {"id": "a", "timestamp": "2026-10-24T19:20:00-07:00", "text": "Fire crossed I-15.", "language": "en", "who": "@one"},
            {"id": "b", "timestamp": "2026-10-24T19:22:00-07:00", "text": "El fuego cruzó la I-15.", "language": "es", "who": "@two"},
            {"id": "c", "timestamp": "2026-10-24T19:30:00-07:00", "text": "Shelter is open.", "language": "en", "who": "@three"}])

    def test_scout_counts_only_cluster_members_and_computes_velocity(self):
        result = scout.run(self.scout_input(), self.runner({"claim": "Fire crossed I-15.",
            "selected_post_ids": ["b", "a"], "summary": "Two posts repeat the claim."}))
        self.assertEqual(result.payload.post_count, 2)
        self.assertEqual(result.payload.velocity_per_min, 1.0)
        self.assertEqual(result.payload.languages, ["en", "es"])

    def test_scout_rejects_unknown_and_duplicate_members_before_caching(self):
        for ids in [["a", "missing"], ["a", "a"]]:
            with self.assertRaises(ValueError):
                scout.run(self.scout_input(), self.runner({"claim": "Fire.", "selected_post_ids": ids, "summary": "Claim."}))
        self.assertEqual(list(Path(self.tmp.name).glob("*.json")), [])

    def test_scout_single_post_has_finite_one_minute_floor(self):
        out = scout.run(self.scout_input(), self.runner({"claim": "Fire.", "selected_post_ids": ["a"], "summary": "Claim."}))
        self.assertEqual(out.payload.velocity_per_min, 1)

    def test_drafter_returns_all_three_bilingual_framings_and_passes_evidence(self):
        runner = self.runner(draft_output())
        out = drafter.run(draft_input("Unverified"), runner)
        self.assertEqual([f.key for f in out.payload.framings], ["A", "B", "C"])
        passed, _ = runner.provider.calls[0]
        self.assertEqual(passed["verdict"], "Unverified")
        self.assertEqual(passed["verified_facts"], ["The pictured sign identifies a different road."])

    def test_drafter_rejects_duplicate_keys_and_overlong_posts(self):
        for output in [dict(framings=[draft_output()["framings"][0]] * 3),
                       dict(framings=[{**f, "text_es": "x" * 281} for f in draft_output()["framings"]])]:
            with self.assertRaises(ValidationError):
                drafter.run(draft_input(), self.runner(output))

    def test_society_orders_groups_and_maps_the_existing_simulation_probabilities(self):
        output = society_output()
        output["scores"].reverse()
        runner = self.runner(output, fast_model="fast-test-model")
        out = society.run(society_input(), runner)
        self.assertEqual([s.group_id for s in out.payload.scores], list(range(6)))
        values = society.simulation_parameters(out.payload)
        self.assertEqual(values["p"], [.24, .18, .12, .15, .27, .06])
        self.assertEqual(values["es_off_mult"], .25)
        self.assertEqual(runner.provider.calls[0][1], "fast-test-model")

    def test_society_rejects_wrong_framing_before_caching(self):
        with self.assertRaises(ValueError):
            society.run(society_input(), self.runner(society_output("A")))
        self.assertEqual(list(Path(self.tmp.name).glob("*.json")), [])

    def test_society_zero_spanish_score_has_finite_neutral_multiplier(self):
        data = society_output()
        data["scores"][1]["belief_drop"] = 0
        data["es_group_en_only_drop"] = 0
        result = society.simulation_parameters(SocietyOut(**data))
        self.assertEqual(result["p"][1], .03)
        self.assertEqual(result["es_off_mult"], 1)

    def broadcast_input(self, approved=True):
        return BroadcastInput(approved=approved, framing_key="B", post_en="  Approved English copy.  ",
            post_es="Texto aprobado.", verified_facts=["The photo is unrelated."],
            official_source="https://www.readysandiego.org/", questions=[
                {"id": "q1", "text": "Is Poway safe?", "language": "en"},
                {"id": "q2", "text": "¿Y Ramona?", "language": "es"}])

    def test_broadcaster_requires_approval_and_preserves_exact_posts(self):
        runner = self.runner({"replies": [{"question_id": "q2", "text": "Consulta los avisos oficiales."},
                                          {"question_id": "q1", "text": "Check official updates."}]})
        out = broadcaster.run(self.broadcast_input(), runner)
        self.assertEqual(out.payload.posts[0].text, "  Approved English copy.  ")
        self.assertEqual([p.in_reply_to for p in out.payload.replies], ["q1", "q2"])
        self.assertEqual([p.language for p in out.payload.replies], ["en", "es"])
        with self.assertRaises(PermissionError):
            broadcaster.run(self.broadcast_input(False), runner)
        self.assertEqual(len(runner.provider.calls), 1)

    def test_broadcaster_rejects_missing_or_unknown_reply_ids(self):
        for replies in [[], [{"question_id": "unknown", "text": "Check updates."}]]:
            out = broadcaster.run(self.broadcast_input(), self.runner({"replies": replies}))
            self.assertEqual(out.payload.reply_status, "unavailable")
            self.assertEqual(out.payload.replies, [])
            self.assertEqual(len(out.payload.posts), 2)
        self.assertEqual(list(Path(self.tmp.name).glob("*.json")), [])

    def test_broadcaster_delivers_approved_posts_when_reply_generation_times_out(self):
        runner = self.runner({})
        def unavailable(*args, **kwargs):
            raise TimeoutError("Provider unavailable")
        runner.provider.generate = unavailable
        out = broadcaster.run(self.broadcast_input(), runner)
        self.assertEqual(out.payload.posts[0].text, "  Approved English copy.  ")
        self.assertEqual(out.payload.reply_status, "unavailable")
        self.assertEqual(out.payload.replies, [])

    def test_broadcaster_without_questions_does_not_need_generation(self):
        inputs = self.broadcast_input().model_copy(update={"questions": [], "post_es": None})
        runner = self.runner({})
        out = broadcaster.run(inputs, runner)
        self.assertEqual(len(out.payload.posts), 1)
        self.assertEqual(out.payload.replies, [])
        self.assertEqual(runner.provider.calls, [])

    def test_replay_and_model_prompt_provider_changes_isolate_cache(self):
        runner = self.runner(draft_output())
        drafter.run(draft_input(), runner)
        runner.mode = "replay"
        self.assertEqual(drafter.run(draft_input(), runner).status, "cached")
        self.assertEqual(len(runner.provider.calls), 1)
        with self.assertRaises(CacheMiss):
            runner.run("drafter", draft_input(), "A changed prompt", DrafterOut,
                       lambda model: self.fail("Replay tried generation"))
        for attribute, value in [("model", "another-model"), ("identity", "other-provider")]:
            if attribute == "model":
                runner.model = value
            else:
                runner.model = "test-model"
                runner.provider.identity = value
            with self.assertRaises(CacheMiss):
                drafter.run(draft_input(), runner)


if __name__ == "__main__":
    unittest.main()
