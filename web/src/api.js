// Thin client for the Catan FastAPI backend. In dev, calls go through the Vite
// proxy at /api -> http://127.0.0.1:8000.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} failed (${res.status}): ${text}`);
  }
  return res.json();
}

export const newGame = (seed = 0) => post("/games/new", { seed });
export const applyAction = (state, action) => post("/games/action", { state, action });
export const botStep = (state) => post("/games/bot-step", { state });
