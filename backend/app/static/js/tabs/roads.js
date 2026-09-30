import { S } from "../state.js";
import { esc, num, clockAt, statusPill } from "../util.js";
import { focusLatLng } from "../mapview.js";

export function render(el) {
  const sim = S.sim;
  if (!sim) { el.innerHTML = '<p class="note">No simulation yet.</p>'; return; }
  const roads = sim.roads.filter((r) => r.status !== "watch").slice(0, 25);
  const routes = sim.evacuation.routes;
  const es = sim.evacuation.summary;
  el.innerHTML = `
    <h2>Roads and evacuation</h2>
    <div class="cards">
      <div class="card"><div class="k">Arterial km cut / waterlogged</div><div class="v">${num(sim.road_summary.arterial_km_affected, 1)}</div><div class="s">of ${num(sim.road_summary.arterial_km_total, 0)} km</div></div>
      <div class="card"><div class="k">Localities with safe route</div><div class="v">${es.routed ?? 0} / ${es.origins ?? 0}</div><div class="s">${es.safe_shelters ?? 0} safe shelters, ${es.blocked_nodes ?? 0} blocked nodes</div></div>
    </div>
    <h3>Roads cut or likely waterlogged</h3>
    ${roads.length ? `<div class="scroll"><table><thead><tr><th>Road</th><th>Status</th><th>km</th><th>First</th></tr></thead><tbody>
      ${roads.map((r) => `<tr><td>${esc(r.name)}<br><small>${esc(r.highway)}${r.bridge ? " - bridge" : ""} - ${esc(r.cause)}</small></td><td>${statusPill(r.status)}</td><td>${num(r.km_affected, 1)}</td><td><small>${esc(clockAt(sim, S.tenant, r.first_impact_h))}</small></td></tr>`).join("")}
      </tbody></table></div>` : '<p class="note">No road is cut in this scenario.</p>'}
    <h3>Evacuation: nearest safe shelter</h3>
    ${routes.length ? `<div class="scroll"><table><thead><tr><th>From</th><th>To</th><th>Min</th><th>Leave before</th></tr></thead><tbody>
      ${routes.map((r) => r.status === "route"
        ? `<tr class="click" data-lat="${r.lat}" data-lon="${r.lon}"><td>${esc(r.origin)}</td><td>${esc(r.shelter)}</td><td>${num(r.minutes, 0)}</td><td><small>${esc(clockAt(sim, S.tenant, r.depart_by_h))}</small></td></tr>`
        : `<tr class="click" data-lat="${r.lat ?? ""}" data-lon="${r.lon ?? ""}"><td>${esc(r.origin)}</td><td colspan="3"><span class="pill critical">no flood-safe route</span> <small>${esc((r.status || "").replace("_", " "))}: shelter in place / request assistance</small></td></tr>`).join("")}
      </tbody></table></div>` : '<p class="note">No routing is available for this region (road network not loaded).</p>'}
    <p class="note">Routes use the OSM road graph with flooded nodes (depth &gt;= 0.3 m, or waterlogging basins under very heavy rain) removed, to the nearest shelter that is not flooded. "Leave before" = local gale onset minus travel time minus a 1 h buffer. Shelters are OSM schools/halls unless designated; capacity is not modelled.</p>`;
  el.querySelectorAll("tr.click").forEach((tr) => tr.addEventListener("click", () => tr.dataset.lat && focusLatLng(+tr.dataset.lat, +tr.dataset.lon, 15)));
}
