"""Official Grok Bot routine trigger, distinct from Grok chat automations.

Reference: https://cursor.com/help/grok-bot/routines
HTTP 200 acknowledges a started run. It does not contain the Bot's result.
"""

import math
import os
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel


@dataclass(frozen=True)
class WebhookSettings:
    # URLs can also contain routing identifiers. Avoid exposing either in repr.
    url: str = field(repr=False)
    key: str = field(repr=False)
    timeout: float = 10

    def __post_init__(self):
        parsed = urlsplit(self.url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
                parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Webhook URL must be HTTPS, with no credentials, query, or fragment")
        if not self.key.strip() or any(c.isspace() for c in self.key):
            raise ValueError("Webhook key must be a nonempty bearer token")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Webhook timeout must be finite and positive")

    @classmethod
    def from_env(cls):
        url = os.getenv("GROKBOTS_WEBHOOK_URL", "").strip()
        key = os.getenv("GROKBOTS_WEBHOOK_KEY", "").strip()
        if not url or not key:
            raise ValueError("Set GROKBOTS_WEBHOOK_URL and GROKBOTS_WEBHOOK_KEY from the routine's Webhook settings")
        return cls(url=url, key=key)


class DispatchReceipt(BaseModel):
    request_id: str
    delivery: Literal["accepted", "rejected", "unknown"]
    http_status: int | None = None


class GrokBotsWebhookClient:
    def __init__(self, settings: WebhookSettings, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._client = httpx.Client(transport=transport, timeout=settings.timeout, follow_redirects=False)

    def send(self, observation: dict, *, request_id: str | None = None) -> DispatchReceipt:
        identifier = request_id or str(uuid4())
        if not identifier.strip():
            raise ValueError("Request ID must not be blank")
        try:
            response = self._client.post(self.settings.url,
                headers={"Authorization": f"Bearer {self.settings.key}"},
                json={"request_id": identifier, "observation": observation})
        except httpx.TransportError:
            # The request might already have reached the server. Never retry blindly.
            return DispatchReceipt(request_id=identifier, delivery="unknown")
        delivery = ("accepted" if response.status_code == 200 else
                    "unknown" if response.status_code >= 500 else "rejected")
        # Do not include arbitrary upstream bodies, headers, or URLs in receipts.
        return DispatchReceipt(request_id=identifier, delivery=delivery, http_status=response.status_code)

    def close(self):
        self._client.close()
