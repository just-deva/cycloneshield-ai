import { S, lead } from "../state.js";
import { api } from "../api.js";
import { esc, num, toast } from "../util.js";

export async function render(el) {
  if (!S.sim) { el.innerHTML = '<p class="note">No simulation yet.</p>'; return; }
  let r;
  try { r = await api.get(`/api/finance/${S.sim.sim_id}?lead_h=${lead()}&pool_crore=${S.pool}`); }
  catch (e) { el.innerHTML = `<div class="errbox">${esc(e.message)}</div>`; return; }
  el.innerHTML = `
    <h2>Anticipatory finance trigger monitor</h2>
    <p class="note">Shows <b>when</b> a pre-agreed trigger would fire and what share of a pre-arranged pool to <b>recommend</b> for early release. It is a recommendation memo for a human to approve. <b>No money moves.</b> ${esc(r.illustrative)}</p>
    <div class="row"><label>Pool (Rs crore, illustrative) <input type="number" id="pool" value="${S.pool}" min="1" step="1" style="width:80px"></label>
      <span class="note">as of ${esc(r.as_of)} (lead ${lead()} h)</span></div>
    <div class="cards">
      <div class="card"><div class="k">Tier reached</div><div class="v" style="font-size:1rem">${esc(r.tier_reached)}</div></div>
      <div class="card"><div class="k">Recommended release</div><div class="v">${r.recommended_release_pct}%</div><div class="s">Rs ${num(r.recommended_release_crore_inr, 2)} crore</div></div>
      <div class="card"><div class="k">Inputs</div><div class="s">wind ${num(r.inputs.peak_wind_kmh)} km/h<br>surge ${num(r.inputs.max_surge_m, 1)} m<br>expected loss ratio ${num(r.inputs.expected_loss_ratio * 100, 0)}%</div></div>
    </div>
    <table><thead><tr><th>Tier</th><th>Condition</th><th>Cum. %</th><th>Fired</th></tr></thead><tbody>
      ${r.tiers.map((t) => `<tr><td><b>${esc(t.tier)}</b><br><small>${esc(t.stage)}</small></td><td><small>${esc(t.condition)}<br><i>${esc(t.actions)}</i></small></td><td>${t.cumulative_pct}%</td>
        <td>${t.fired ? '<span class="pill ok">fired</span>' : `<span class="pill watch">${t.stage_reached ? "hazard not met" : "stage not reached"}</span>`}</td></tr>`).join("")}
    </tbody></table>
    <h3>Release recommendation memo (draft)</h3><pre class="xml">${esc(r.memo)}</pre>
    <div class="row"><button id="fin-approve" ${r.level === 0 ? "disabled" : ""}>Approve memo (logged)</button><span class="note">sha256 <span class="mono">${esc(r.memo_sha256.slice(0, 20))}...</span></span></div>
    <div id="fin-msg"></div>
    <h3>Basis risk</h3><ul class="note">${r.basis_risk.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>
    <details><summary>Reference programmes</summary><ul class="note">${r.references.map((x) => `<li><a href="${esc(x.split(": ")[1])}" target="_blank" rel="noopener">${esc(x.split(": ")[0])}</a></li>`).join("")}</ul></details>`;
  el.querySelector("#pool").onchange = (e) => { S.pool = Math.max(1, +e.target.value || 10); render(el); };
  el.querySelector("#fin-approve").onclick = async () => {
    try { await api.post(`/api/finance/${S.sim.sim_id}/approve`, { actor: S.actor, lead_h: lead(), pool_crore: S.pool }); toast(el.querySelector("#fin-msg"), "ok", "Memo approval recorded in the audit chain. No funds were moved."); }
    catch (e) { toast(el.querySelector("#fin-msg"), "err", e.message); }
  };
}
