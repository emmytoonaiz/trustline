import React, { useState } from "react";
import { verifyMessage } from "./api.js";
import { COPY } from "./copy.js";
import VerdictCard from "./components/VerdictCard.jsx";
import StatsPanel from "./components/StatsPanel.jsx";

export default function App() {
  const [lang, setLang] = useState("en");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statsKey, setStatsKey] = useState(0);

  const t = COPY[lang];

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { id: Date.now(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const result = await verifyMessage(text);
      setMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, role: "bot", result, originalMessage: text },
      ]);
      setStatsKey((k) => k + 1);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: "error",
          text: "Something went wrong reaching TrustLine. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <div className="app-title">{t.title}</div>
          <div className="app-subtitle">{t.subtitle}</div>
        </div>
        <button
          className="lang-toggle"
          onClick={() => setLang((l) => (l === "en" ? "pcm" : "en"))}
        >
          {lang === "en" ? "Pidgin" : "EN"}
        </button>
      </header>

      <main className="app-main">
        <section className="chat-panel">
          {messages.length === 0 && <p className="intro">{t.intro}</p>}

          <div className="chat-log">
            {messages.map((m) => {
              if (m.role === "user") {
                return (
                  <div key={m.id} className="bubble user-bubble">
                    {m.text}
                  </div>
                );
              }
              if (m.role === "error") {
                return (
                  <div key={m.id} className="bubble error-bubble">
                    {m.text}
                  </div>
                );
              }
              return (
                <VerdictCard
                  key={m.id}
                  result={m.result}
                  originalMessage={m.originalMessage}
                  t={t}
                />
              );
            })}
            {loading && <div className="bubble bot-typing">…</div>}
          </div>

          <div className="chat-input-row">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t.placeholder}
              rows={2}
            />
            <button onClick={handleSend} disabled={loading || !input.trim()}>
              {t.send}
            </button>
          </div>
        </section>

        <StatsPanel t={t} refreshKey={statsKey} />
      </main>
    </div>
  );
}
