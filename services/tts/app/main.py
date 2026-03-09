import os
import threading
from pathlib import Path
from uuid import uuid4

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="MirrorMind TTS", version="0.2.0")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TTS_VOICE = os.getenv("TTS_VOICE", "af_heart")
AUDIO_DIR = Path(os.getenv("TTS_AUDIO_DIR", "/tmp/tts_audio"))
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Lazy-loaded Kokoro pipeline (singleton)
# ---------------------------------------------------------------------------
_pipeline = None
_pipeline_lock = threading.Lock()


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                from kokoro import KPipeline

                _pipeline = KPipeline(lang_code="a")  # 'a' = American English
    return _pipeline


def warmup_tts() -> None:
    """
    Prime Kokoro and lazy dependencies during service startup.
    This reduces first-request latency spikes.
    """
    try:
        pipeline = get_pipeline()
        for _gs, _ps, _audio in pipeline("warmup", voice=TTS_VOICE):
            break
        print("[TTS] Warmup complete.")
    except Exception as e:
        print(f"[TTS] Warmup failed: {repr(e)}")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SpeakRequest(BaseModel):
    session_id: str
    chunk_index: int
    text: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup_event() -> None:
    import asyncio

    async def run_warmup_background() -> None:
        await asyncio.get_event_loop().run_in_executor(None, warmup_tts)

    asyncio.create_task(run_warmup_background())


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "tts",
        "engine": "kokoro",
        "voice": TTS_VOICE,
    }


@app.post("/tts/speak")
async def speak(request: SpeakRequest) -> dict:
    import asyncio
    import numpy as np

    chunk_id = f"{request.session_id}_{request.chunk_index}_{uuid4().hex[:6]}"
    wav_path = AUDIO_DIR / f"{chunk_id}.wav"

    # Run synthesis in a thread pool to avoid blocking the event loop
    def synthesize():
        pipeline = get_pipeline()
        segments = []
        for _gs, _ps, audio in pipeline(request.text, voice=TTS_VOICE):
            segments.append(audio)
        return segments

    segments = await asyncio.get_event_loop().run_in_executor(None, synthesize)

    if not segments:
        return {
            "chunk_id": chunk_id,
            "status": "empty",
            "text_chars": len(request.text),
            "audio_url": None,
        }

    full_audio = np.concatenate(segments)
    sf.write(str(wav_path), full_audio, samplerate=24000)

    audio_url = f"/tts/audio/{chunk_id}.wav"

    return {
        "chunk_id": chunk_id,
        "status": "ok",
        "text_chars": len(request.text),
        "audio_url": audio_url,
    }


@app.get("/tts/audio/{filename}")
async def serve_audio(filename: str):
    file_path = AUDIO_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(file_path), media_type="audio/wav")


@app.delete("/tts/session/{session_id}")
async def cleanup_session(session_id: str) -> dict:
    """Remove all audio files for a given session."""
    count = 0
    for f in AUDIO_DIR.glob(f"{session_id}_*"):
        f.unlink(missing_ok=True)
        count += 1
    return {"status": "cleaned", "files_removed": count}
