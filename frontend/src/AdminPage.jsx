import React, { useCallback, useEffect, useMemo, useState } from "react";
import "./admin.css";

// The key lives only in this tab (sessionStorage), so closing the tab signs you out.
const KEY_STORE = "trustline-admin-key";

function readKey() {
  try {
    return sessionStorage.getItem(KEY_STORE) || "";
  } catch {
    return "";
  }
}

function saveKey(value) {
  try {
    if (value) sessionStorage.setItem(KEY_STORE, value);
    else sessionStorage.removeItem(KEY_STORE);
  } catch {
    /* storage blocked: you'll just be asked again */
  }
}

async function call(path, key) {
  const res = await fetch(`/api${path}`, { headers: { "X-Admin-Key": key }, cache: "no-store" });
  if (res.status === 403) throw new Error("wrong");
  if (res.status === 404) throw new Error("off");
  if (res.status === 429) throw new Error("locked");
  if (!res.ok) throw new Error("failed");
  return res.json();
}

const MESSAGES = {
  wrong: "That key isn't right.",
  off: "The admin area is switched off: ADMIN_KEY isn't set on the server.",
  locked: "Too many wrong keys. Try again in about ten minutes.",
  failed: "Something went wrong loading the data. Try again.",
};

function Stars({ value }) {
  if (!value) return <span className="muted">no rating</span>;
  return (
    <span className="stars-row" aria-label={`${value} out of 5`}>
      {"★".repeat(value)}
      <span className="muted">{"★".repeat(5 - value)}</span>
    </span>
  );
}

function Contact({ value }) {
  if (!value) return null;
  const isEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  return (
    <div className="fb-contact">
      Contact: {isEmail ? <a href={`mailto:${value}`}>{value}</a> : <span>{value}</span>}
    </div>
  );
}

export default function AdminPage() {
  const [key, setKey] = useState(readKey);
  const [draft, setDraft] = useState("");
  const [days, setDays] = useState(30);
  const [visits, setVisits] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [onlyPilot, setOnlyPilot] = useState(false);

  useEffect(() => {
    document.title = "TrustLine admin";
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow";
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);

  const load = useCallback(async () => {
    if (!key) return;
    setLoading(true);
    setError("");
    try {
      const [v, f] = await Promise.all([call(`/visits?days=${days}`, key), call("/feedback?limit=200", key)]);
      setVisits(v);
      setFeedback(f);
    } catch (e) {
      setError(MESSAGES[e.message] || MESSAGES.failed);
      if (e.message === "wrong" || e.message === "off") {
        saveKey("");
        setKey("");
      }
      setVisits(null);
      setFeedback(null);
    } finally {
      setLoading(false);
    }
  }, [key, days]);

  useEffect(() => {
    load();
  }, [load]);

  function signIn(e) {
    e.preventDefault();
    const value = draft.trim();
    if (!value) return;
    saveKey(value);
    setKey(value);
    setDraft("");
  }

  function signOut() {
    saveKey("");
    setKey("");
    setVisits(null);
    setFeedback(null);
    setError("");
  }

  const summary = useMemo(() => {
    const rated = (feedback || []).filter((f) => f.rating);
    const average = rated.length ? rated.reduce((sum, f) => sum + f.rating, 0) / rated.length : null;
    const top = visits ? Object.entries(visits.by_ref)[0] : null;
    return {
      average,
      top,
      pilots: (feedback || []).filter((f) => f.wants_pilot).length,
    };
  }, [feedback, visits]);

  if (!key) {
    return (
      <main className="admin">
        <form className="admin-card login" onSubmit={signIn}>
          <h1>TrustLine admin</h1>
          <p className="muted">Enter your admin key to see visits and feedback.</p>
          <input
            type="password"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Admin key"
            autoComplete="off"
            autoFocus
            aria-label="Admin key"
          />
          {error && <p className="admin-error">{error}</p>}
          <button type="submit" disabled={!draft.trim()}>
            Open dashboard
          </button>
        </form>
      </main>
    );
  }

  const maxVisits = visits ? Math.max(1, ...Object.values(visits.by_ref)) : 1;
  const shownFeedback = (feedback || []).filter((f) => !onlyPilot || f.wants_pilot);

  return (
    <main className="admin">
      <header className="admin-top">
        <h1>TrustLine admin</h1>
        <div className="admin-actions">
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Period">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button onClick={load} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
          <button className="secondary" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      {error && <p className="admin-error">{error}</p>}

      <section className="tiles">
        <div className="tile">
          <div className="tile-number">{visits ? visits.total : "–"}</div>
          <div className="tile-label">Visits, last {days} days</div>
        </div>
        <div className="tile">
          <div className="tile-number">{summary.top ? summary.top[0] : "–"}</div>
          <div className="tile-label">Top source{summary.top ? ` (${summary.top[1]})` : ""}</div>
        </div>
        <div className="tile">
          <div className="tile-number">{feedback ? feedback.length : "–"}</div>
          <div className="tile-label">Feedback notes</div>
        </div>
        <div className="tile">
          <div className="tile-number">{summary.average ? summary.average.toFixed(1) : "–"}</div>
          <div className="tile-label">Average rating (of 5)</div>
        </div>
        <div className="tile">
          <div className="tile-number">{feedback ? summary.pilots : "–"}</div>
          <div className="tile-label">Want the business pilot</div>
        </div>
      </section>

      <section className="admin-card">
        <h2>Visits by link</h2>
        <p className="muted small">
          One count per browser session. The label is whatever follows <code>?ref=</code> in the link.
        </p>
        {visits && Object.keys(visits.by_ref).length === 0 && <p className="muted">No visits in this period yet.</p>}
        <ul className="bars">
          {visits &&
            Object.entries(visits.by_ref).map(([label, n]) => (
              <li key={label}>
                <span className="bar-label">{label}</span>
                <span className="bar-track">
                  <span className="bar-fill" style={{ width: `${(n / maxVisits) * 100}%` }} />
                </span>
                <span className="bar-count">{n}</span>
              </li>
            ))}
        </ul>
      </section>

      <section className="admin-card">
        <div className="fb-head">
          <h2>Feedback</h2>
          <label className="check">
            <input type="checkbox" checked={onlyPilot} onChange={(e) => setOnlyPilot(e.target.checked)} />
            Only business-pilot requests
          </label>
        </div>
        {feedback && shownFeedback.length === 0 && <p className="muted">Nothing here yet.</p>}
        <ul className="fb-list">
          {shownFeedback.map((f) => (
            <li key={f.id} className="fb-item">
              <div className="fb-meta">
                <Stars value={f.rating} />
                <span className="chip">{f.ref}</span>
                <span className="chip">{f.language}</span>
                {f.wants_pilot && <span className="chip pilot">wants pilot</span>}
                <span className="muted small fb-time">{new Date(f.created_at).toLocaleString()}</span>
              </div>
              <p className="fb-message">{f.message}</p>
              <Contact value={f.contact} />
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
