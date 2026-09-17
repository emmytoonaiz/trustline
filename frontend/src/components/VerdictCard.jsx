import React, { useState } from "react";
import { reportScam } from "../api.js";

const VERDICT_STYLE = {
  likely_scam: { cls: "scam", icon: "⚠️" },
  uncertain: { cls: "uncertain", icon: "🤔" },
  likely_safe: { cls: "safe", icon: "✅" },
  link_unsupported: { cls: "info", icon: "🔗" },
};

const PLATFORM_LABELS = {
  youtube: "YouTube",
  x: "X (Twitter)",
  facebook: "Facebook",
  instagram: "Instagram",
};

export default function VerdictCard({ result, originalMessage, t }) {
  const [reported, setReported] = useState(false);
  const style = VERDICT_STYLE[result.verdict] ?? VERDICT_STYLE.uncertain;

  const verdictLabel =
    result.verdict === "likely_scam"
      ? t.verdictScam
      : result.verdict === "likely_safe"
      ? t.verdictSafe
      : result.verdict === "link_unsupported"
      ? "Link"
      : t.verdictUncertain;

  async function handleReport() {
    try {
      await reportScam(originalMessage, result.matched?.category);
      setReported(true);
    } catch (e) {
      // Best-effort in a prototype: still flip the UI so the demo isn't blocked by a flaky network.
      setReported(true);
    }
  }

  if (result.verdict === "link_unsupported") {
    return (
      <div className={`verdict-card ${style.cls}`}>
        <div className="verdict-header">
          <span className="verdict-icon">{style.icon}</span>
          <div>
            <div className="verdict-label">{verdictLabel}</div>
            <div className="verdict-headline">{result.headline}</div>
          </div>
        </div>
        <div className="verdict-section">
          <p>{result.link_notice}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`verdict-card ${style.cls}`}>
      <div className="verdict-header">
        <span className="verdict-icon">{style.icon}</span>
        <div>
          <div className="verdict-label">{verdictLabel}</div>
          <div className="verdict-headline">{result.headline}</div>
        </div>
        <div className="verdict-confidence">{result.confidence}%</div>
      </div>

      {result.source_platform && (
        <div className="verdict-source-platform">
          Checked from a {PLATFORM_LABELS[result.source_platform] ?? result.source_platform} link
        </div>
      )}

      {result.matched && (
        <>
          <div className="verdict-section">
            <div className="verdict-section-title">{t.whyTitle}</div>
            <ul>
              {result.matched.why.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
          <div className="verdict-section">
            <div className="verdict-section-title">{t.adviceTitle}</div>
            <p>{result.matched.advice}</p>
          </div>
          <div className="verdict-source">
            {t.sourceLabel}: {result.matched.source}
          </div>
        </>
      )}

      {!result.matched && result.generic_advice && (
        <div className="verdict-section">
          <p>{result.generic_advice}</p>
        </div>
      )}

      <div className="verdict-actions">
        <button disabled={reported} onClick={handleReport}>
          {reported ? t.reportedButton : t.reportButton}
        </button>
      </div>
    </div>
  );
}
