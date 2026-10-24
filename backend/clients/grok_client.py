"""Small xAI adapter using the installed OpenAI-compatible SDK.

Reference: https://docs.x.ai/developers/model-capabilities/text/structured-outputs
No social network tools are enabled.
"""

import json
import time

import httpx
from openai import BadRequestError, OpenAI
from pydantic import ValidationError

from backend.config import Settings
from backend.schemas import T


class GrokOutputError(RuntimeError):
    pass


class GrokClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self._client = None

    @property
    def identity(self):
        return "xai-api-v1"

    def _sdk(self):
        if not self.settings.api_key:
            raise ValueError("Set XAI_API_KEY in .env before making live Grok calls")
        if self._client is None:
            self._client = OpenAI(api_key=self.settings.api_key, base_url="https://api.x.ai/v1",
                                  max_retries=0, timeout=self.settings.timeout,
                                  http_client=httpx.Client(transport=self.transport,
                                                           timeout=self.settings.timeout))
        return self._client

    def list_models(self) -> list[str]:
        return sorted(model.id for model in self._sdk().models.list().data)

    def generate(self, system: str, user: str, schema: type[T], *, model: str | None = None) -> T:
        selected = model or self.settings.model
        sdk = self._sdk()
        if not selected:
            raise ValueError("Set GROK_MODEL to an ID returned by --list-models")
        json_schema = schema.model_json_schema()
        deadline = time.monotonic() + self.settings.timeout
        structured = True
        invalid_attempts = 0
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Grok exceeded its time budget")
            request = dict(model=selected, messages=messages, temperature=.7, timeout=remaining)
            if structured:
                request["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": schema.__name__, "schema": json_schema, "strict": True}}
            else:
                request["messages"] = [{"role": "system", "content": system +
                    "\nReturn only JSON matching this schema: " + json.dumps(json_schema)}, *messages[1:]]
            try:
                response = sdk.chat.completions.create(**request)
            except BadRequestError as exc:
                # Do not hide invalid schemas, authentication errors, or bad model IDs.
                body = exc.body if isinstance(exc.body, dict) else {}
                error = body.get("error", body)
                message = str(error.get("message", "")).lower() if isinstance(error, dict) else ""
                if structured and ("response_format" in message or "json_schema" in message) and any(
                    word in message for word in ("not supported", "unsupported", "does not support")):
                    structured = False
                    continue
                raise
            if not response.choices:
                raise GrokOutputError("Grok returned no choices")
            choice = response.choices[0]
            if choice.message.refusal:
                raise GrokOutputError("Grok declined the request")
            if choice.finish_reason != "stop":
                raise GrokOutputError("Grok response was incomplete")
            try:
                return schema.model_validate_json(choice.message.content or "")
            except ValidationError as exc:
                if invalid_attempts >= 1:
                    raise GrokOutputError("Grok returned invalid output after one retry") from exc
                invalid_attempts += 1
                messages.append({"role": "user", "content":
                    "The response was invalid. Return complete JSON matching this schema: " + json.dumps(json_schema)})

    def close(self):
        if self._client is not None:
            self._client.close()


def grok_json(system: str, user: str, schema: type[T], model: str | None = None) -> T:
    """Convenience API matching the build plan. Reuse GrokClient for agent runs."""
    client = GrokClient(Settings.from_env())
    try:
        return client.generate(system, user, schema, model=model)
    finally:
        client.close()
