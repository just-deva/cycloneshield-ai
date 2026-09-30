import { S, ACTORS, lead } from "../state.js";
import { api } from "../api.js";
import { esc, num, clockAt, tierPill, toast, h } from "../util.js";

let roles = [];
let list = [];
let busy = false;
const ALL_LANGS = ["English", "Telugu", "Hindi", "Odia", "Bengali", "Tamil", "Malayalam", "Kannada", "Marathi", "Gujarati", "Vietnamese"];

export async function render(el) {
  if (!S.sim) { el.innerHTML = '<p class="note">No simulation yet.</p>'; return; }
  if (!roles.length) roles = await api.get("/api/roles").catch(() => []);
  list = (await api.get("/api/advisories").catch(() => [])).filter((a) => a.sim_id === S.sim.sim_id);
  const langs = [...new Set([...(S.tenant.languages || []), ...ALL_LANGS])];
  const sev = S.severity;
  const active = list.find((a) => a.id === S.activeAdvisory) || null;
  const tg = S.health?.features?.telegram;
  el.innerHTML = `
    <h2>Advisories: draft, approve, dispatch</h2>
    <p class="note">Gemini <b>drafts</b>; code decides the tier and checks every number; a human <b>approves</b> (two people for orange/red); only then is anything sent. Everything is logged in a hash-chained audit trail.</p>
    <div class="tier-banner tier-${sev ? sev.colour : "green"}">${sev ? esc(sev.name) : "-"} at T-${lead()} h<small>${sev ? esc(sev.rule) : ""}</small></div>
    <div class="row">
      <label>Acting as <select id="a-actor">${ACTORS.map((a) => `<option ${a === S.actor ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></label>
    </div>
    <div class="row">
      <label>Audience <select id="a-role">${roles.map((r) => `<option value="${esc(r.role)}" ${r.role === S.role ? "selected" : ""}>${esc(r.role.replace("_", " "))}</option>`).join("")}</select></label>
      <label>Language <select id="a-lang">${langs.map((l) => `<option ${l === S.language ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      <button id="a-draft">Draft advisory</button>
    </div>
    <div class="${tg ? "okbox" : "warnbox"}">Telegram delivery: ${tg ? "configured - dispatch sends a real message with an Acknowledge button" : "not configured - dispatch is simulated and labelled (set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)"}. SMS, WhatsApp and Cell Broadcast are always simulated (they need SDMA/telecom gateways).</div>
    <div id="a-msg"></div>
    ${list.length ? `<h3>Advisories for this simulation</h3><div class="row">${list.map((a) => `<button class="ghost ${a.id === S.activeAdvisory ? "active" : ""}" data-id="${esc(a.id)}">${esc(a.role.replace("_", " "))} / ${esc(a.language)} <small>${esc(a.status)}</small></button>`).join("")}</div>` : ""}
    <div id="a-detail">${active ? detailHtml(active) : ""}</div>`;
  el.querySelector("#a-actor").onchange = (e) => { S.actor = e.target.value; render(el); };
  el.querySelector("#a-role").onchange = (e) => { S.role = e.target.value; };
  el.querySelector("#a-lang").onchange = (e) => { S.language = e.target.value; };
  el.querySelector("#a-draft").onclick = () => draft(el);
  el.querySelectorAll("[data-id]").forEach((b) => (b.onclick = () => { S.activeAdvisory = b.dataset.id; render(el); }));
  if (active) wire(el, active);
}

async function draft(el) {
  if (busy) return;
  busy = true;
  const btn = el.querySelector("#a-draft");
  btn.disabled = true; btn.textContent = "Drafting with Gemini...";
  try {
    const a = await api.post("/api/advisories/draft", { sim_id: S.sim.sim_id, lead_h: lead(), role: S.role, language: S.language, actor: S.actor });
    S.activeAdvisory = a.id;
  } catch (e) { toast(el.querySelector("#a-msg"), "err", e.message); }
  busy = false;
  await render(el);
}

function checks(v) {
  if (!v) return "";
  return v.checks.map((c) => `<div class="check ${c.ok ? "ok" : "bad"}"><span><b>${esc(c.name.replaceAll("_", " "))}</b>: ${esc(c.detail)}</span></div>`).join("");
}

function textBlock(t) {
  if (!t || !t.headline) return "";
  return `<h4>${esc(t.headline)}</h4>${t.situation ? `<p>${esc(t.situation)}</p>` : ""}
    ${t.actions?.length ? `<ul>${t.actions.map((x) => `<li><b>${esc(x.who)}</b>: ${esc(x.action)} <small>(by ${esc(x.deadline)})</small></li>`).join("")}</ul>` : ""}
    ${t.uncertainty ? `<p class="note"><i>${esc(t.uncertainty)}</i></p>` : ""}`;
}

function detailHtml(a) {
  const loc = a.localized && a.localized.headline && a.language !== "English";
  const sourceBadge = a.source === "template"
    ? '<span class="badge" style="background:#4a3b0a;color:#fde68a">TEMPLATE FALLBACK</span>'
    : `<span class="badge" ${a.cached ? 'style="background:#1e293b;color:#cbd5e1" title="Real Gemini output for identical facts, generated ' + esc(a.cached.cached_utc.slice(0, 16)) + ' UTC, re-validated now"' : ""}>GEMINI: ${esc(a.source)}${a.cached ? " " + esc(a.cached.cached_utc.slice(0, 10)) : ""}</span>`;
  const dsp = a.dispatch;
  return `<div class="advisory" data-adv="${esc(a.id)}">
    <div class="row">${tierPill(a.tier)} <span class="badge">${esc(a.status)}</span> ${sourceBadge}
      <small class="muted">${esc(a.role.replace("_", " "))} - ${esc(a.language)} - approvals ${a.approvals.length}/${a.required_approvals}</small></div>
    ${loc ? `<div>${textBlock(a.localized)}</div><details><summary>English source text</summary>${textBlock(a.english)}</details>` : textBlock(a.english)}
    ${a.notes?.length ? a.notes.map((n) => `<div class="warnbox">${esc(n)}</div>`).join("") : ""}
    <h3>Guardrails</h3>${checks(a.validation)}
    ${a.translation?.validation ? `<div class="note">Translation (${esc(a.translation.model)}):</div>${checks(a.translation.validation)}` : ""}
    <div class="note">Tier decided by rules: ${esc(a.tier.rule)}. Facts packet sha256: <span class="mono">${esc(a.facts_sha256)}</span></div>
    <div class="row" id="a-actions"></div>
    ${dsp ? dispatchHtml(a) : ""}
    <div id="a-xml"></div>
    <details><summary>Audit trail for this advisory (${a.history.length})</summary>
      ${a.history.map((x) => `<div class="mono">${esc(x.ts.slice(0, 19))} - ${esc(x.actor)} - <b>${esc(x.action)}</b> - ${esc(x.entry_hash.slice(0, 16))}...</div>`).join("")}</details>
  </div>`;
}

function dispatchHtml(a) {
  return `<h3>Dispatch results</h3><table><thead><tr><th>Channel</th><th>Status</th><th>Detail</th></tr></thead><tbody>
    ${a.dispatch.results.map((r) => `<tr><td>${esc(r.channel)}</td><td><span class="pill ${r.status === "sent" ? "ok" : r.status === "failed" ? "critical" : "watch"}">${esc(r.status)}</span></td><td><small>${esc(r.detail)}</small></td></tr>`).join("")}</tbody></table>
    <p class="note">Dispatched by ${esc(a.dispatch.actor)}. CAP sha256 <span class="mono">${esc(a.dispatch.cap_sha256.slice(0, 24))}...</span>${a.acks?.length ? ` - acknowledged by ${esc(a.acks.map((x) => `${x.actor} via ${x.via}`).join(", "))}` : ""}</p>`;
}

function wire(el, a) {
  const box = el.querySelector("#a-actions");
  const msg = el.querySelector("#a-msg");
  // rerender=false for view-only actions (editor, XML, read-aloud) so what they open is not wiped by a refresh
  const act = (label, cls, fn, disabled = false, title = "", rerender = true) => {
    const b = h(`<button class="${cls}" ${disabled ? "disabled" : ""} title="${esc(title)}">${esc(label)}</button>`);
    b.onclick = async () => {
      b.disabled = true;
      try { await fn(); } catch (e) { toast(msg, "err", e.message); }
      if (rerender) await render(el); else b.disabled = false;
    };
    box.append(b);
  };
  const call = (p, body) => api.post(`/api/advisories/${a.id}/${p}`, { actor: S.actor, ...(body || {}) });
  if (a.status === "DRAFT") {
    act("Edit", "ghost", async () => { if (!el.querySelector("#a-editor")) openEditor(el, a); }, false, "", false);
    act("Submit for approval", "", () => call("submit"), !a.validation?.passed, a.validation?.passed ? "" : "Validator did not pass");
  }
  if (a.status === "PENDING_APPROVAL") {
    act(`Approve as ${S.actor}`, "ok", () => call("approve"), false, "Maker-checker: the approver must differ from the maker" + (a.required_approvals > 1 ? "; orange/red needs two different approvers" : ""));
    act("Reject", "danger", () => call("reject", { reason: "rejected by officer" }));
  }
  if (a.status === "APPROVED") act("Dispatch now", "warn", () => call("dispatch"));
  if (a.status === "DISPATCHED" || a.status === "ACKED") {
    act("Acknowledge receipt (simulate)", "ok", () => call("ack"));
    act("Cancel (CAP Cancel)", "danger", () => call("cancel"));
  }
  if (a.status === "DRAFT" && (a.cached || a.source === "template")) {
    act("Regenerate live with Gemini", "ghost", async () => {
      const n = await api.post("/api/advisories/draft", { sim_id: S.sim.sim_id, lead_h: a.lead_h, role: a.role, language: a.language, actor: S.actor, refresh: true });
      S.activeAdvisory = n.id;
    }, false, "Calls the model now (uses quota). If Gemini is unavailable the labelled template is used.");
  }
  act("View CAP XML", "ghost", async () => {
    const xml = await api.get(`/api/advisories/${a.id}/cap.xml`);
    el.querySelector("#a-xml").innerHTML = `<h3>CAP 1.2 (status Exercise, scope Restricted)</h3><pre class="xml">${esc(xml)}</pre>`;
  }, false, "", false);
  act("Read aloud", "ghost", async () => {
    const t = a.localized?.headline && a.language !== "English" ? a.localized : a.english;
    const text = [t.headline, t.situation, ...(t.actions || []).map((x) => `${x.who}: ${x.action}`)].join(". ");
    if (!("speechSynthesis" in window)) throw new Error("This browser has no speech synthesis. Try Chrome or Edge.");
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text); u.lang = a.locale || "en-IN"; speechSynthesis.speak(u);
  }, false, "Uses the browser's built-in voices; availability varies by language", false);
}

function openEditor(el, a) {
  const t = a.english;
  const form = h(`<div class="advisory" id="a-editor"><h3>Edit draft (English source)</h3>
    <label>Headline</label><textarea id="e-h" rows="2">${esc(t.headline)}</textarea>
    <label>Situation</label><textarea id="e-s" rows="3">${esc(t.situation)}</textarea>
    <label>Uncertainty</label><textarea id="e-u" rows="2">${esc(t.uncertainty)}</textarea>
    ${t.actions.map((x, i) => `<div class="row"><input type="text" data-i="${i}" data-k="who" value="${esc(x.who)}" placeholder="who" size="14"><input type="text" data-i="${i}" data-k="action" value="${esc(x.action)}" placeholder="action" size="30"><input type="text" data-i="${i}" data-k="deadline" value="${esc(x.deadline)}" placeholder="by" size="14"></div>`).join("")}
    <div class="row"><button id="e-save">Save &amp; re-validate</button></div>
    <p class="note">Edits are re-checked by the validator (numbers must still come from the model output) and clear any approvals. The edit is logged.</p></div>`);
  el.querySelector("#a-detail").append(form);
  form.querySelector("#e-save").onclick = async () => {
    const actions = t.actions.map((x, i) => ({ ...x, who: form.querySelector(`[data-i="${i}"][data-k=who]`).value, action: form.querySelector(`[data-i="${i}"][data-k=action]`).value, deadline: form.querySelector(`[data-i="${i}"][data-k=deadline]`).value }));
    try {
      await api.patch(`/api/advisories/${a.id}`, { actor: S.actor, headline: form.querySelector("#e-h").value, situation: form.querySelector("#e-s").value, uncertainty: form.querySelector("#e-u").value, actions });
    } catch (e) { toast(el.querySelector("#a-msg"), "err", e.message); }
    await render(el);
  };
}
