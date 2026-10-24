import json
import unittest

import httpx

from backend.clients.grokbots_webhook import GrokBotsWebhookClient, WebhookSettings


class WebhookTests(unittest.TestCase):
    def client(self, handler):
        client = GrokBotsWebhookClient(
            WebhookSettings(url="https://hooks.example.test/firebreak", key="test-secret"),
            transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return client

    def test_sends_observation_and_correlation_id_with_bearer_auth(self):
        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.headers["authorization"], "Bearer test-secret")
            self.assertEqual(json.loads(request.content), {
                "request_id": "round-1", "observation": {"claim": "Fictional claim"}})
            return httpx.Response(200, json={"ignored": "this is not a Bot action"})
        result = self.client(handler).send({"claim": "Fictional claim"}, request_id="round-1")
        self.assertEqual(result.delivery, "accepted")
        self.assertEqual(result.request_id, "round-1")
        self.assertFalse(hasattr(result, "action"))

    def test_timeout_is_unknown_and_never_retried(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("Timeout", request=request)
        result = self.client(handler).send({}, request_id="round-1")
        self.assertEqual(result.delivery, "unknown")
        self.assertEqual(len(calls), 1)

    def test_does_not_follow_redirects_or_forward_credentials(self):
        urls = []
        def handler(request):
            urls.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://other.example.test/"})
        self.assertEqual(self.client(handler).send({}).delivery, "rejected")
        self.assertEqual(urls, ["https://hooks.example.test/firebreak"])

    def test_auth_rate_limit_and_server_failures_are_not_success(self):
        for code, expected in [(401, "rejected"), (429, "rejected"), (503, "unknown")]:
            out = self.client(lambda request: httpx.Response(code)).send({})
            self.assertEqual(out.delivery, expected)
            self.assertEqual(out.http_status, code)

    def test_configuration_rejects_unsafe_urls_and_masks_key(self):
        for url in ["http://hooks.example.test/", "https://user:pass@hooks.example.test/", "https://hooks.example.test/?key=secret"]:
            with self.assertRaises(ValueError):
                WebhookSettings(url=url, key="secret")
        self.assertNotIn("secret", repr(WebhookSettings(url="https://hooks.example.test/", key="secret")))


if __name__ == "__main__":
    unittest.main()
