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
  const [sessionId, setSessionId] = useState(randomSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [liveReply, setLiveReply] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const eventSourceRef = useRef(null);

  const personaOpening = useMemo(() => {
    const match = personas.find((p) => p.id === persona);
    return match ? match.opening : "";
  }, [persona]);

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
    beginStream(text);
  }

  useEffect(() => closeStream, []);

  return (
    <section className="shell">
      <div className="chat-area">
        <h1 className="title">MirrorMind v1</h1>
        <p className="subtitle">
          Text streaming is live now. TTS and MuseTalk are wired on the backend
          interface.
        </p>

        <div className="status-row">
          <span>Session: {sessionId}</span>
          <span className={status === "streaming" ? "stream-ok" : "stream-warn"}>
            Stream: {status}
          </span>
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
          <strong>Avatar panel</strong>
          <p>
            API emits chunk events for TTS handoff. MuseTalk integration can
            push an HLS/WebRTC stream URL here in phase 3.
          </p>
        </div>
      </aside>
    </section>
  );
}
