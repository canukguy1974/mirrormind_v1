# RunPod GPU Avatar Implementation Plan

## Goal
Run full MuseTalk image animation on a RunPod GPU while keeping local development cheap and fast.

## Architecture
- Local services: `frontend`, `api`, `tts`
- Remote service (RunPod): `avatar`
- API routes all avatar calls to selected endpoint via toggle.

Data flow:
1. User sends chat to local `api`.
2. `api` streams text + triggers local `tts`.
3. `api` receives audio URLs and calls `/avatar/lip-sync` on selected avatar backend.
4. Frontend opens `/avatar/stream/{session_id}` to local `api`, which proxies to local or RunPod avatar websocket.

## Config Toggle (Implemented)
API now supports these env vars:
- `AVATAR_MODE=local|runpod|auto`
- `AVATAR_LOCAL_BASE_URL` (default `http://avatar:8020`)
- `AVATAR_RUNPOD_BASE_URL` (e.g. `https://<pod-id>-8020.proxy.runpod.net`)
- `AVATAR_BASE_URL` optional hard override (legacy, highest priority)

Resolution order:
1. `AVATAR_BASE_URL` override if set
2. Mode-specific URL (`runpod` or `local`)
3. `auto`: runpod if set, else local

## Local Development (No RunPod Credits)
Use local stack only:
```bash
docker compose -f docker/docker-compose.yml up -d frontend api tts avatar
```
Set:
```bash
AVATAR_MODE=local
```

## RunPod Development / Production
Run local stack without local avatar:
```bash
docker compose -f docker/docker-compose.yml up -d frontend api tts
```
Set:
```bash
AVATAR_MODE=runpod
AVATAR_RUNPOD_BASE_URL=https://<runpod-endpoint>
```

## RunPod Pod Setup
1. Choose GPU with sufficient VRAM (12GB minimum, 16GB+ recommended).
2. Deploy `services/avatar` image as container.
3. Expose container port `8020` publicly.
4. Mount persistent volume for model cache and weights:
   - `/app/models`
5. Ensure env vars on pod:
   - `API_BASE_URL` (optional for internal fetch behavior)
   - `TTS_BASE_URL` (not required if API always supplies absolute URLs)
   - `HF_HOME=/app/models/.hf`
   - `HUGGINGFACE_HUB_CACHE=/app/models/.hf/hub`

## First Boot / Warmup Procedure
After pod starts:
1. `GET /health` until service is `ok`.
2. Trigger one short `/avatar/lip-sync` request to warm models.
3. Open one websocket stream `/avatar/stream/<session>`.
4. Confirm logs show model loaded and frames sent.

## Reliability + Latency Controls
- Keep one warm pod running to avoid cold starts.
- Add an external health monitor that pings `/health` every 30-60s.
- If using serverless scale-to-zero, expect first-response delay due to model load.
- Keep retries enabled in local API websocket proxy (already implemented).

## Security / Networking
- Prefer RunPod HTTPS endpoint and `wss://` websocket proxying.
- Restrict public exposure where possible (IP allowlist / auth gateway).
- If required, put RunPod behind your own reverse proxy with token auth.

## Rollout Plan
1. Configure envs with `AVATAR_MODE=runpod` and endpoint URL.
2. Start local `frontend+api+tts`.
3. Validate:
   - `GET http://localhost:8000/health` returns runpod avatar base URL.
   - Chat returns audio quickly.
   - Avatar stream renders full image animation.
4. Observe latency for 20-30 turns.
5. Tune chunk size (`TTS_FLUSH_CHARS`) and avatar pod GPU size.

## Rollback Plan
If RunPod degrades or fails:
1. Set `AVATAR_MODE=local`
2. Start local avatar service
3. Restart local `api`

No code rollback required.

## Validation Checklist
- [ ] API health reports correct avatar mode/base URL
- [ ] Audio still plays in < 3-5s warm
- [ ] Avatar websocket remains connected across turns
- [ ] No repeated reconnect errors to avatar backend
- [ ] Visual mouth movement is image-based (RunPod MuseTalk), not local fallback overlay
