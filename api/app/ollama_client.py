import json
from typing import AsyncIterator

import httpx


async def stream_ollama_chat(
  *,
  base_url: str,
  model: str,
  messages: list[dict[str, str]]
) -> AsyncIterator[str]:
  url = f"{base_url.rstrip('/')}/api/chat"
  payload = {
    "model": model,
    "messages": messages,
    "stream": True
  }

  async with httpx.AsyncClient(timeout=None) as client:
    async with client.stream("POST", url, json=payload) as response:
      response.raise_for_status()
      async for line in response.aiter_lines():
        if not line:
          continue

        try:
          parsed = json.loads(line)
        except json.JSONDecodeError:
          continue

        if parsed.get("error"):
          raise RuntimeError(parsed["error"])

        message = parsed.get("message", {})
        token = message.get("content", "")
        if token:
          yield token
