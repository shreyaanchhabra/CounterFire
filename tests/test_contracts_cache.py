import tempfile
import time
import unittest
from pathlib import Path

from pydantic import ValidationError

from backend.cache import CacheMiss, DiskCache
from backend.schemas import Framing, SocietyOut


def framing():
    return Framing(key="A", name="Fact check", text_en="Check official updates.", text_es="Consulta los avisos oficiales.")


class ContractTests(unittest.TestCase):
    def test_rejects_overlong_or_blank_corrections(self):
        for text in ["x" * 281, "   "]:
            with self.assertRaises(ValidationError):
                Framing(key="A", name="Fact check", text_en=text, text_es="Aviso.")

    def test_society_requires_each_group_once_and_bounded_finite_scores(self):
        scores = [{"group_id": i, "belief_drop": .5, "reaction": "I will check."} for i in range(6)]
        valid = dict(framing_key="B", scores=scores, es_group_en_only_drop=.2)
        self.assertEqual([s.group_id for s in SocietyOut(**valid).scores], list(range(6)))
        for bad in [-.1, 1.1, float("nan")]:
            with self.assertRaises(ValidationError):
                SocietyOut(**{**valid, "es_group_en_only_drop": bad})
        with self.assertRaises(ValidationError):
            SocietyOut(**{**valid, "scores": scores[:5] + [scores[0]]})


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = DiskCache(Path(self.tmp.name), timeout=.02)

    def call(self, fn, mode="live", inputs=None):
        return self.cache.get_or_run("drafter", inputs or {"claim": "one"}, Framing, fn, mode=mode)

    def test_replay_never_calls_provider_and_requires_exact_input(self):
        self.call(framing)
        def forbidden():
            self.fail("Replay contacted provider")
        out = self.call(forbidden, "replay")
        self.assertEqual(out.status, "cached")
        self.assertEqual(out.payload.key, "A")
        with self.assertRaises(CacheMiss):
            self.call(forbidden, "replay", {"claim": "different"})

    def test_hybrid_reuses_cache_but_live_attempts_fresh_generation(self):
        self.call(framing)
        def forbidden():
            self.fail("Hybrid regenerated a cached pipeline result")
        self.assertEqual(self.call(forbidden, "hybrid").status, "cached")
        changed = framing().model_copy(update={"text_en": "A new verified update."})
        self.assertEqual(self.call(lambda: changed).payload.text_en, "A new verified update.")

    def test_timeout_falls_back_without_late_cache_overwrite(self):
        self.call(framing)
        def slow():
            time.sleep(.06)
            return framing().model_copy(update={"text_en": "Late output"})
        self.assertEqual(self.call(slow).status, "cached")
        time.sleep(.08)
        self.assertEqual(self.call(framing, "replay").payload.text_en, "Check official updates.")

    def test_timeout_without_cache_is_not_fabricated_success(self):
        with self.assertRaises(TimeoutError):
            self.call(lambda: time.sleep(.06))

    def test_corrupt_cache_is_a_miss_in_replay_and_repaired_live(self):
        self.call(framing)
        next(Path(self.tmp.name).glob("*.json")).write_text("broken")
        with self.assertRaises(CacheMiss):
            self.call(framing, "replay")
        self.assertEqual(self.call(framing).status, "done")

    def test_invalid_utf8_cache_is_a_miss_and_can_be_repaired(self):
        self.call(framing)
        next(Path(self.tmp.name).glob("*.json")).write_bytes(b"\xff\xfe")
        with self.assertRaises(CacheMiss):
            self.call(framing, "replay")
        self.assertEqual(self.call(framing).status, "done")


if __name__ == "__main__":
    unittest.main()
