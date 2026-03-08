# MirrorMind v1 Onboarding

This repo now contains a practical v1 scaffold aligned to `muse_talk_mirror_mind_v_1.md`.

## What was here before

- Existing app was **Create React App**, not Next.js.
- Useful reusable piece: persona concept (`Flirty AF`, `Brutally Honest`, `Therapist`).
- Legacy `src/components/mirrormind-agent.jsx` has been switched to env vars (`REACT_APP_DID_CLIENT_KEY`, `REACT_APP_DID_AGENT_ID`) so secrets are no longer hardcoded.

## Current project structure

```text
frontend/          # Next.js UI (token streaming + persona selection + avatar panel placeholder)
api/               # FastAPI orchestration API (SSE stream, vLLM mode, TTS chunk handoff)
docker/
  docker-compose.yml
services/
  tts/             # FastAPI stub service (phase 2 integration point)
  avatar/          # FastAPI stub service (phase 3 integration point)
assets/
  avatars/         # put source portrait assets here
models/            # mount model/cache storage here
```

## Fast start (local)

1. Copy env defaults:
   - `cp .env.example .env` (PowerShell: `Copy-Item .env.example .env`)
2. Start baseline stack (no GPU required):
   - `docker compose -f docker/docker-compose.yml --env-file .env up --build`
3. Open:
   - Frontend: `http://localhost:3000`
   - API health: `http://localhost:8000/health`

This runs in `STREAM_MODE=mock` so you can validate UI streaming immediately.

## Switch to real vLLM streaming

1. Set in `.env`:
   - `STREAM_MODE=vllm`
   - `MODEL_NAME=<your model>`
2. Start with GPU profile:
   - `docker compose -f docker/docker-compose.yml --env-file .env --profile gpu up --build`
3. Validate:
   - `http://localhost:8001/v1/models`
   - send a chat message in UI and confirm streamed tokens.

## Switch to local Ollama streaming

1. Ensure Ollama is running on your host machine.
2. Set in `.env`:
   - `STREAM_MODE=ollama`
   - `OLLAMA_BASE_URL=http://host.docker.internal:11434`
   - `OLLAMA_MODEL=<your-ollama-model-tag>`
3. Start without the GPU vLLM profile:
   - `docker compose -f docker/docker-compose.yml --env-file .env up --build`
4. Validate:
   - `http://localhost:8000/health` should show `stream_mode: ollama`
   - send a chat message in UI and confirm streamed tokens.

## What is already aligned to your target architecture

- Streaming text path is implemented end-to-end.
- API chunking hook for TTS handoff is implemented (`/tts/speak` calls from API).
- Avatar service integration point exists (`/avatar/lip-sync` stub).
- Docker topology includes: `frontend`, `api`, `vllm`, `tts`, `avatar`, optional `redis`.

## What to build next (in order)

1. Replace `services/tts` stub with real low-latency TTS (Piper/Kokoro/hosted streaming).
2. Replace `services/avatar` stub with MuseTalk worker that consumes TTS audio chunks.
3. Push a real media stream URL back to frontend avatar panel (HLS or WebRTC).
4. Add queue/session state (Redis) once concurrency increases.
5. Add voice input/VAD turn-taking (TEN) only after text+TTS+avatar loop is stable.
