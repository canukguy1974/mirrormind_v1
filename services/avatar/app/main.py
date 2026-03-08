from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="MirrorMind Avatar Stub", version="0.1.0")


class LipSyncRequest(BaseModel):
  session_id: str
  audio_url: str
  avatar_image_path: str


@app.get("/health")
async def health() -> dict:
  return {"status": "ok", "service": "avatar"}


@app.post("/avatar/lip-sync")
async def lip_sync(request: LipSyncRequest) -> dict:
  return {
    "status": "accepted",
    "session_id": request.session_id,
    "stream_url": f"/avatar/stream/{request.session_id}.m3u8"
  }
