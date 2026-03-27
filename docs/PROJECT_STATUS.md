# MirrorMind v1 Project Status

Last updated: 2026-03-12

## 1) Current Snapshot
- Core chat pipeline is working: `frontend -> api -> tts -> browser playback`.
- Audio is stable after warmup.
- Avatar service is integrated and streaming frames over websocket.
- Local GPU (4 GB VRAM) cannot run stable full MuseTalk face synthesis in realtime, so local runtime frequently falls back to lightweight mouth overlay animation.
- RunPod path is partially implemented via config toggle and is the intended path for true image animation.

## 2) What Works Right Now
- SSE text stream from `/chat/stream`.
- TTS chunking + progressive audio events to UI.
- Audio proxying via API `/tts/audio/{filename}`.
- Avatar websocket proxy path from API to avatar backend.
- Weights persistence fix: avatar now checks required files and skips re-downloading when present.
- Local fallback animation now appears near lips (not just a static red dot), with better mouth positioning than before.

## 3) Current Pain Points / Known Issues
- Full-image MuseTalk animation is not reliable on local 4 GB GPU.
- Frequent local log pattern:
  - `MuseTalk inference failed for chunk; falling back to lightweight animation: RuntimeError('MuseTalk patch variance too low')`
- Occasional avatar sync timeout from API:
  - `Failed to trigger avatar sync attempt=1: ReadTimeout('')`
- Occasional websocket close noise in API logs during disconnect/reconnect cycles.
- Latency profile reported by user:
  - cold start ~35s
  - then ~14s
  - then ~8s
  - warm/stable ~3s

## 4) Main Code Changes Already In Place
- `api/app/main.py`
  - Avatar backend selection by mode (`local`, `runpod`, `auto`) plus legacy override.
  - Async TTS pipeline emits audio event immediately and triggers avatar sync in background.
  - Retry logic for TTS + avatar calls.
  - API health exposes avatar mode/base URL.
- `docker/docker-compose.yml`
  - Added avatar mode/runpod envs for API.
  - Added HF cache envs for avatar.
  - API no longer hard-depends on local avatar container (supports runpod mode).
- `services/avatar/app/main.py`
  - Audio URL dedupe per session to reduce duplicate queue buildup.
  - Better logging and cleanup around disconnects.
- `services/avatar/app/musetalk_wrapper.py`
  - Added fallback mode + realtime budget guard + NaN/Inf safety.
  - Added low VRAM force-fallback behavior (<= 6 GB).
  - Added feathered blend mask to reduce square patch artifact.
- `services/avatar/scripts/download_weights.py`
  - Switched to exact required-file checks/download behavior to stop repeat downloads.
- `services/avatar/Dockerfile`
  - Pinned `huggingface_hub==0.20.2` for compatibility.

## 5) Configuration Modes

### Local Development (no RunPod spend)
Use local avatar service and accept fallback animation quality on low VRAM.

Required env:
```env
AVATAR_MODE=local
AVATAR_LOCAL_BASE_URL=http://avatar:8020
```

### RunPod GPU (target for real image animation)
Run local `frontend + api + tts`, route avatar calls to remote RunPod.

Required env:
```env
AVATAR_MODE=runpod
AVATAR_RUNPOD_BASE_URL=https://<runpod-endpoint>
```

Optional hard override:
```env
AVATAR_BASE_URL=https://<force-endpoint>
```

## 6) Fast Resume Checklist (When You Return Later)
1. `git status --short` to see current uncommitted work.
2. Confirm `.env` has the intended avatar mode (`local` vs `runpod`).
3. Bring stack up:
   - Local avatar: `docker compose -f docker/docker-compose.yml up -d frontend api tts avatar`
   - RunPod avatar: `docker compose -f docker/docker-compose.yml up -d frontend api tts`
4. Check API health:
   - `curl -s http://localhost:8000/health | jq`
   - Verify `avatar_mode` and `avatar_base_url`.
5. Send one short message in UI and watch:
   - first token time
   - first audio playback time
   - avatar panel behavior
6. Tail logs if needed:
   - `docker compose -f docker/docker-compose.yml logs -f api avatar tts`

## 7) Active Next Priorities
1. Move avatar inference to RunPod GPU and verify full-image lip animation (not fallback overlay).
2. Add explicit health/warmup endpoint for avatar and trigger on startup.
3. Reduce API/avatar sync timeout noise and tighten retry/backoff.
4. Optional: add UI indicator showing `fallback` vs `full MuseTalk` mode so behavior is explicit.

## 8) Files You Should Read First Next Session
- `docs/RUNPOD_GPU_IMPLEMENTATION_PLAN.md`
- `docker/docker-compose.yml`
- `api/app/main.py`
- `services/avatar/app/main.py`
- `services/avatar/app/musetalk_wrapper.py`

## 9) Working Tree Status (At Last Check)
Modified:
- `api/app/main.py`
- `docker/docker-compose.yml`
- `services/avatar/Dockerfile`
- `services/avatar/app/main.py`
- `services/avatar/app/musetalk_wrapper.py`
- `services/avatar/requirements.txt`
- `services/avatar/scripts/download_weights.py`

Untracked:
- `docs/` (includes this status file and RunPod plan)

## 10) Bottom Line
- You are past “prototype broken” stage.
- Text + audio conversational loop is viable.
- Local 4 GB setup is now useful for cheap dev/testing.
- True image animation quality now depends on moving avatar inference to higher-VRAM GPU (RunPod), which is already partially wired via env toggle.
