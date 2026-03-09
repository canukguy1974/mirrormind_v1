"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const personas = [
  {
    id: "flirty",
    label: "Flirty AF",
    opening: "Hey gorgeous. Ready for fast, spicy feedback?"
  },
  {
    id: "brutal",
    label: "Brutally Honest",
    opening: "I will be direct and useful. No sugar coating."
  },
  {
    id: "therapist",
    label: "Therapist",
    opening: "Take one breath. We can untangle this calmly."
  }
];

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function randomSessionId() {
  return `sess_${Math.random().toString(36).slice(2, 10)}`;
}

export default function ChatClient() {
  const [persona, setPersona] = useState(personas[2].id);
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [liveReply, setLiveReply] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [avatarFrameCount, setAvatarFrameCount] = useState(0);
  const [hasAvatarStream, setHasAvatarStream] = useState(false);
  const eventSourceRef = useRef(null);
  const wsRef = useRef(null);
  const avatarCanvasRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const audioUnlockedRef = useRef(false);

  useEffect(() => {
    setSessionId(randomSessionId());
  }, []);

  function drawToAvatarCanvas(imageSrc) {
    const canvas = avatarCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      // Draw fit-center crop into square canvas.
      const sw = img.width;
      const sh = img.height;
      const size = Math.min(sw, sh);
      const sx = Math.floor((sw - size) / 2);
      const sy = Math.floor((sh - size) / 2);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, sx, sy, size, size, 0, 0, canvas.width, canvas.height);
    };
    img.src = imageSrc;
  }

  useEffect(() => {
    // Load portrait onto canvas as initial frame.
    drawToAvatarCanvas(`${API_URL}/avatar/portrait`);
  }, []);

  // Set up WebSocket connection for Avatar
  useEffect(() => {
    if (!sessionId) return;

    // We connect to the API proxy port 8000
    const wsUrl = `${API_URL.replace('http', 'ws')}/avatar/stream/${sessionId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      // Expecting Base64 JPEG
      if (typeof event.data === 'string' && event.data.length > 50) {
        drawToAvatarCanvas(`data:image/jpeg;base64,${event.data}`);
        setAvatarFrameCount((prev) => prev + 1);
        setHasAvatarStream(true);
      }
    };

    ws.onopen = () => console.log('Avatar WebSocket connected');
    ws.onclose = () => console.log('Avatar WebSocket closed');
    ws.onerror = (e) => console.error('Avatar WebSocket error:', e);

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [sessionId]);

  const personaOpening = useMemo(() => {
    const match = personas.find((p) => p.id === persona);
    return match ? match.opening : "";
  }, [persona]);

  // -----------------------------------------------------------------------
  // Audio unlock for Chrome autoplay policy
  // -----------------------------------------------------------------------
  function unlockAudio() {
    if (audioUnlockedRef.current) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const buffer = ctx.createBuffer(1, 1, 22050);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      source.start(0);
      audioUnlockedRef.current = true;
      console.log('Audio context unlocked');
    } catch (e) {
      console.warn('Audio unlock failed:', e);
    }
  }

  // -----------------------------------------------------------------------
  // Audio queue — plays TTS chunks sequentially
  // -----------------------------------------------------------------------
  function enqueueAudio(url) {
    audioQueueRef.current.push(url);
    if (!isPlayingRef.current) {
      playNext();
    }
  }

  function playNext() {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setIsPlaying(false);
      return;
    }

    isPlayingRef.current = true;
    setIsPlaying(true);
    const url = audioQueueRef.current.shift();

    const audio = new Audio(url);
    audio.onended = () => playNext();
    audio.onerror = (e) => { console.error('Audio error:', e, url); playNext(); };
    audio.play()
      .then(() => console.log('Playing audio:', url))
      .catch((e) => { console.warn('Audio play blocked:', e); playNext(); });
  }

  // -----------------------------------------------------------------------
  // SSE streaming
  // -----------------------------------------------------------------------
  function closeStream() {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }

  function beginStream(userText) {
    closeStream();
    setLiveReply("");
    setError("");
    setStatus("streaming");
    audioQueueRef.current = [];
    let assembledText = "";

    const query = new URLSearchParams({
      message: userText,
      persona,
      session_id: sessionId
    });

    const stream = new EventSource(`${API_URL}/chat/stream?${query.toString()}`);
    eventSourceRef.current = stream;

    stream.addEventListener("meta", (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.session_id) {
          setSessionId(payload.session_id);
        }
      } catch (_) {
        // Ignore malformed event payload.
      }
    });

    stream.addEventListener("token", (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.token) {
          setLiveReply((prev) => {
            const next = prev + payload.token;
            assembledText = next;
            return next;
          });
        }
      } catch (_) {
        // Ignore malformed event payload.
      }
    });

    stream.addEventListener("audio", (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.audio_url) {
          // audio_url is API-relative, e.g. /tts/audio/chunk.wav
          enqueueAudio(`${API_URL}${payload.audio_url}`);
        }
      } catch (_) {
        // Ignore malformed event payload.
      }
    });

    stream.addEventListener("done", (event) => {
      let text = assembledText;
      try {
        const payload = JSON.parse(event.data);
        if (payload.text) {
          text = payload.text;
        }
      } catch (_) {
        // Keep streamed text if done payload is not parseable.
      }

      if (text.trim()) {
        setMessages((prev) => [...prev, { role: "assistant", text }]);
      }

      setLiveReply("");
      setStatus("idle");
      closeStream();
    });

    stream.addEventListener("error", (event) => {
      let err = "Stream disconnected.";
      try {
        if (event.data) {
          const payload = JSON.parse(event.data);
          if (payload.message) {
            err = payload.message;
          }
        }
      } catch (_) {
        // Ignore malformed event payload.
      }
      setError(err);
      setStatus("error");
      closeStream();
    });
  }

  function submit(event) {
    event.preventDefault();
    const text = input.trim();
    if (!text || status === "streaming") {
      return;
    }

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    unlockAudio();
    beginStream(text);
  }

  useEffect(() => closeStream, []);

  return (
    <section className="shell">
      <div className="chat-area">
        <h1 className="title">MirrorMind v1</h1>
        <p className="subtitle">
          Text streaming is live. TTS audio plays automatically when available.
        </p>

        <div className="status-row">
          <span>Session: {sessionId}</span>
          <span className={status === "streaming" ? "stream-ok" : "stream-warn"}>
            Stream: {status}
          </span>
          {isPlaying && (
            <span className="audio-indicator" title="Audio playing">
              🔊
            </span>
          )}
        </div>

        <div className="history">
          {!messages.length && !liveReply ? (
            <div className="bubble bubble-assistant">{personaOpening}</div>
          ) : null}

          {messages.map((msg, idx) => (
            <div
              key={`${msg.role}-${idx}`}
              className={`bubble ${msg.role === "user" ? "bubble-user" : "bubble-assistant"}`}
            >
              {msg.text}
            </div>
          ))}

          {liveReply ? (
            <div className="bubble bubble-assistant live">{liveReply}</div>
          ) : null}
        </div>

        <form className="composer" onSubmit={submit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
          />
          <button type="submit" disabled={status === "streaming"}>
            Send
          </button>
        </form>

        {error ? <p className="stream-error">{error}</p> : null}
      </div>

      <aside className="panel">
        <h2>Persona</h2>
        <p>This is reused from your older prototype and now drives prompting.</p>
        <div className="persona-list">
          {personas.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setPersona(item.id)}
              className={`persona ${persona === item.id ? "active" : ""}`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="avatar">
          <strong>Avatar panel {hasAvatarStream ? `(frames: ${avatarFrameCount})` : ""}</strong>
          <div className="avatar-frame mt-4" style={{
            width: '100%',
            aspectRatio: '1',
            borderRadius: '12px',
            overflow: 'hidden',
            backgroundColor: '#1e293b',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: isPlaying ? '2px solid #3b82f6' : '1px solid #334155',
            boxShadow: isPlaying ? '0 0 15px rgba(59, 130, 246, 0.4)' : 'none',
            transition: 'all 0.3s ease'
          }}>
            <canvas
              ref={avatarCanvasRef}
              width={512}
              height={512}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
            {!hasAvatarStream && (
              <div style={{
                color: '#94a3b8',
                textAlign: 'center',
                fontSize: '0.9rem',
                position: 'absolute',
                bottom: '12px',
                left: '12px',
                background: 'rgba(15, 23, 42, 0.75)',
                borderRadius: '6px',
                padding: '4px 8px'
              }}>
                <div style={{ fontSize: '2rem', marginBottom: '8px' }}>👤</div>
                {isPlaying ? "Generating frames..." : "Waiting for audio..."}
              </div>
            )}
          </div>
        </div>
      </aside>
    </section>
  );
}
