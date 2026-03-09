# MirrorMind v1 — Agent Instructions

You are working on **MirrorMind v1**, a real-time AI avatar conversation platform. Read this file before making any changes to understand the project, its conventions, and its architecture.

## Project overview

MirrorMind creates a FaceTime-like experience where a user chats with an AI persona backed by:

1. **LLM streaming** (text generation via vLLM, Ollama, or mock mode)
2. **TTS** (text-to-speech, consuming streamed text chunks)
3. **Avatar lip-sync** (MuseTalk consuming TTS audio to animate a portrait)

The guiding principle is **low latency over perfection** — stream and parallelize every stage.

## Repository layout

```
frontend/          → Next.js UI (token streaming, persona picker, avatar panel)
api/               → FastAPI orchestration (SSE streaming, TTS chunk handoff)
  app/main.py      → Core API: /health, /chat/stream (SSE)
  app/vllm_client.py
  app/ollama_client.py
docker/
  docker-compose.yml
services/
  tts/             → FastAPI stub (phase 2 integration point)
  avatar/          → FastAPI stub (phase 3 integration point)
assets/avatars/    → Source portrait images
models/            → Model weights / cache (gitignored)
src/               → Legacy Create React App (not actively used)
```

## Tech stack

| Layer     | Technology                            |
|-----------|---------------------------------------|
| Frontend  | Next.js, React                        |
| API       | FastAPI, Python 3.11+, httpx          |
| LLM       | vLLM or Ollama (OpenAI-compatible)    |
| TTS       | Kokoro (Integrated & Verified)        |
| Avatar    | MuseTalk (Integrated & Building)     |
| Infra     | Docker Compose, optional Redis        |
| Deploy    | RunPod (RTX 4090 Pod)                 |

## Key environment variables

Defined in `.env` (copy from `.env.example`):

| Variable              | Purpose                            |
|-----------------------|------------------------------------|
| `STREAM_MODE`         | `mock`, `vllm`, or `ollama`        |
| `MODEL_NAME`          | LLM model identifier               |
| `VLLM_BASE_URL`       | vLLM server URL                    |
| `OLLAMA_BASE_URL`     | Ollama server URL                  |
| `OLLAMA_MODEL`        | Ollama model tag                   |
| `TTS_BASE_URL`        | TTS service URL                    |
| `AVATAR_BASE_URL`     | Avatar (MuseTalk) service URL      |
| `TTS_FLUSH_CHARS`     | Buffer size before flushing to TTS |
| `NEXT_PUBLIC_API_URL`  | Frontend → API base URL           |

## Architecture patterns

- **SSE streaming** — The `/chat/stream` endpoint uses Server-Sent Events. Tokens stream as `event: token`, metadata as `event: meta`, completion as `event: done`.
- **Persona system** — Three personas (`flirty`, `brutal`, `therapist`) control the system prompt. Default is `therapist`.
- **TTS chunk handoff** — As tokens accumulate past `TTS_FLUSH_CHARS`, chunks are POSTed to the TTS service asynchronously via `asyncio.create_task`.
- **Session memory** — In-memory `defaultdict(list)` keyed by session ID. Last 10 messages kept for context.

## Conventions

- **Python**: Type hints required. Use `async/await` for I/O. Follow FastAPI patterns.
- **Frontend**: Next.js App Router. Components in `frontend/components/`. Pages in `frontend/app/`.
- **Docker**: Each service has its own `Dockerfile`. Compose ties them together.
- **Secrets**: Never hardcode. All secrets go in `.env` (gitignored). Reference via `os.getenv()` in Python, `process.env` or `NEXT_PUBLIC_*` in Next.js.
- **No large files in git**: Models, weights, and caches belong in `models/` (gitignored).

## Build phases (current roadmap)

| Phase | Goal                          | Status       |
|-------|-------------------------------|--------------|
| 1     | Fast text streaming loop      | ✅ Complete   |
| 2     | Low-latency TTS integration   | ✅ Complete   |
| 3     | MuseTalk avatar lip-sync      | ✅ Complete   |
| 4     | Polish (idle anim, LivePortrait, voice quality) | 🔲 Planned |

## Running locally

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml --env-file .env up --build
# Frontend: http://localhost:3000
# API:      http://localhost:8000/health
```

## Current status & testing

1.  **TTS**: Fully integrated. Audio plays automatically in the browser after text streaming.
2.  **Avatar**: 
    - Container is running and weights are being verified (see `docker logs mirrormind-v1-avatar-1`).
    - The code already supports WebSocket frame streaming to the frontend `<canvas>`.
    - **To test**: Once logs show "All weights downloaded", simply send a message in the UI.

## Troubleshooting
- **No Audio?** Click the 🔒 icon in Chrome and ensure "Sound" is allowed.
- **No Avatar?** Check if the GPU is recognized inside the container with `docker exec mirrormind-v1-avatar-1 nvidia-smi`.
