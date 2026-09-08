import { useState } from "react";
import { api } from "../../lib/creditApi";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function ChatTab() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    setMessages((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.queryGraph(q);
      setMessages((m) => [...m, { role: "assistant", text: res.explanation }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: `Error: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="card chat">
        <h2>Financial Graph Chat</h2>
        <div className="chat-log">
          {messages.length === 0 && (
            <p className="muted">Ask anything about the financial risk knowledge graph.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <strong>{m.role === "user" ? "You" : "CreditGraph"}:</strong> {m.text}
            </div>
          ))}
        </div>
        <div className="chat-input">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
            placeholder="Ask about risk models, VaR, collateral…"
          />
          <button className="primary" onClick={send} disabled={busy || !input.trim()}>
            Send
          </button>
        </div>
      </section>
    </div>
  );
}