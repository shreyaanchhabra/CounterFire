import json
import unittest

import httpx
from openai import AuthenticationError, BadRequestError
from pydantic import BaseModel

from backend.clients.grok_client import GrokClient, GrokOutputError
from backend.config import Settings


class Answer(BaseModel):
    value: int


def completion(content, *, refusal=None, finish_reason="stop"):
    return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 1,
        "model": "configured-test-model", "choices": [{"index": 0, "finish_reason": finish_reason,
        "message": {"role": "assistant", "content": content, "refusal": refusal}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


class ClientTests(unittest.TestCase):
    def client(self, handler):
        client = GrokClient(Settings(api_key="test-secret", model="configured-test-model"),
                            transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return client

    def test_sends_configured_model_and_validates_structured_json(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://api.x.ai/v1/chat/completions")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "configured-test-model")
            self.assertEqual(body["response_format"]["type"], "json_schema")
            self.assertEqual(body["response_format"]["json_schema"]["schema"]["properties"]["value"]["type"], "integer")
            return completion('{"value": 7}')
        self.assertEqual(self.client(handler).generate("System", "Data", Answer).value, 7)

    def test_retries_invalid_output_once(self):
        calls = []
        def handler(request):
            calls.append(request)
            return completion("not json" if len(calls) == 1 else '{"value": 9}')
        self.assertEqual(self.client(handler).generate("System", "Data", Answer).value, 9)
        self.assertEqual(len(calls), 2)

    def test_stops_after_two_invalid_outputs(self):
        calls = []
        def handler(request):
            calls.append(request)
            return completion("not json")
        with self.assertRaises(GrokOutputError):
            self.client(handler).generate("System", "Data", Answer)
        self.assertEqual(len(calls), 2)

    def test_unsupported_structured_format_falls_back_to_prompted_json(self):
        calls = []
        def handler(request):
            body = json.loads(request.content)
            calls.append(body)
            if len(calls) == 1:
                return httpx.Response(400, json={"error": {"message": "response_format json_schema is not supported", "param": "response_format", "type": "invalid_request_error"}})
            self.assertNotIn("response_format", body)
            self.assertIn('"value"', body["messages"][0]["content"])
            return completion('{"value": 3}')
        self.assertEqual(self.client(handler).generate("System", "Data", Answer).value, 3)
        self.assertEqual(len(calls), 2)

    def test_auth_and_invalid_schema_errors_are_not_format_fallbacks(self):
        for status, message, error in [(401, "Invalid key", AuthenticationError),
                                        (400, "Invalid JSON schema", BadRequestError)]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, json={"error": {"message": message, "type": "invalid_request_error"}})
            with self.assertRaises(error):
                self.client(handler).generate("System", "Data", Answer)
            self.assertEqual(len(calls), 1)

    def test_refusal_and_truncation_are_not_accepted_as_success(self):
        for response in [completion(None, refusal="Cannot answer"), completion('{"value": 3}', finish_reason="length")]:
            with self.assertRaises(GrokOutputError):
                self.client(lambda request: response).generate("System", "Data", Answer)

    def test_missing_credentials_fail_only_when_live_generation_is_requested(self):
        client = GrokClient(Settings())
        self.addCleanup(client.close)
        with self.assertRaisesRegex(ValueError, "XAI_API_KEY"):
            client.generate("System", "Data", Answer)

    def test_lists_models_without_requiring_model_selection(self):
        client = GrokClient(Settings(api_key="test-secret"), transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"object": "list", "data": [
                {"id": "available-model", "object": "model", "created": 1, "owned_by": "xai"}]})))
        self.addCleanup(client.close)
        self.assertEqual(client.list_models(), ["available-model"])


if __name__ == "__main__":
    unittest.main()
