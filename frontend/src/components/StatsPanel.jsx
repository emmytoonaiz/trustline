import React, { useEffect, useState } from "react";
import { getStats } from "../api.js";

export default function StatsPanel({ t, lang, refreshKey }) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    getStats(lang)
      .then(setStats)
      .catch(() => setStats(null));
  }, [refreshKey, lang]);

  if (!stats || stats.top_categories.length === 0) return null;

  const max = Math.max(...stats.top_categories.map((c) => c.count), 1);

  return (
    <aside className="stats-panel">
      <div className="stats-title">{t.statsTitle}</div>
      <div className="stats-subtitle">{t.statsSubtitle}</div>
      <ul className="stats-list">
        {stats.top_categories.map((c) => (
          <li key={c.category}>
            <div className="stats-row">
              <span className="stats-category">{c.category}</span>
              <span className="stats-count">{c.count}</span>
            </div>
            <div className="stats-bar-track">
              <div
                className="stats-bar-fill"
                style={{ width: `${(c.count / max) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
