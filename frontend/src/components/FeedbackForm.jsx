import React, { useEffect, useRef, useState } from "react";
import { sendFeedback } from "../api.js";
import "./feedback.css";

export default function FeedbackForm({ t, lang, onClose }) {
  const [rating, setRating] = useState(0);
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [wantsPilot, setWantsPilot] = useState(false);
  const [website, setWebsite] = useState(""); // hidden trap field: people never fill it in
  const [status, setStatus] = useState("idle"); // idle | sending | done | error | rate
  const messageRef = useRef(null);

  useEffect(() => {
    messageRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(e) {
    e.preventDefault();
    if (message.trim().length < 3 || status === "sending") return;
    setStatus("sending");
    try {
      await sendFeedback({
        message: message.trim(),
        rating: rating || null,
        contact: contact.trim() || null,
        wants_pilot: wantsPilot,
        language: lang,
        website,
      });
      setStatus("done");
    } catch (err) {
      setStatus(err.message === "rate" ? "rate" : "error");
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="feedback-title">
        <button className="modal-close" onClick={onClose} aria-label={t.feedbackClose}>
          ×
        </button>

        {status === "done" ? (
          <div className="feedback-done">
            <div className="feedback-title" id="feedback-title">
              {t.feedbackThanksTitle}
            </div>
            <p>{t.feedbackThanks}</p>
            <button className="feedback-submit" onClick={onClose}>
              {t.feedbackClose}
            </button>
          </div>
        ) : (
          <form onSubmit={submit}>
            <div className="feedback-title" id="feedback-title">
              {t.feedbackTitle}
            </div>
            <p className="feedback-intro">{t.feedbackIntro}</p>

            <div className="field">
              <span className="field-label">{t.feedbackRating}</span>
              <div className="stars" role="radiogroup" aria-label={t.feedbackRating}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    type="button"
                    key={n}
                    role="radio"
                    aria-checked={rating === n}
                    aria-label={`${n}`}
                    className={n <= rating ? "star on" : "star"}
                    onClick={() => setRating(n === rating ? 0 : n)}
                  >
                    ★
                  </button>
                ))}
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="fb-message">
                {t.feedbackMessage} <span className="req">*</span>
              </label>
              <textarea
                id="fb-message"
                ref={messageRef}
                rows={5}
                maxLength={2000}
                required
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={t.feedbackPlaceholder}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="fb-contact">
                {t.feedbackContact}
              </label>
              <input
                id="fb-contact"
                type="text"
                maxLength={200}
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                autoComplete="off"
              />
            </div>

            <label className="check-row">
              <input type="checkbox" checked={wantsPilot} onChange={(e) => setWantsPilot(e.target.checked)} />
              <span>{t.feedbackPilot}</span>
            </label>

            {/* honeypot */}
            <input
              type="text"
              name="website"
              tabIndex={-1}
              autoComplete="off"
              className="hp"
              aria-hidden="true"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />

            <p className="feedback-warn">{t.feedbackWarn}</p>

            {status === "error" && <p className="feedback-error">{t.feedbackError}</p>}
            {status === "rate" && <p className="feedback-error">{t.feedbackRate}</p>}

            <button className="feedback-submit" type="submit" disabled={status === "sending" || message.trim().length < 3}>
              {status === "sending" ? t.feedbackSending : t.feedbackSend}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
