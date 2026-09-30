// API client. Errors carry the server's `detail` so the UI can show a useful message (e.g. Gemini not configured).

async function request(method, path, body, isForm = false) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  }
  let res;
  try { res = await fetch(path, opts); }
  catch (e) { throw new Error("Cannot reach the server. Check your connection and try again."); }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = j.detail ? (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)) : detail; } catch { /* keep statusText */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b ?? {}),
  patch: (p, b) => request("PATCH", p, b),
  upload: (p, file) => { const f = new FormData(); f.append("file", file); return request("POST", p, f, true); },
};
