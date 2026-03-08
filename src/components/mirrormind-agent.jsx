import { useEffect } from "react";

export default function MirrorMindAgent() {
  useEffect(() => {
    const clientKey = process.env.REACT_APP_DID_CLIENT_KEY;
    const agentId = process.env.REACT_APP_DID_AGENT_ID;

    if (!clientKey || !agentId) {
      return;
    }

    if (typeof window !== "undefined") {
      const script = document.createElement("script");
      script.type = "module";
      script.src = "https://agent.d-id.com/v1/index.js";
      script.setAttribute("data-name", "did-agent");
      script.setAttribute("data-mode", "fabio");
      script.setAttribute("data-client-key", clientKey);
      script.setAttribute("data-agent-id", agentId);
      script.setAttribute("data-monitor", "true");

      document.body.appendChild(script);
    }
  }, []);

  return null;
}
