// Small shared helpers. Everything inserted into HTML goes through esc() (the API returns text that includes
// OSM names and LLM output, which must never be interpreted as markup).

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export const num = (x, d = 0) => (x === null || x === undefined || Number.isNaN(+x) ? "-" : (+x).toFixed(d));

export const STATUS_LABEL = { ok: "OK", watch: "Watch", at_risk: "At risk", critical: "Critical", cut: "Cut", waterlogging_likely: "Waterlogging" };
export const statusPill = (s) => `<span class="pill ${esc(s)}">${esc(STATUS_LABEL[s] || s)}</span>`;
export const TIER_CLASS = { green: "green", watch: "blue", yellow: "yellow", orange: "orange", red: "red" };
export const tierPill = (t) => `<span class="pill ${TIER_CLASS[t.colour] || "green"}">${esc(t.name)}</span>`;

// Clock string for "hours relative to closest approach" in the tenant's local timezone.
export function clockAt(sim, tenant, relH) {
  if (relH === null || relH === undefined) return "-";
  const off = (tenant?.utc_offset_hours ?? 5.5) * 3600e3;
  const t = new Date(Date.parse(sim.t0) + relH * 3600e3 + off);
  const day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][t.getUTCDay()];
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][t.getUTCMonth()];
  const pad = (n) => String(n).padStart(2, "0");
  return `${day} ${pad(t.getUTCDate())} ${mon} ${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())} ${tenant?.tz_label ?? "IST"}`;
}

export function relLabel(hours) {
  if (hours === null || hours === undefined) return "-";
  if (Math.abs(hours) < 0.5) return "T0";
  return `T${hours < 0 ? "-" : "+"}${Math.abs(Math.round(hours))} h`;
}

export function toast(container, kind, msg) {
  const cls = { err: "errbox", warn: "warnbox", ok: "okbox" }[kind] || "note";
  const el = h(`<div class="${cls}">${esc(msg)}</div>`);
  container.prepend(el);
  setTimeout(() => el.remove(), 9000);
  return el;
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
