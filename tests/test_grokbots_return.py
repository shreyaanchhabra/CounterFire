import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
import httpx

from backend.grokbots_return import JobStore, RoundTask, create_app
from backend.grokbots_return import callback_observation
from backend.clients.grokbots_webhook import GrokBotsWebhookClient, WebhookSettings


class ReturnTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = JobStore(Path(self.tmp.name) / "jobs.sqlite3")
        self.client = TestClient(create_app(self.store))
        self.addCleanup(self.client.close)
        self.task = RoundTask(episode_id="episode-test", round_id=1, group_id=0,
                              observation={"messages": ["Fictional rumor."], "synthetic": True})
        self.job = self.store.create(self.task)

    def result(self, **updates):
        return {"request_id": self.job.request_id, "episode_id": "episode-test", "round_id": 1,
                "group_id": 0, "observation_hash": self.job.observation_hash,
                "action": "verify", "belief": .4, "message": None,
                "reason": "I need a source before sharing.", **updates}

    def post(self, data=None, token=None):
        return self.client.post(f"/api/results/{self.job.request_id}",
            headers={"Authorization": "Bearer " + (token or self.job.callback_token)},
            json=data or self.result())

    def test_valid_result_is_durable_and_contains_no_stored_bearer(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        reopened = JobStore(self.store.path)
        result = reopened.get(self.job.request_id)
        self.assertEqual(result["result"]["action"], "verify")
        self.assertEqual(result["result"]["belief"], .4)
        self.assertNotIn(self.job.callback_token.encode(), self.store.path.read_bytes())

    def test_wrong_or_missing_capability_is_rejected(self):
        self.assertEqual(self.post(token="wrong").status_code, 401)
        self.assertEqual(self.client.post(f"/api/results/{self.job.request_id}",json=self.result()).status_code, 401)
        self.assertEqual(self.store.get(self.job.request_id)["status"], "pending")

    def test_mismatched_round_group_episode_or_observation_never_completes(self):
        for update in [{"round_id": 2}, {"group_id": 1}, {"episode_id": "other"},
                       {"observation_hash": "0" * 64}, {"request_id": "other"}]:
            self.assertEqual(self.post(self.result(**update)).status_code, 409)
        self.assertEqual(self.store.get(self.job.request_id)["status"], "pending")

    def test_duplicate_is_idempotent_but_conflicting_result_is_rejected(self):
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().json()["duplicate"], True)
        self.assertEqual(self.post(self.result(action="wait")).status_code, 409)
        self.assertEqual(self.store.get(self.job.request_id)["result"]["action"], "verify")

    def test_expired_or_superseded_tasks_are_rejected(self):
        expired = self.store.create(self.task, ttl=1, now=1)
        response = self.client.post(f"/api/results/{expired.request_id}",
            headers={"Authorization": "Bearer " + expired.callback_token}, json=self.result())
        self.assertEqual(response.status_code, 410)
        self.assertEqual(self.post().status_code, 409)

    def test_oversized_invalid_and_out_of_range_results_are_rejected(self):
        self.assertEqual(self.post(self.result(belief=1.1)).status_code, 422)
        self.assertEqual(self.post(self.result(action="approve")).status_code, 422)
        self.assertEqual(self.post(self.result(reason="x" * 70000)).status_code, 413)

    def test_service_does_not_expose_jobs_docs_or_approval_controls(self):
        for path in ["/", "/docs", "/openapi.json", "/api/jobs", "/api/approve"]:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_scoped_task_pull_requires_capability_and_expires(self):
        path=f'/api/tasks/{self.job.request_id}'
        self.assertEqual(self.client.get(path).status_code,401)
        headers={'Authorization':'Bearer '+self.job.callback_token}
        response=self.client.get(path,headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['task']['observation'],self.task.observation)
        self.assertEqual(response.json()['observation_hash'],self.job.observation_hash)
        self.assertNotIn('token',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.post()
        self.assertEqual(self.client.get(path,headers=headers).status_code,409)

    def test_dispatch_packet_contains_task_scoped_callback_and_result_schema(self):
        packet = callback_observation(self.task, self.job, "https://example.trycloudflare.com")
        self.assertEqual(packet["callback"]["url"], "https://example.trycloudflare.com/api/results/" + self.job.request_id)
        self.assertEqual(packet["callback"]["token"], self.job.callback_token)
        self.assertEqual(packet["task"]["observation"]["messages"], ["Fictional rumor."])
        self.assertEqual(packet["result_schema"]["properties"]["action"]["enum"],
                         ["share", "question", "verify", "reply", "retract", "wait"])
        for base in ["http://example.com", "https://user:pass@example.com", "https://example.com/?token=secret"]:
            with self.assertRaises(ValueError):
                callback_observation(self.task, self.job, base)

    def test_webhook_receipt_is_not_completion_until_authenticated_result_arrives(self):
        transmitted = []
        def native_trigger(request):
            transmitted.append(json.loads(request.content))
            return httpx.Response(200)
        sender = GrokBotsWebhookClient(WebhookSettings(url="https://hooks.example.test/", key="fake-key"),
                                      transport=httpx.MockTransport(native_trigger))
        self.addCleanup(sender.close)
        observation = callback_observation(self.task, self.job, "https://example.trycloudflare.com")
        receipt = sender.send(observation, request_id=self.job.request_id)
        self.assertEqual(receipt.delivery, "accepted")
        self.assertEqual(self.store.get(self.job.request_id)["status"], "pending")
        delivered = transmitted[0]
        result = self.result(request_id=delivered["request_id"],
                             observation_hash=delivered["observation"]["observation_hash"])
        response = self.client.post("/api/results/" + delivered["request_id"],
            headers={"Authorization": "Bearer " + delivered["observation"]["callback"]["token"]}, json=result)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.get(self.job.request_id)["result"]["action"], "verify")


if __name__ == "__main__":
    unittest.main()
