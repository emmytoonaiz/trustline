const BASE = "/api";

export async function verifyMessage(message, language = "en") {
  const res = await fetch(`${BASE}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, language }),
  });
  if (!res.ok) throw new Error("verify request failed");
  return res.json();
}

export async function reportScam(message, category) {
  const res = await fetch(`${BASE}/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, category }),
  });
  if (!res.ok) throw new Error("report request failed");
  return res.json();
}

export async function getStats(language = "en") {
  const res = await fetch(`${BASE}/stats?language=${encodeURIComponent(language)}`);
  if (!res.ok) throw new Error("stats request failed");
  return res.json();
}

export async function getConfig() {
  const res = await fetch(`${BASE}/config`);
  if (!res.ok) throw new Error("config request failed");
  return res.json();
}

// Counts one visit under the link label (?ref=tiktok). Nothing identifies the visitor.
export function recordVisit(ref) {
  return fetch(`${BASE}/visit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref }),
  }).catch(() => {});
}

export async function sendFeedback(payload) {
  const res = await fetch(`${BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, ref: new URLSearchParams(window.location.search).get("ref") }),
  });
  if (res.status === 429) throw new Error("rate");
  if (!res.ok) throw new Error("feedback request failed");
  return res.json();
}
