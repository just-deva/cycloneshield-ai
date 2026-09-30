import { S } from "../state.js";
import { esc, num, clockAt, statusPill } from "../util.js";
import { focusAsset } from "../mapview.js";

const filt = { kind: "all", min: "at_risk" };
const ORDER = { ok: 0, watch: 1, at_risk: 2, critical: 3 };

export function render(el) {
  const sim = S.sim;
  if (!sim) { el.innerHTML = '<p class="note">No simulation yet.</p>'; return; }
  const rows = sim.assets
    .filter((a) => (filt.kind === "all" || a.kind === filt.kind) && ORDER[a.status] >= ORDER[filt.min])
    .sort((a, b) => ORDER[b.status] - ORDER[a.status] || b.hazard_score - a.hazard_score);
  const named = rows.filter((a) => !a.name.includes("(unnamed)"));
  const shown = (named.length >= 8 ? named : rows).slice(0, 120);
  el.innerHTML = `
    <h2>What gets hit, and when</h2>
    <div class="row">
      <label>Type <select id="f-kind"><option value="all">All</option><option value="hospital">Hospitals</option><option value="substation">Power substations</option><option value="shelter">Shelters</option></select></label>
      <label>Min status <select id="f-min"><option value="watch">Watch</option><option value="at_risk">At risk</option><option value="critical">Critical</option></select></label>
      <span class="note">${rows.length} match (showing ${shown.length})</span>
    </div>
    <div class="scroll"><table>
      <thead><tr><th>Asset</th><th>Status</th><th>Hazards</th><th>First impact</th><th>k/9</th></tr></thead>
      <tbody>${shown.map((a) => `
        <tr class="click" data-id="${esc(a.id)}" title="${esc(a.reasons.join(" | "))}">
          <td><b>${esc(a.name)}</b><br><small>${esc(a.kind)}${a.kind === "shelter" ? (a.usable ? " - usable" : " - NOT usable") : ""}${a.props?.designated ? " - designated" : ""}</small></td>
          <td>${statusPill(a.status)}</td>
          <td><small>${a.hazards.map((x) => ({ wind: `wind ${num(a.peak_wind_kmh)}`, surge: `surge ${num(a.surge_depth_m, 1)} m`, rain: `rain ${a.pluvial}` }[x])).join("<br>") || "-"}</small></td>
          <td><small>${esc(clockAt(sim, S.tenant, a.first_impact_h))}</small></td>
          <td>${a.scenario_hits ?? "-"}</td>
        </tr>`).join("")}</tbody></table></div>
    <p class="note">Statuses come from explicit thresholds (see Trust &rarr; Methodology): gale 62, damaging 89, destructive 118 km/h; surge depth 0.3 m passability; IMD heavy / very heavy rain 64.5 / 115.6 mm per day on waterlogging basins and runoff corridors. Click a row to locate it on the map. OSM lists many small unnamed clinics and schools; unnamed items are hidden when enough named ones exist.</p>
    <details><summary>Power lines and roads in the storm's path</summary>
      <p class="note">Power lines (OSM, clipped to the study area): ${num(sim.power_lines.total_km, 0)} km total; in gale wind ${num(sim.power_lines.gale_62, 0)} km, in damaging wind ${num(sim.power_lines.damaging_89, 0)} km, destructive ${num(sim.power_lines.destructive_118, 0)} km; flooded &gt;= 0.5 m ${num(sim.power_lines.flooded_km, 1)} km. OSM has the high-voltage grid but few distribution poles, where most cyclone outages occur, so these km understate distribution exposure.</p>
    </details>`;
  el.querySelector("#f-kind").value = filt.kind;
  el.querySelector("#f-min").value = filt.min;
  el.querySelector("#f-kind").onchange = (e) => { filt.kind = e.target.value; render(el); };
  el.querySelector("#f-min").onchange = (e) => { filt.min = e.target.value; render(el); };
  el.querySelectorAll("tr.click").forEach((tr) => tr.addEventListener("click", () => focusAsset(tr.dataset.id)));
}
