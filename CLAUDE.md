# CLAUDE.md — MirrorMind v1

This file provides guidance for Claude (Anthropic) when working on this repository.

## Project summary

MirrorMind v1 is a real-time AI avatar conversation platform. It streams LLM responses as SSE tokens, forwards text chunks to a TTS service, and pipes TTS audio into a MuseTalk avatar for lip-synced video. The goal is FaceTime-like latency — every stage streams and parallelizes.

## Repository structure

```
frontend/        → Next.js app (App Router) — chat UI, persona selection, avatar panel
api/             → FastAPI backend — SSE streaming, session state, TTS chunk dispatch
  app/main.py    → /health and /chat/stream endpoints
services/tts/    → TTS stub service (FastAPI, phase 2)
services/avatar/ → Avatar stub service (FastAPI, phase 3)
docker/          → docker-compose.yml orchestrating all services
src/             → Legacy CRA app (archived, not actively used)
```

## Key commands

```bash
# Start the full stack (mock mode, no GPU)
docker compose -f docker/docker-compose.yml --env-file .env up --build

# Frontend dev server (standalone)
cd frontend && npm run dev

# API dev server (standalone)
cd api && uvicorn app.main:app --reload --port 8000

# Health check
curl http://localhost:8000/health
```

## Code style and conventions

- **Python (api/)**: Python 3.11+, async everywhere, type hints required. FastAPI patterns. Dependencies in `requirements.txt`.
- **JavaScript (frontend/)**: Next.js App Router. JSX components. Config in `next.config.mjs`.
- **Environment**: All config via `.env`. Never hardcode secrets. Use `os.getenv()` (Python) or `process.env.NEXT_PUBLIC_*` (Next.js).

## Architecture notes

- **Streaming**: `/chat/stream` sends SSE events (`meta`, `token`, `done`, `error`). Tokens stream word-by-word.
- **Personas**: System prompts keyed by persona name (`flirty`, `brutal`, `therapist`). Configured in `PERSONA_PROMPTS` dict in `main.py`.
- **TTS handoff**: Text accumulates in a buffer. When it exceeds `TTS_FLUSH_CHARS` characters, a chunk is POSTed to the TTS service asynchronously.
- **Session state**: In-memory `defaultdict(list)` keyed by session ID. Last 10 messages are kept for LLM context.
- **LLM backends**: Controlled by `STREAM_MODE` env var — `mock` (hardcoded responses), `vllm` (local vLLM server), or `ollama` (local Ollama).

## Important files

| File | Role |
|------|------|
| `api/app/main.py` | Core API routes and streaming logic |
| `api/app/vllm_client.py` | vLLM streaming client |
| `api/app/ollama_client.py` | Ollama streaming client |
| `frontend/app/page.js` | Main chat page |
| `frontend/components/` | Reusable React components |
| `docker/docker-compose.yml` | Full service topology |
| `.env.example` | All environment variable defaults |
| `muse_talk_mirror_mind_v_1.md` | Original architecture design doc |

## Current state

- Phase 1 (text streaming) is complete and working end-to-end.
- TTS and avatar services exist as stubs awaiting real implementation.
- The legacy `src/` directory contains a Create React App that is archived — work in `frontend/` instead.

## Guidelines for changes

1. Keep latency low — do not introduce synchronous blocking in the streaming pipeline.
2. Maintain the SSE event contract (`meta`, `token`, `done`, `error`).
3. New services should follow the existing FastAPI stub pattern in `services/`.
4. Test with `STREAM_MODE=mock` first before connecting real LLM backends.
5. Do not commit `.env`, model weights, or `node_modules`.
