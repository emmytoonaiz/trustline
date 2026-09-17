const BASE = "/api";

export async function verifyMessage(message) {
  const res = await fetch(`${BASE}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
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

export async function getStats() {
  const res = await fetch(`${BASE}/stats`);
  if (!res.ok) throw new Error("stats request failed");
  return res.json();
}
