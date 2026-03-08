import asyncio
import json
import os
from collections import defaultdict
from typing import AsyncIterator
from uuid import uuid4

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .vllm_client import stream_vllm_chat

STREAM_MODE = os.getenv("STREAM_MODE", "mock").lower()
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8001")
TTS_BASE_URL = os.getenv("TTS_BASE_URL", "http://localhost:8010")
AVATAR_BASE_URL = os.getenv("AVATAR_BASE_URL", "http://localhost:8020")
TTS_FLUSH_CHARS = int(os.getenv("TTS_FLUSH_CHARS", "48"))

PERSONA_PROMPTS = {
  "flirty": "You are playful, witty, and warm. Keep responses concise.",
  "brutal": "You are direct and honest. Keep responses constructive and concise.",
  "therapist": "You are calm and supportive. Help the user think clearly in short steps."
}

SESSIONS: dict[str, list[dict[str, str]]] = defaultdict(list)

app = FastAPI(title="MirrorMind API", version="0.1.0")

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"]
)


def sse_event(event_name: str, payload: dict) -> str:
  data = json.dumps(payload, ensure_ascii=True)
  return f"event: {event_name}\ndata: {data}\n\n"


async def stream_mock_tokens(message: str, persona: str) -> AsyncIterator[str]:
  intro = {
    "flirty": "Short answer, but make it sparkle.",
    "brutal": "Direct answer, no fluff.",
    "therapist": "Gentle answer, practical focus."
  }.get(persona, "Practical answer.")

  response = (
    f"{intro} You said: '{message}'. "
    "The live stack is working, so next wire TTS and MuseTalk in parallel."
  )

  for token in response.split(" "):
    yield f"{token} "
    await asyncio.sleep(0.05)


async def push_tts_chunk(text: str, session_id: str, chunk_index: int) -> None:
  if not TTS_BASE_URL:
    return

  payload = {
    "session_id": session_id,
    "chunk_index": chunk_index,
    "text": text
  }

  try:
    async with httpx.AsyncClient(timeout=4) as client:
      await client.post(f"{TTS_BASE_URL.rstrip('/')}/tts/speak", json=payload)
  except Exception:
    return


def persona_prompt(persona: str) -> str:
  return PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["therapist"])


@app.get("/health")
async def health() -> dict:
  return {
    "status": "ok",
    "stream_mode": STREAM_MODE,
    "model_name": MODEL_NAME,
    "avatar_base_url": AVATAR_BASE_URL
  }


@app.get("/chat/stream")
async def chat_stream(
  message: str = Query(..., min_length=1),
  persona: str = Query("therapist"),
  session_id: str | None = Query(None)
):
  sid = session_id or f"sess_{uuid4().hex[:10]}"
  history = SESSIONS[sid]

  messages = [{"role": "system", "content": persona_prompt(persona)}]
  messages.extend(history[-10:])
  messages.append({"role": "user", "content": message})

  async def event_stream() -> AsyncIterator[str]:
    full_text = ""
    tts_buffer = ""
    tts_chunk_index = 0

    yield sse_event(
      "meta",
      {
        "session_id": sid,
        "stream_mode": STREAM_MODE
      }
    )

    try:
      if STREAM_MODE == "vllm":
        token_stream = stream_vllm_chat(
          base_url=VLLM_BASE_URL,
          model=MODEL_NAME,
          messages=messages
        )
      else:
        token_stream = stream_mock_tokens(message=message, persona=persona)

      async for token in token_stream:
        full_text += token
        tts_buffer += token
        yield sse_event("token", {"token": token})

        if len(tts_buffer) >= TTS_FLUSH_CHARS:
          tts_chunk_index += 1
          asyncio.create_task(push_tts_chunk(tts_buffer, sid, tts_chunk_index))
          tts_buffer = ""

      if tts_buffer.strip():
        tts_chunk_index += 1
        asyncio.create_task(push_tts_chunk(tts_buffer, sid, tts_chunk_index))

      history.append({"role": "user", "content": message})
      history.append({"role": "assistant", "content": full_text})

      yield sse_event(
        "done",
        {
          "text": full_text.strip(),
          "session_id": sid,
          "tts_chunks_sent": tts_chunk_index
        }
      )
    except Exception as exc:
      yield sse_event("error", {"message": str(exc)})

  return StreamingResponse(
    event_stream(),
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no"
    }
  )
