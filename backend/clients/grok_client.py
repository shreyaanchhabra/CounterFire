"""Grok client (xAI, OpenAI-compatible). Owned by the Grok side; keep the grok_json signature."""
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from .. import config

_grok: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _grok
    if not config.XAI_API_KEY:
        raise RuntimeError("XAI_API_KEY is not set in .env")
    if _grok is None:
        _grok = AsyncOpenAI(api_key=config.XAI_API_KEY, base_url="https://api.x.ai/v1")
    return _grok


async def grok_json(system: str, user: str, schema: type[BaseModel], model: str | None = None, temperature=0.7):
    last = None
    for _ in range(2):
        resp = await client().chat.completions.create(
            model=model or config.GROK_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}},
            temperature=temperature,
        )
        try:
            return schema.model_validate_json(resp.choices[0].message.content)
        except ValidationError as e:
            last = e
    raise last
