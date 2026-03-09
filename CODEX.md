# CODEX.md — MirrorMind v1

Instructions for OpenAI Codex when working on this repository.

## What this project is

MirrorMind v1 is a real-time AI avatar conversation app. A user sends a message, the backend streams LLM tokens via SSE, dispatches text chunks to a TTS service, and feeds TTS audio into MuseTalk for lip-synced avatar video. Everything streams — nothing blocks.

## Repo map

```
frontend/            Next.js (App Router) — chat UI + avatar panel
api/                 FastAPI — SSE streaming + TTS chunk dispatch
  app/main.py        Core routes: /health, /chat/stream
  app/vllm_client.py vLLM streaming helper
  app/ollama_client.py Ollama streaming helper
services/tts/        TTS stub (FastAPI)
services/avatar/     Avatar stub (FastAPI)
docker/              docker-compose.yml
src/                 Legacy CRA app (archived)
models/              Model weights (gitignored)
assets/avatars/      Source portrait images
```

## Setup

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml --env-file .env up --build
```

- Frontend → `http://localhost:3000`
- API → `http://localhost:8000/health`
- Default mode is `STREAM_MODE=mock` (no GPU needed).

## Environment variables

See `.env.example` for the full list. Key ones:

- `STREAM_MODE` — `mock` | `vllm` | `ollama`
- `MODEL_NAME` — LLM model (default: `Qwen/Qwen2.5-7B-Instruct`)
- `TTS_FLUSH_CHARS` — character count before flushing a TTS chunk (default: 48)
- `NEXT_PUBLIC_API_URL` — API URL for the frontend

## How streaming works

1. Client hits `GET /chat/stream?message=...&persona=...&session_id=...`
2. API builds a message list (system prompt + last 10 messages + user message).
3. Tokens stream from the LLM backend and are emitted as SSE `event: token`.
4. Every `TTS_FLUSH_CHARS` characters, a chunk is POSTed async to the TTS service.
5. On completion, `event: done` is emitted with the full text and session info.

## Code conventions

### Python (api/, services/)
- Python 3.11+
- Async-first (`async def`, `await`, `asyncio.create_task`)
- Type hints on all function signatures
- FastAPI for all HTTP services
- Dependencies listed in `requirements.txt`

### JavaScript (frontend/)
- Next.js App Router
- Components in `frontend/components/`
- Pages in `frontend/app/`
- Public env vars use `NEXT_PUBLIC_` prefix

### General
- Secrets in `.env` only — never hardcode
- Each service gets its own `Dockerfile`
- Large files (models, weights) go in `models/` (gitignored)

## Build phases

1. ✅ **Text streaming** — LLM → SSE → UI (done)
2. 🔲 **TTS** — Real TTS integration replacing `services/tts/` stub
3. 🔲 **Avatar** — MuseTalk integration replacing `services/avatar/` stub
4. 🔲 **Polish** — Idle animation, LivePortrait expressions, voice quality

## Rules

- Never block the streaming pipeline synchronously.
- Keep the SSE event contract: `meta`, `token`, `done`, `error`.
- New backend services should follow the FastAPI stub pattern in `services/`.
- Always test changes in mock mode first (`STREAM_MODE=mock`).
- Do not commit `.env`, `node_modules`, `__pycache__`, or model files.
- The `src/` directory is legacy — all frontend work happens in `frontend/`.
