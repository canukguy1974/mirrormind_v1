# MuseTalk — MirrorMind v1

## Project goal
Build the first practical version of MirrorMind that feels fast and alive enough for real conversation. Prioritize low latency and believable interaction over perfect cinematic visuals.

## What we decided in this conversation
- FaceTime-like feel matters more than full rendered video quality.
- InfiniteTalk is interesting, but it is the wrong first choice for interactive conversation because it is a clip-generation path, not a low-latency live response path.
- MirrorMind v1 should start with:
  - fast LLM streaming
  - streamed text in the UI
  - streamed TTS
  - real-time lip sync with MuseTalk
  - optional expression/head-motion layer later with LivePortrait
- TEN Framework is useful as the real-time conversation backbone if we want turn detection, VAD, and full-duplex voice behavior, but it is not required for the first text-plus-avatar MVP.
- RunPod Pods are the right place to start, not Serverless, because we need persistent control, custom containers, and room to debug.

## Recommended v1 architecture

### Core principle
Do not wait for one stage to finish before the next starts. Stream and parallelize.

### Response flow
1. User sends text or speech.
2. Backend forwards prompt to a fast LLM endpoint.
3. First tokens stream back immediately.
4. UI displays text as it arrives.
5. TTS starts once the first useful chunk is available.
6. MuseTalk consumes audio chunks and animates the avatar.
7. Browser receives video/audio stream and updates continuously.

## Recommended RunPod setup

### GPU
Start with a single RTX 4090 Pod.

Why:
- good balance of cost and performance
- enough for LLM + TTS + avatar testing if you are careful
- simpler and cheaper than jumping straight to an A100

### Storage
- Persistent volume mounted to `/workspace`
- Keep model weights, repos, and cached assets there

### Networking
Expose these ports:
- 3000 -> frontend
- 8000 -> API gateway / FastAPI
- 8001 -> vLLM OpenAI-compatible endpoint
- 7860 -> avatar service preview or debug UI if needed

## Containers and services

### 1) Frontend container
Purpose:
- React/Next.js UI for chat, streamed text, and avatar panel

Responsibilities:
- websocket or SSE connection to backend
- show text tokens as they stream
- play streamed audio
- display avatar stream or repeated image/video frames

Suggested stack:
- Next.js
- React
- simple websocket client

### 2) API orchestration container
Purpose:
- one backend entrypoint for the app

Responsibilities:
- accept user messages
- call vLLM
- stream tokens to frontend
- chunk response for TTS
- forward audio to MuseTalk pipeline
- maintain session state

Suggested stack:
- FastAPI
- websockets or Server-Sent Events
- Redis optional for sessions/queueing

### 3) vLLM container
Purpose:
- fast local LLM inference with an OpenAI-compatible API

Recommended initial model:
- Qwen2.5-7B-Instruct or Llama-3.1-8B-Instruct

Why:
- fast enough for live conversation feel
- much better latency than 70B-class models

Responsibilities:
- serve `/v1/chat/completions`
- stream tokens quickly

### 4) TTS container
Purpose:
- convert response chunks into speech quickly

Recommended starting options:
- Piper for cheap local testing
- Kokoro or another low-latency local TTS if voice quality is acceptable

If quality matters more than cost later:
- switch to a hosted streaming TTS provider

### 5) MuseTalk avatar container
Purpose:
- lip-sync the avatar from the generated audio

Responsibilities:
- take source face image/video frames
- take incoming audio chunks or short buffered segments
- output updated talking-face frames

Notes:
- start with a fixed avatar portrait
- get mouth motion working first
- do not chase perfect head motion on day one

### 6) Optional LivePortrait container
Purpose:
- richer facial expression and head motion after v1 loop works

Do not make this blocking for the first MVP.

### 7) Optional TEN container
Purpose:
- real-time voice orchestration, VAD, turn detection, interruption handling

Use this in v1.5 or v2 if you want real voice turn-taking.

## Repos to get

### Core repos
- vLLM
- MuseTalk
- LivePortrait
- TEN Framework

### Nice-to-have support repos or components
- a local TTS engine repo if needed
- Redis image for lightweight state/queueing
- a simple websocket-ready frontend starter

## Recommended repo roles

### vLLM
Role:
- low-latency text generation server

### MuseTalk
Role:
- real-time lip-sync engine for the avatar

### LivePortrait
Role:
- optional motion/expression enhancement layer

### TEN Framework
Role:
- optional real-time multimodal orchestration for voice mode

## What to clone first
1. vLLM
2. MuseTalk
3. LivePortrait
4. your MirrorMind app repo
5. TEN only after text-plus-avatar loop works

## Actual MVP build order

### Phase 1 — fast text loop
- Launch RunPod 4090 Pod
- Run vLLM with a 7B or 8B instruct model
- Build FastAPI route that streams tokens to frontend
- Confirm first token is fast enough

### Phase 2 — audio loop
- Add TTS that starts speaking before the whole answer is done
- Keep chunk sizes small enough to feel live

### Phase 3 — avatar loop
- Feed TTS audio into MuseTalk
- Render a single talking portrait
- Keep visual pipeline simple

### Phase 4 — polish
- idle animation
- quick reaction phrases
- better voice
- LivePortrait layer

## What not to do right now
- do not start with InfiniteTalk as the primary interaction engine
- do not use giant reasoning models for primary chat replies
- do not add multiple heavy visual models before latency is acceptable
- do not build voice interruption logic before text+TTS+avatar works reliably

## Practical latency targets
- first text token: under 500 ms if possible
- speech start: under 1.2 seconds
- visible mouth movement: as soon as the first audio chunk is available

## Initial file/folder suggestion

```text
mirrormind-v1/
  frontend/
  api/
  docker/
    docker-compose.yml
  services/
    tts/
    avatar/
  models/
  assets/
    avatars/
```

## Starter docker plan

Services:
- frontend
- api
- vllm
- tts
- musetalk
- redis (optional)

## Environment variables to expect
- OPENAI_BASE_URL or local VLLM_BASE_URL
- MODEL_NAME
- TTS_ENGINE
- AVATAR_IMAGE_PATH
- REDIS_URL
- PUBLIC_API_URL
- WEBSOCKET_URL

## Immediate next step
Build the Pod-first version on RunPod with only:
- frontend
- FastAPI backend
- vLLM
- TTS
- MuseTalk

That is the smallest serious version of MirrorMind that can actually feel alive.

