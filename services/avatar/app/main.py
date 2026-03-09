import os
import aiohttp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import asyncio
from typing import Dict

from .musetalk_wrapper import wrapper

app = FastAPI(title="MirrorMind Avatar (MuseTalk)", version="0.2.0")

# Store active sessions and their audio queues
sessions: Dict[str, asyncio.Queue] = {}
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000").rstrip("/")
TTS_BASE_URL = os.getenv("TTS_BASE_URL", "http://tts:8010").rstrip("/")


class LipSyncRequest(BaseModel):
    session_id: str
    audio_url: str
    avatar_image_path: str = "/app/assets/default_avatar.jpg"  # Fallback


@app.on_event("startup")
async def startup_event():
    # Attempt to pre-load models on startup if weights exist
    models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
    wrapper.load_models(models_dir)

    # We should have a default avatar image to pre-load
    wrapper.prepare_avatar("/app/assets/default_avatar.jpg")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "avatar",
        "engine": "musetalk",
        "loaded": wrapper.is_loaded,
    }


@app.get("/assets/{filename}")
async def get_asset(filename: str):
    file_path = f"/app/assets/{filename}"
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Asset not found")


def _audio_fetch_candidates(audio_url: str) -> list[str]:
    """
    Build candidate URLs from relative/absolute audio paths.

    We prefer the API proxy path first (stable from browser + backend),
    then direct TTS service path as a fallback.
    """
    if audio_url.startswith("http://") or audio_url.startswith("https://"):
        return [audio_url]

    path = audio_url if audio_url.startswith("/") else f"/{audio_url}"
    candidates = [f"{API_BASE_URL}{path}"]

    if path.startswith("/tts/audio/"):
        filename = path.rsplit("/", 1)[-1]
        candidates.append(f"{TTS_BASE_URL}/tts/audio/{filename}")

    return candidates


async def fetch_audio_and_queue(session_id: str, audio_url: str):
    """Downloads audio and pushes bytes to the session queue."""
    if session_id not in sessions:
        sessions[session_id] = asyncio.Queue()

    candidates = _audio_fetch_candidates(audio_url)

    try:
        async with aiohttp.ClientSession() as http:
            for url in candidates:
                async with http.get(url) as resp:
                    if resp.status == 200:
                        audio_bytes = await resp.read()
                        await sessions[session_id].put(audio_bytes)
                        print(
                            f"Queued {len(audio_bytes)} audio bytes for {session_id} from {url}"
                        )
                        return
                    print(f"Audio fetch failed for {session_id} from {url}: {resp.status}")

        print(f"Audio fetch exhausted all candidates for {session_id}: {candidates}")
    except Exception as e:
        print(f"Error fetching audio for MuseTalk ({session_id}): {e}")


@app.post("/avatar/lip-sync")
async def lip_sync(request: LipSyncRequest, background_tasks: BackgroundTasks) -> dict:
    """
    Receives an audio URL, triggers background download, and returns the WS URL.
    """
    background_tasks.add_task(fetch_audio_and_queue, request.session_id, request.audio_url)

    return {
        "status": "accepted",
        "session_id": request.session_id,
        "ws_url": f"/avatar/stream/{request.session_id}",
    }


@app.websocket("/avatar/stream/{session_id}")
async def websocket_stream(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint that reads downloaded audio chunks from the queue,
    runs MuseTalk inference, and yields Base64 JPEG frames back to the client.
    """
    await websocket.accept()

    if session_id not in sessions:
        sessions[session_id] = asyncio.Queue()

    try:
        while True:
            # Wait for the next audio chunk to arrive from the POST route
            audio_bytes = await sessions[session_id].get()
            sent_frames = 0

            # Run MuseTalk inference (async generator yielding Base64 strings)
            async for frame_b64 in wrapper.generate_frames(audio_bytes):
                await websocket.send_text(frame_b64)
                sent_frames += 1

            print(f"Sent {sent_frames} frames for session {session_id}")

            sessions[session_id].task_done()

    except WebSocketDisconnect:
        print(f"Client disconnected for session: {session_id}")
        if session_id in sessions:
            del sessions[session_id]
