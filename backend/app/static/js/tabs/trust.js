import { S } from "../state.js";
import { api } from "../api.js";
import { esc, num } from "../util.js";

export async function render(el) {
  const [meth, calib, trace, audit] = await Promise.all([
    api.get("/api/methodology").catch(() => null), S.tenant ? api.get(`/api/calibration/${S.tenant.id}`).catch(() => null) : null,
    api.get("/api/trace?n=12").catch(() => []), api.get("/api/audit?limit=8").catch(() => null)]);
  const sim = S.sim;
  el.innerHTML = `
    <h2>Trust and validation</h2>
    <div class="two-col">
      <div><b>What AI does (Gemini 3.7 Flash)</b><ul><li>Reads a bulletin PDF/image into a structured track</li><li>Writes advisories from a facts packet, in the officer's language</li><li>Answers questions by calling our tools</li></ul></div>
      <div><b>What code does (deterministic)</b><ul><li>Wind, surge, flooding, rain pathways, asset status</li><li>Warning tier (IMD stage clock + hazard rules)</li><li>Number/name validation, approval rules, CAP, audit chain</li></ul></div>
    </div>
    <h3>Guardrails on every AI output</h3>
    <ul class="note"><li><b>Numbers</b> in a draft must appear in the model output (validator blocks anything else, incl. translations, any digit script).</li>
    <li><b>Severity</b> is set by rules, never by the LLM.</li><li><b>Untrusted text</b> (feeds, bulletins) is treated as data; the model has no dispatch tool.</li>
    <li>If a draft fails validation twice, a labelled <b>template</b> is used. Dispatch needs <b>human approval</b> (two people for orange/red).</li></ul>
    ${calib ? calibrationHtml(calib) : ""}
    ${meth ? `<h3>Methodology, assumptions and limits</h3>${meth.modules.map((m) => `<details><summary>${esc(m.module)}</summary><p class="note"><b>Method:</b> ${esc(m.method)}<br><b>Assumptions / limits:</b> ${esc(m.assumptions)}</p></details>`).join("")}` : ""}
    <h3>Audit chain</h3>
    <div class="row"><button id="verify" class="ghost">Verify hash chain</button><span id="verify-out" class="note">${audit ? (audit.verify.ok ? `✔ ${audit.verify.entries} entries, chain intact` : `✘ broken at entry ${audit.verify.broken_at}`) : ""}</span></div>
    <p class="note">Append-only and hash-chained: each entry commits to the previous one, so any edit or deletion breaks every later hash. For stronger guarantees anchor the head in a retention-locked bucket and sign entries with Cloud KMS. We do not call this a blockchain or tamper-proof.</p>
    ${audit?.entries?.length ? `<details><summary>Latest entries</summary>${audit.entries.map((e) => `<div class="mono">#${e.seq} ${esc(e.ts.slice(0, 19))} ${esc(e.actor)} <b>${esc(e.action)}</b> ${esc(e.entry_hash.slice(0, 14))}</div>`).join("")}</details>` : ""}
    <h3>AI trace (latest Gemini calls)</h3>
    ${trace.length ? `<div class="scroll"><table><thead><tr><th>Purpose</th><th>Model</th><th>ms</th><th>Tools</th><th>Status</th></tr></thead><tbody>${trace.map((t) => `<tr><td>${esc(t.purpose)}<br><small>${esc((t.input || "").slice(0, 80))}</small></td><td><small>${esc(t.model || "-")}</small></td><td>${t.latency_ms ?? "-"}</td><td><small>${esc((t.tool_calls || []).map((c) => c.name).join(", ") || "-")}</small></td><td>${esc(t.status)}${t.fallback_used ? " (fallback model)" : ""}</td></tr>`).join("")}</tbody></table></div>` : '<p class="note">No Gemini calls yet. Draft an advisory or ask the copilot.</p>'}
    <h3>Data sources and attribution</h3>
    <ul class="note">${(S.tenant?.attribution || []).map((a) => `<li>${esc(a)}</li>`).join("")}<li>Rain prior: R-CLIPER (Tuleya et al. 2007). Wind: Holland (1980). Loss ratio: Emanuel (2011), NIO calibration from CLIMADA/Eberenz et al. (2021).</li></ul>
    ${sim ? `<p class="note">Earth Engine: ${S.health?.features?.earth_engine ? "enabled (see Earth Engine tab / status)" : "disabled"}. This run's terrain is open Terrarium tiles (SRTM-derived); the surface model is biased high under buildings and trees, so flooding is under-predicted in built-up areas.</p>` : ""}
    <div class="warnbox">${esc((await api.get("/api/methodology")).disclaimer)}</div>`;
  el.querySelector("#verify").onclick = async () => {
    const v = await api.get("/api/audit/verify");
    el.querySelector("#verify-out").textContent = v.ok ? `✔ ${v.entries} entries, chain intact` : `✘ chain broken at entry ${v.broken_at}: ${v.reason}`;
  };
}

function calibrationHtml(c) {
  if (!c.calibrated) return `<h3>Surge calibration</h3><div class="warnbox">${esc(c.note)}</div>`;
  return `<h3>Surge calibration (${esc(c.storm)}; observed ${c.observed_surge_m[0]}-${c.observed_surge_m[1]} m at ${esc(c.where)})</h3>
    <table><thead><tr><th>Sector</th><th>Modelled surge (m)</th><th>k</th></tr></thead><tbody>${c.sectors.map((s) => `<tr><td>${esc(s.sector)}</td><td>${num(s.modelled_surge_m, 2)}</td><td>${s.k}</td></tr>`).join("")}</tbody></table>
    <div class="warnbox">${esc(c.note)}</div>`;
}
