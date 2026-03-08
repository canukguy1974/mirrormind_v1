from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="MirrorMind TTS Stub", version="0.1.0")


class SpeakRequest(BaseModel):
  session_id: str
  chunk_index: int
  text: str


@app.get("/health")
async def health() -> dict:
  return {"status": "ok", "service": "tts"}


@app.post("/tts/speak")
async def speak(request: SpeakRequest) -> dict:
  chunk_id = f"{request.session_id}_{request.chunk_index}_{uuid4().hex[:6]}"
  return {
    "chunk_id": chunk_id,
    "status": "accepted",
    "text_chars": len(request.text),
    "audio_url": f"/tts/audio/{chunk_id}.wav"
  }
