import asyncio
import json
import os
from collections import defaultdict
from typing import AsyncIterator
from uuid import uuid4

import httpx
import websockets
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .ollama_client import stream_ollama_chat
from .vllm_client import stream_vllm_chat

STREAM_MODE = os.getenv("STREAM_MODE", "mock").lower()
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8001")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", MODEL_NAME)
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


async def push_tts_chunk(text: str, session_id: str, chunk_index: int) -> str | None:
  """Send text to TTS service and return the audio URL, or None on failure."""
  if not TTS_BASE_URL:
    return None

  payload = {
    "session_id": session_id,
    "chunk_index": chunk_index,
    "text": text
  }

  # First chunk often pays model warm-up cost; allow one retry.
  timeouts = [30, 60]
  for attempt, timeout_s in enumerate(timeouts, start=1):
    try:
      async with httpx.AsyncClient(timeout=timeout_s) as client:
        print(
          f"[TTS] sending chunk {session_id}:{chunk_index} "
          f"({len(text)} chars) attempt={attempt} timeout={timeout_s}s"
        )
        resp = await client.post(f"{TTS_BASE_URL.rstrip('/')}/tts/speak", json=payload)
        if resp.status_code != 200:
          print(
            f"[TTS] non-200 for {session_id}:{chunk_index} -> "
            f"{resp.status_code} {resp.text[:300]}"
          )
          continue

        data = resp.json()
        audio_url = data.get("audio_url")
        if not audio_url:
          print(f"[TTS] missing audio_url for {session_id}:{chunk_index} payload={data}")
        else:
          print(f"[TTS] ready chunk {session_id}:{chunk_index} -> {audio_url}")
          return audio_url
    except Exception as e:
      print(
        f"[TTS] error for {session_id}:{chunk_index} "
        f"attempt={attempt}: {repr(e)}"
      )
    await asyncio.sleep(0.2 * attempt)

  return None

async def trigger_avatar_sync(audio_url: str, session_id: str) -> None:
  """Tells the avatar service to generate frames for this audio chunk."""
  if not AVATAR_BASE_URL:
    return

  payload = {
    "session_id": session_id,
    "audio_url": audio_url,
    "avatar_image_path": "/app/assets/default_avatar.jpg"
  }

  # Avatar may still be initializing; retry a couple of times.
  for attempt in (1, 2):
    try:
      async with httpx.AsyncClient(timeout=15) as client:
        await client.post(f"{AVATAR_BASE_URL.rstrip('/')}/avatar/lip-sync", json=payload)
        return
    except Exception as e:
      print(f"Failed to trigger avatar sync attempt={attempt}: {repr(e)}")
      await asyncio.sleep(0.15 * attempt)


def persona_prompt(persona: str) -> str:
  return PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["therapist"])


@app.get("/health")
async def health() -> dict:
  llm_target = {
    "mock": "mock",
    "vllm": VLLM_BASE_URL,
    "ollama": OLLAMA_BASE_URL
  }.get(STREAM_MODE, "unknown")

  return {
    "status": "ok",
    "stream_mode": STREAM_MODE,
    "model_name": MODEL_NAME,
    "ollama_model": OLLAMA_MODEL,
    "llm_target": llm_target,
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
    
    event_queue = asyncio.Queue()
    pending_audio: dict[int, dict] = {}
    next_audio_index = 1

    # Track active background tasks
    active_tasks = 0
    producer_finished = False

    async def process_tts_pipeline(text, session_id, index, queue):
      nonlocal active_tasks
      try:
        url = await push_tts_chunk(text, session_id, index)
        if url:
          await trigger_avatar_sync(url, session_id)
          await queue.put(("audio", {"audio_url": url, "chunk_index": index}))
      finally:
        active_tasks -= 1
        if producer_finished and active_tasks == 0:
          await queue.put(("producer_done", None))

    # Task to feed tokens into the queue and trigger background TTS
    async def token_producer():
      nonlocal full_text, tts_buffer, tts_chunk_index, active_tasks, producer_finished
      try:
        await event_queue.put(("meta", {"session_id": sid, "stream_mode": STREAM_MODE}))
        
        if STREAM_MODE == "vllm":
          token_stream = stream_vllm_chat(base_url=VLLM_BASE_URL, model=MODEL_NAME, messages=messages)
        elif STREAM_MODE == "ollama":
          token_stream = stream_ollama_chat(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL, messages=messages)
        elif STREAM_MODE == "mock":
          token_stream = stream_mock_tokens(message=message, persona=persona)
        else:
          await event_queue.put(("error", {"message": "Unsupported STREAM_MODE"}))
          return

        async for token in token_stream:
          full_text += token
          tts_buffer += token
          await event_queue.put(("token", {"token": token}))

          if len(tts_buffer) >= TTS_FLUSH_CHARS:
            tts_chunk_index += 1
            active_tasks += 1
            asyncio.create_task(process_tts_pipeline(tts_buffer, sid, tts_chunk_index, event_queue))
            tts_buffer = ""

        if tts_buffer.strip():
          tts_chunk_index += 1
          active_tasks += 1
          asyncio.create_task(process_tts_pipeline(tts_buffer, sid, tts_chunk_index, event_queue))
        
        producer_finished = True
        if active_tasks == 0:
          await event_queue.put(("producer_done", None))
      except Exception as exc:
        await event_queue.put(("error", {"message": str(exc)}))

    producer_task = asyncio.create_task(token_producer())
    
    while True:
      event_type, payload = await event_queue.get()
      if event_type == "producer_done":
        while next_audio_index in pending_audio:
          yield sse_event("audio", pending_audio.pop(next_audio_index))
          next_audio_index += 1

        # Check if history needs updates here
        SESSIONS[sid].append({"role": "user", "content": message})
        SESSIONS[sid].append({"role": "assistant", "content": full_text})
        
        yield sse_event("done", {
          "text": full_text.strip(),
          "session_id": sid,
          "tts_chunks_sent": tts_chunk_index
        })
        break
      elif event_type == "error":
        yield sse_event("error", payload)
        break
      elif event_type == "audio":
        chunk_index = int(payload.get("chunk_index", 0))
        if chunk_index == next_audio_index:
          yield sse_event("audio", payload)
          next_audio_index += 1
          while next_audio_index in pending_audio:
            yield sse_event("audio", pending_audio.pop(next_audio_index))
            next_audio_index += 1
        else:
          pending_audio[chunk_index] = payload
      else:
        yield sse_event(event_type, payload)

  return StreamingResponse(
    event_stream(),
    media_type="text/event-stream",
    headers={
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no"
    }
  )


@app.get("/tts/audio/{filename}")
async def proxy_tts_audio(filename: str):
  """Proxy TTS audio files so the browser doesn't need direct TTS access."""
  url = f"{TTS_BASE_URL.rstrip('/')}/tts/audio/{filename}"
  try:
    async with httpx.AsyncClient(timeout=10) as client:
      resp = await client.get(url)
      if resp.status_code != 200:
        return Response(content='{"error":"not found"}', status_code=404,
                        media_type="application/json")
      return Response(
        content=resp.content,
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=300"}
      )
  except Exception:
    return Response(content='{"error":"tts unavailable"}', status_code=502,
                    media_type="application/json")


@app.websocket("/avatar/stream/{session_id}")
async def proxy_avatar_stream(websocket: WebSocket, session_id: str):
  """Proxy the WebSocket stream from the Avatar container to the frontend."""
  await websocket.accept()
  
  if not AVATAR_BASE_URL:
    await websocket.close()
    return
    
  target_ws_url = f"{AVATAR_BASE_URL.replace('http', 'ws').rstrip('/')}/avatar/stream/{session_id}"
  
  try:
    async with websockets.connect(target_ws_url) as backend_ws:
      # We only need one-way streaming for frames (Backend -> Frontend)
      async for message in backend_ws:
        await websocket.send_text(message)
  finally:
    await websocket.close()


@app.get("/avatar/portrait")
async def get_avatar_portrait():
  """Proxy the static avatar portrait image."""
  # The avatar service serves assets locally; we can either fetch from it or use a default.
  # For MVP, we know it's at /app/assets/default_avatar.jpg in the avatar container.
  # But the avatar container doesn't have a GET route for assets yet, so we'll add one
  # or just proxy it if we add a route there. 
  # Actually, the avatar container DOES NOT have a route for this yet.
  # Let's just point to a placeholder or add a route to avatar/app/main.py too.
  url = f"{AVATAR_BASE_URL.rstrip('/')}/assets/default_avatar.jpg"
  try:
    async with httpx.AsyncClient(timeout=5) as client:
      resp = await client.get(url)
      if resp.status_code == 200:
        return Response(content=resp.content, media_type="image/jpeg")
  except Exception:
    pass
  
  # Fallback to a simple 1x1 transparent pixel or 404
  return Response(status_code=404)
