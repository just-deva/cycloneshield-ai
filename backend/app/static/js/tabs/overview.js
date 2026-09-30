import { S } from "../state.js";
import { esc, num, clockAt, relLabel, tierPill } from "../util.js";
import { api } from "../api.js";

const EE = { simId: null, data: null };

async function fillEarthEngine(el, sim) {
  const box = el.querySelector("#ee-box");
  if (!box) return;
  if (EE.simId !== sim.sim_id) {
    box.textContent = "Checking Earth Engine (live GFS rain, population and buildings in the flood zone)...";
    try { EE.data = await api.get(`/api/gee/summary/${sim.sim_id}`); } catch (e) { EE.data = { available: false, note: e.message }; }
    EE.simId = sim.sim_id;
  }
  const d = EE.data;
  if (!el.contains(box)) return;
  if (!d.available) { box.innerHTML = `<div class="warnbox">Earth Engine is not connected on this server${d.error ? ` (${esc(String(d.error).split(/\r?\n/)[0].slice(0, 120))})` : ""}. The simulation above runs on open terrain tiles; with Earth Engine connected this panel shows live NOAA GFS forecast rain and the people/buildings inside the modelled flood zone.</div>`; return; }
  const r = d.rain, x = d.exposure;
  box.innerHTML = `<div class="cards">
    ${r ? `<div class="card"><div class="k">GFS rain next 24 h / 72 h</div><div class="v">${num(r.focus_24h_mm, 0)} / ${num(r.focus_72h_mm, 0)} mm</div><div class="s">at ${esc(sim.tenant.focus.label)}; max in area ${num(r.max_72h_mm, 0)} mm (72 h)</div></div>` : ""}
    ${x ? `<div class="card"><div class="k">People in flood zone</div><div class="v">${x.people === null ? "-" : Number(x.people).toLocaleString()}</div><div class="s">GHSL 2025 population grid</div></div>
    <div class="card"><div class="k">Buildings in flood zone</div><div class="v">${x.buildings === null ? "-" : Number(x.buildings).toLocaleString()}</div><div class="s">Google Open Buildings v3</div></div>` : ""}</div>
    <p class="note">${r ? esc(r.note) : ""} ${x ? esc(x.note || "") : ""} ${d.rain_error ? `Rain: ${esc(d.rain_error)}` : ""} ${d.exposure_error ? `Exposure: ${esc(d.exposure_error)}` : ""}</p>`;
}

export function render(el) {
  const sim = S.sim;
  if (!sim) { el.innerHTML = '<p class="note">Run a simulation to see the situation.</p>'; return; }
  const f = sim.focus, k = sim.summary.by_kind;
  const surgeMax = Math.max(...sim.sectors.map((s) => s.surge_max_m ?? s.surge_m), 0);
  const surgeMin = Math.max(...sim.sectors.map((s) => s.surge_min_m ?? s.surge_m), 0);
  const risky = (x) => (x ? x.critical + x.at_risk : 0);
  const sev = S.severity;
  const tierCls = sev ? `tier-${sev.colour}` : "tier-green";
  const es = sim.evacuation.summary;
  el.innerHTML = `
    <div class="tier-banner ${tierCls}">
      ${sev ? `${esc(sev.name)} (${esc(sev.colour)}) - as of ${esc(clockAt(sim, S.tenant, -Math.max(0, -S.hour)))}` : "Tier"}
      <small>${sev ? esc(sev.rule) : ""}${sev && sev.hazard_reasons.length ? `<br>Why: ${esc(sev.hazard_reasons.join("; "))}` : ""}</small>
    </div>
    <div class="row"><b>${esc(sim.storm.name)}</b> <span class="badge">${esc(sim.storm.kind.toUpperCase())}</span>
      <span class="note">${esc(sim.tenant.name)} - closest approach ${num(sim.closest_approach_km, 0)} km at ${esc(clockAt(sim, S.tenant, 0))}</span></div>
    <p class="note">${esc(sim.storm.summary || "")}</p>
    ${sim.official_surge ? `<div class="okbox"><b>Official surge guidance in the bulletin</b> (read by Gemini - verify against the source): ${esc(sim.official_surge.text || "")} ${sim.official_surge.high_m != null ? `(${sim.official_surge.low_m ?? "?"}-${sim.official_surge.high_m} m)` : ""}<br><small>Official guidance overrides our screening-level estimate wherever they differ.</small></div>` : ""}
    ${sim.storm.kind === "scenario" ? `<div class="warnbox">What-if scenario: track ${num(sim.scenario.cross_track_km, 0)} km sideways, intensity ${num(sim.scenario.delta_kt, 0)} kt. Not a forecast.</div>` : ""}
    <div class="cards">
      <div class="card"><div class="k">Peak wind at ${esc(sim.tenant.focus.label)}</div><div class="v">${num(f.peak_wind_kmh)} km/h</div><div class="s">${esc(f.category)} - ${esc(relLabel(f.peak_h))}</div></div>
      <div class="card"><div class="k">Storm surge (coast)</div><div class="v">${surgeMin === surgeMax ? num(surgeMax, 1) : `${num(surgeMin, 1)}-${num(surgeMax, 1)}`} m</div><div class="s">max over 9 scenarios, screening-level</div></div>
      <div class="card"><div class="k">Surge flooding</div><div class="v">${num(sim.flooded_km2, 1)} km&sup2;</div><div class="s">sea-connected, depth classes</div></div>
      <div class="card"><div class="k">Rain 24 h (prior)</div><div class="v">${num(f.rain24_mm)} mm</div><div class="s">${esc(f.rain_class)} (R-CLIPER)</div></div>
      <div class="card"><div class="k">Hospitals at risk</div><div class="v">${risky(k.hospital)} / ${k.hospital?.total ?? 0}</div><div class="s">critical + at risk</div></div>
      <div class="card"><div class="k">Substations at risk</div><div class="v">${risky(k.substation)} / ${k.substation?.total ?? 0}</div><div class="s">critical + at risk</div></div>
      <div class="card"><div class="k">Shelters usable</div><div class="v">${sim.summary.shelters_usable} / ${sim.summary.shelters_total}</div><div class="s">${sim.summary.designated_shelters} designated in OSM (candidates = schools/halls)</div></div>
      <div class="card"><div class="k">Arterial road cut</div><div class="v">${num(sim.summary.arterial_km_affected, 1)} km</div><div class="s">of ${num(sim.summary.arterial_km_total, 0)} km in area</div></div>
      <div class="card"><div class="k">Evacuation</div><div class="v">${es.routed ?? 0} / ${es.origins ?? 0}</div><div class="s">localities with a flood-safe route</div></div>
      <div class="card"><div class="k">Power lines</div><div class="v">${num(sim.power_lines.damaging_89, 0)} km</div><div class="s">in damaging wind (>= 89 km/h) of ${num(sim.power_lines.total_km, 0)} km</div></div>
    </div>
    <h3>How to read this</h3>
    <ul class="note">
      <li>Drag the <b>event clock</b> under the map: the storm moves and assets light up as they are first hit. The IMD 4-stage warning clock (Watch 72 h, Alert 48 h, Warning 24 h, Outlook 12 h) sets the tier.</li>
      <li>Open <b>Assets</b> for the "what gets hit, when" table, <b>Advisories</b> to draft, approve and dispatch, <b>Copilot</b> to ask questions, <b>Trust</b> for methods, calibration and the audit chain.</li>
      <li>"k of 9" = in how many of 9 what-if scenarios (track &plusmn;40 km, intensity &plusmn;10 kt) an asset is hit. It is a spread, not a calibrated probability.</li>
    </ul>
    <h3>Data &amp; authority</h3>
    <p class="note"><b>Track:</b> ${esc(sim.storm.source)}<br><b>Authority:</b> ${esc(sim.storm.authority)}. Winds are ${esc(sim.storm.wind_avg_period_min)}-minute sustained (IMD's 3-minute values run a few percent lower).<br>
    <b>Exposure:</b> OpenStreetMap - ${sim.exposure_counts.hospitals} hospitals, ${sim.exposure_counts.substations} substations, ${sim.exposure_counts.arterial_road_ways} arterial road segments, ${sim.exposure_counts.shelters} candidate shelters. OSM is sparse for distribution poles and designated cyclone shelters.</p>
    <h3>Earth Engine (live data)</h3><div id="ee-box" class="note"></div>
    ${sim.exposure_counts.road_ways === 0 ? '<div class="warnbox">No road network is loaded for this region yet, so roads and evacuation routing are unavailable here.</div>' : ""}`;
  fillEarthEngine(el, sim);
}
