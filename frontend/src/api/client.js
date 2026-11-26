// Must match API_COMMON_PREFIX in backend/app/settings.py, the Vite proxy and the Firebase rewrite.
export const API_PREFIX = "/multiverse/api/v1";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function query(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "" && v !== "all") qs.set(k, v);
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export async function get(path, params, { signal } = {}) {
  const res = await fetch(`${API_PREFIX}${path}${query(params)}`, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* keep status text */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : "Request failed");
  }
  return res.json();
}

export const api = {
  stats: (o) => get("/stats", {}, o),
  realities: (params, o) => get("/realities", params, o),
  reality: (id, o) => get(`/realities/${encodeURIComponent(id)}`, {}, o),
  coverage: (params, o) => get("/coverage", params, o),
  credits: (o) => get("/credits", {}, o),
  entity: (id, o) => get(`/entities/${encodeURIComponent(id)}`, {}, o),
  neighbourhood: (node, o) => get("/graph/neighbourhood", { node, limit: 30 }, o),
  search: (q, o, params = {}) => get("/search", { q, ...params }, o),
  nodes: (ids, o) => get("/graph/nodes", { ids: ids.join("|") }, o),
  characters: (params, o) => get("/characters", params, o),
  askMeta: (o) => get("/ask/meta", {}, o),
  timeline: (o) => get("/timeline/earth-199999", {}, o),
};

/** POST /ask and call onEvent for every server-sent event (steps, query, answer, citations, done). */
export async function askStream(question, onEvent, { signal } = {}) {
  const res = await fetch(`${API_PREFIX}/ask`, {
    method: "POST", signal, credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* keep status text */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : "Request failed");
  }
  const handle = (chunk) => chunk.split("\n").forEach((line) => {
    if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)));
  });
  if (!res.body || !res.body.getReader) {
    (await res.text()).split("\n\n").forEach(handle);
    return;
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    parts.forEach(handle);
  }
  if (buf.trim()) handle(buf);
}
