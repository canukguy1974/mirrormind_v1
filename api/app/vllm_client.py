import json
from typing import AsyncIterator

import httpx


async def stream_vllm_chat(
  *,
  base_url: str,
  model: str,
  messages: list[dict[str, str]],
  temperature: float = 0.7
) -> AsyncIterator[str]:
  url = f"{base_url.rstrip('/')}/v1/chat/completions"
  payload = {
    "model": model,
    "messages": messages,
    "stream": True,
    "temperature": temperature
  }

  async with httpx.AsyncClient(timeout=None) as client:
    async with client.stream("POST", url, json=payload) as response:
      response.raise_for_status()
      async for line in response.aiter_lines():
        if not line or not line.startswith("data:"):
          continue

        data = line[5:].strip()
        if data == "[DONE]":
          break

        try:
          parsed = json.loads(data)
        except json.JSONDecodeError:
          continue

        choices = parsed.get("choices", [])
        if not choices:
          continue

        token = choices[0].get("delta", {}).get("content", "")
        if token:
          yield token
