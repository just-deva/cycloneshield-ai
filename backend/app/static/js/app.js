import { S, on, lead } from "./state.js";
import { api } from "./api.js";
import { $, esc, h, num, clockAt, relLabel, tierPill, debounce, toast } from "./util.js";
import * as map from "./mapview.js";
import * as overview from "./tabs/overview.js";
import * as assets from "./tabs/assets.js";
import * as roads from "./tabs/roads.js";
import * as advisories from "./tabs/advisories.js";
import * as copilot from "./tabs/copilot.js";
import * as finance from "./tabs/finance.js";
import * as trust from "./tabs/trust.js";

const TABS = [["overview", "Overview", overview], ["assets", "Assets", assets], ["roads", "Roads & evac", roads],
              ["advisories", "Advisories", advisories], ["copilot", "Copilot", copilot], ["finance", "Finance", finance], ["trust", "Trust", trust]];
let tab = "overview";

const loading = (on_, text = "Running simulation...") => { $("#loading").hidden = !on_; $("#loading-text").textContent = text; };

function renderTabs() {
  const nav = $("#tabs");
  nav.innerHTML = TABS.map(([id, label]) => `<button role="tab" data-tab="${id}" class="${id === tab ? "active" : ""}">${esc(label)}</button>`).join("");
  nav.querySelectorAll("button").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; renderTabs(); renderBody(); }));
}

async function renderBody() {
  const el = $("#tabbody");
  const mod = TABS.find((t) => t[0] === tab)[2];
  try { await mod.render(el); }
  catch (e) { el.innerHTML = `<div class="errbox">${esc(e.message)}</div>`; console.error(e); }
}

function renderHealth() {
  const f = S.health?.features || {};
  const chip = (on_, label, why) => `<span class="chip ${on_ ? "on" : "off"}" title="${esc(why)}">${on_ ? "●" : "○"} ${esc(label)}</span>`;
  $("#health").innerHTML = chip(f.gemini, f.gemini ? `Gemini ${f.gemini_model}` : "Gemini off", f.gemini ? "Gemini API key configured" : "No GEMINI_API_KEY: advisories use the labelled template fallback")
    + chip(f.earth_engine, "Earth Engine", "Earth Engine layers are used when the project is registered; otherwise open terrain tiles")
    + chip(f.telegram, f.telegram ? "Telegram live" : "Telegram simulated", "Real dispatch to a Telegram chat when a bot token is configured");
}

// ---------- simulation ----------
async function runSim() {
  loading(true);
  try {
    S.sim = await api.post("/api/simulate", { tenant_id: S.tenant.id, storm_id: S.stormId, cross_track_km: S.scenario.cross_track_km,
      delta_kt: S.scenario.delta_kt, tide_m: S.scenario.tide_m, ensemble: true });
    S.activeAdvisory = null;
    const t = S.sim.timeline;
    const slider = $("#tl-slider");
    slider.min = t.length ? Math.floor(t[0].h) : -72; slider.max = t.length ? Math.ceil(t[t.length - 1].h) : 12;
    if (S.hour < +slider.min || S.hour > +slider.max) S.hour = Math.max(+slider.min, Math.min(+slider.max, -24));
    slider.value = S.hour;
    map.renderSim();
    if (!S._fitted) { map.invalidate(); map.fitTenant(); S._fitted = true; }
    if (S._eeTenant !== S.tenant.id) { S._eeTenant = S.tenant.id; map.loadEeTiles(S.tenant.id); }
    buildTimeline();
    await refreshSeverity();
    $("#mode-badge").textContent = S.sim.storm.kind === "bulletin" ? "BULLETIN (AI-READ)" : S.sim.storm.kind === "scenario" ? "WHAT-IF" : "REPLAY";
    renderBody();
  } catch (e) {
    $("#tabbody").innerHTML = `<div class="errbox">${esc(e.message)}</div>`;
  } finally { loading(false); }
}

async function refreshSeverity() {
  if (!S.sim) return;
  try { S.severity = await api.get(`/api/severity/${S.sim.sim_id}?lead_h=${lead()}`); } catch { S.severity = null; }
  updateTimelineHead();
}

// ---------- timeline ----------
const STAGES = [[-72, "Watch"], [-48, "Alert"], [-24, "Warning"], [-12, "Outlook"], [0, "T0"]];
function buildTimeline() {
  const slider = $("#tl-slider"), min = +slider.min, max = +slider.max;
  const pos = (v) => ((v - min) / (max - min)) * 100;
  $("#tl-marks").innerHTML = STAGES.filter(([v]) => v >= min && v <= max).map(([v, l]) => `<span style="left:${pos(v)}%">${esc(v === 0 ? "T0" : `T${v}`)} ${v === 0 ? "" : esc(l)}</span>`).join("");
  $("#tl-presets").innerHTML = [-72, -48, -24, -12, 0].filter((v) => v >= min && v <= max).map((v) => `<button class="ghost ${v === S.hour ? "active" : ""}" data-h="${v}">${v === 0 ? "Closest approach" : `T${v} h`}</button>`).join("");
  $("#tl-presets").querySelectorAll("button").forEach((b) => (b.onclick = () => { slider.value = b.dataset.h; onHour(+b.dataset.h, true); }));
  updateTimelineHead();
}

function updateTimelineHead() {
  if (!S.sim) return;
  $("#tl-clock").textContent = `${relLabel(S.hour)} - ${clockAt(S.sim, S.tenant, S.hour)}`;
  const st = $("#tl-stage");
  if (S.severity) { st.className = `pill ${({ green: "green", watch: "blue", yellow: "yellow", orange: "orange", red: "red" })[S.severity.colour]}`; st.textContent = S.severity.name; }
  const pt = S.sim.timeline.reduce((b, x) => (Math.abs(x.h - S.hour) < Math.abs(b.h - S.hour) ? x : b), S.sim.timeline[0]);
  if (pt) $("#tl-wind").textContent = `storm ${num(pt.dist_focus_km, 0)} km from ${S.sim.tenant.focus.label}, ${num(pt.focus_wind_kmh, 0)} km/h there now`;
  $("#tl-presets").querySelectorAll("button").forEach((b) => b.classList.toggle("active", +b.dataset.h === S.hour));
}

const settle = debounce(async () => { await refreshSeverity(); if (["overview", "advisories", "finance", "copilot"].includes(tab)) renderBody(); }, 250);
function onHour(hr, immediate = false) {
  map.setHour(hr);
  updateTimelineHead();
  immediate ? (refreshSeverity().then(() => renderBody())) : settle();
}

// ---------- selectors ----------
function fillStorms() {
  const t = S.tenant;
  const stormOpts = [...t.replay_storms.map((id) => S.storms.find((s) => s.id === id)).filter(Boolean),
    ...S.storms.filter((s) => !t.replay_storms.includes(s.id)), ...S.bulletinStorms.map((b) => ({ id: b.id, name: b.name + " (read by Gemini)", season: "" }))];
  $("#storm").innerHTML = stormOpts.map((s) => `<option value="${esc(s.id)}">${esc(s.name)} ${esc(s.season)}${t.replay_storms.includes(s.id) ? "" : " - other region"}</option>`).join("");
  if (!stormOpts.some((s) => s.id === S.stormId)) S.stormId = stormOpts[0].id;
  $("#storm").value = S.stormId;
}

// ---------- modals ----------
function modal(html) { $("#modal-body").innerHTML = html; const d = $("#modal"); if (!d.open) d.showModal(); return $("#modal-body"); }

function openScenario() {
  const b = modal(`<h2>What-if scenario</h2><p class="note">Shift the whole track sideways or change intensity to stress-test the district. Pressure is scaled consistently with the wind. This is not a forecast.</p>
    <div class="row"><label>Track shift (km, + = right of motion) <input type="range" id="sc-track" min="-100" max="100" step="10" value="${S.scenario.cross_track_km}"></label><b id="sc-track-v">${S.scenario.cross_track_km}</b></div>
    <div class="row"><label>Intensity change (kt) <input type="range" id="sc-kt" min="-40" max="60" step="5" value="${S.scenario.delta_kt}"></label><b id="sc-kt-v">${S.scenario.delta_kt}</b></div>
    <div class="row"><label>Astronomical tide at peak (m) <input type="number" id="sc-tide" step="0.1" min="-1" max="3" value="${S.scenario.tide_m ?? S.tenant.tide_default_m ?? 0.4}" style="width:80px"></label><span class="note">assumed; the demo has no tide gauge feed</span></div>
    <div class="row"><button id="sc-run">Run scenario</button><button class="ghost" id="sc-reset">Reset to the real track</button></div>`);
  const bind = (id) => b.querySelector(`#${id}`).oninput = (e) => (b.querySelector(`#${id}-v`).textContent = e.target.value);
  bind("sc-track"); bind("sc-kt");
  b.querySelector("#sc-run").onclick = () => { S.scenario = { cross_track_km: +b.querySelector("#sc-track").value, delta_kt: +b.querySelector("#sc-kt").value, tide_m: +b.querySelector("#sc-tide").value }; $("#modal").close(); runSim(); };
  b.querySelector("#sc-reset").onclick = () => { S.scenario = { cross_track_km: 0, delta_kt: 0, tide_m: null }; $("#modal").close(); runSim(); };
}

function openBulletin() {
  const gem = S.health?.features?.gemini;
  const b = modal(`<h2>Read an official bulletin with Gemini</h2>
    <p class="note">IMD publishes cyclone bulletins only as PDF/PNG (no machine-readable feed). Upload one (PDF, PNG, JPEG) or paste its text: Gemini 3.7 Flash extracts the track and intensity into a schema; deterministic code then range-checks positions, converts kt/km/h, orders times, and shows you what it read so you can verify it against the source.</p>
    ${gem ? "" : '<div class="warnbox">GEMINI_API_KEY is not configured on this server, so bulletin reading is unavailable.</div>'}
    <div class="row"><input type="file" id="bf" accept="application/pdf,image/png,image/jpeg,text/plain" ${gem ? "" : "disabled"}><button id="bgo" ${gem ? "" : "disabled"}>Read with Gemini</button></div>
    <details><summary>Or paste bulletin text</summary><textarea id="bt" rows="6" placeholder="Paste the text of a cyclone bulletin..."></textarea><button id="bgo2" ${gem ? "" : "disabled"}>Read pasted text</button></details>
    <div id="bres"></div>`);
  const show = (r) => {
    const x = r.extraction;
    const rows = [x.current, ...x.forecast].filter(Boolean);
    b.querySelector("#bres").innerHTML = `<h3>What Gemini read</h3>
      <p class="note">${esc(x.agency || "?")} - ${esc(x.storm_name || "?")} - bulletin ${esc(x.bulletin_no || "?")} - issued ${esc(x.issued_utc || "?")} - winds ${esc(x.wind_averaging_min ?? "?")}-min - ${esc(r.model)} in ${r.latency_ms} ms</p>
      <table><thead><tr><th>Time (UTC)</th><th>Lat</th><th>Lon</th><th>Wind</th><th>Category</th></tr></thead><tbody>${rows.map((p) => `<tr><td>${esc(p.time_utc || `+${p.hours_from_issue ?? "?"} h`)}</td><td>${p.lat}</td><td>${p.lon}</td><td>${p.wind ?? "-"} ${esc(p.wind_unit)}</td><td>${esc(p.category || "")}</td></tr>`).join("")}</tbody></table>
      ${x.surge_text ? `<p class="note"><b>Surge sentence (verbatim):</b> ${esc(x.surge_text)}</p>` : ""}${x.landfall_text ? `<p class="note"><b>Landfall (verbatim):</b> ${esc(x.landfall_text)}</p>` : ""}
      ${r.issues.map((i) => `<div class="${i.level === "error" ? "errbox" : i.level === "warning" ? "warnbox" : "okbox"}">${esc(i.level)}: ${esc(i.msg)}</div>`).join("")}
      ${r.storm_id ? `<div class="row"><button id="bsim">Simulate this track for ${esc(S.tenant.name)}</button></div><p class="note">Always compare the table with the source document before acting. Values are AI-extracted.</p>` : '<div class="errbox">No usable track could be extracted.</div>'}`;
    const go = b.querySelector("#bsim");
    if (go) go.onclick = () => { S.bulletinStorms.push({ id: r.storm_id, name: x.storm_name || "Bulletin storm" }); S.stormId = r.storm_id; fillStorms(); $("#modal").close(); runSim(); };
  };
  const run = async (fn, btn) => { btn.disabled = true; btn.textContent = "Reading..."; try { show(await fn()); } catch (e) { b.querySelector("#bres").innerHTML = `<div class="errbox">${esc(e.message)}</div>`; } btn.disabled = false; btn.textContent = "Read with Gemini"; };
  b.querySelector("#bgo").onclick = (e) => { const f = b.querySelector("#bf").files[0]; if (f) run(() => api.upload("/api/bulletin/extract", f), e.target); };
  b.querySelector("#bgo2").onclick = (e) => { const t = b.querySelector("#bt").value; if (t.length > 20) run(() => api.post("/api/bulletin/extract-text", { text: t }), e.target); };
}

// ---------- boot ----------
async function boot() {
  try {
    [S.health, S.tenants, S.storms] = await Promise.all([api.get("/api/health"), api.get("/api/tenants"), api.get("/api/storms")]);
  } catch (e) { $("#tabbody").innerHTML = `<div class="errbox">${esc(e.message)}</div>`; return; }
  renderHealth();
  map.initMap();
  $("#tenant").innerHTML = S.tenants.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("");
  S.tenant = S.tenants[0];
  fillStorms();
  renderTabs();
  $("#tenant").onchange = (e) => { S.tenant = S.tenants.find((t) => t.id === e.target.value); S.stormId = S.tenant.replay_storms[0]; S.scenario = { cross_track_km: 0, delta_kt: 0, tide_m: null }; S.language = "English"; fillStorms(); S._fitted = false; runSim(); };
  $("#storm").onchange = (e) => { S.stormId = e.target.value; S.scenario = { cross_track_km: 0, delta_kt: 0, tide_m: null }; runSim(); };
  $("#btn-scenario").onclick = openScenario;
  $("#btn-bulletin").onclick = openBulletin;
  $("#tl-slider").addEventListener("input", (e) => onHour(+e.target.value));
  window.addEventListener("resize", () => map.invalidate());
  map.fitTenant();
  setTimeout(async () => { try { S.health = await api.get("/api/health"); renderHealth(); } catch { /* ignore */ } }, 6000);
  await runSim();
}

boot();
