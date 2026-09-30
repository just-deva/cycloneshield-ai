// Leaflet map: storm track + position at the event clock, inundation & waterlogging overlays, assets, affected roads, routes.
import { S, emit } from "./state.js";
import { esc, clockAt, relLabel, num, statusPill, STATUS_LABEL } from "./util.js";

const GLYPH = { hospital: "+", substation: "⚡", shelter: "⌂" };
let map, layers = {}, markers = {}, stormMarker = null, inundation = null, pathways = null;
const toggles = { inundation: true, pathways: false, assets: true, roads: true, routes: true, upcoming: true, candidates: false };

export function initMap() {
  map = L.map("map", { zoomControl: true, preferCanvas: true }).setView([17.7, 83.25], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "&copy; OpenStreetMap contributors" }).addTo(map);
  for (const k of ["track", "sectors", "roads", "routes"]) layers[k] = L.layerGroup().addTo(map);
  const ORDER = { ok: 0, watch: 1, at_risk: 2, critical: 3 };
  const COLORS = ["#22c55e", "#eab308", "#f97316", "#ef4444"];
  layers.assets = L.markerClusterGroup({
    showCoverageOnHover: false, maxClusterRadius: 45, disableClusteringAtZoom: 15, chunkedLoading: true,
    iconCreateFunction: (c) => {
      const worst = Math.max(...c.getAllChildMarkers().map((m) => ORDER[m.options.status] ?? 0));
      return L.divIcon({ className: "", iconSize: [34, 34], html: `<div class="asset-icon" style="width:34px;height:34px;border-color:${COLORS[worst]};font-size:12px">${c.getChildCount()}</div>` });
    } }).addTo(map);
  renderTools();
}

function renderTools() {
  const el = document.getElementById("maptools");
  const row = (id, label, extra = "") => `<label><input type="checkbox" data-t="${id}" ${toggles[id] ? "checked" : ""}> ${label}${extra}</label>`;
  el.innerHTML = `<b>Layers</b>
    ${row("inundation", "Surge flooding", ' <span class="legend-dot" style="background:#2563eb"></span>')}
    ${row("pathways", "Rain pathways", ' <span class="legend-dot" style="background:#f97316"></span><span class="legend-dot" style="background:#a855f7"></span>')}
    ${row("assets", "Assets")}${row("candidates", "Candidate shelters (schools/halls)")}${row("roads", "Cut roads")}${row("routes", "Evacuation routes")}${row("upcoming", "Show not-yet-hit assets")}
    <small class="muted">orange = runoff corridors, purple = waterlogging basins</small>`;
  el.querySelectorAll("input").forEach((i) => i.addEventListener("change", () => { toggles[i.dataset.t] = i.checked; applyToggles(); }));
}

function applyToggles() {
  if (inundation) toggles.inundation ? inundation.addTo(map) : map.removeLayer(inundation);
  if (pathways) toggles.pathways ? pathways.addTo(map) : map.removeLayer(pathways);
  for (const k of ["assets", "roads", "routes"]) toggles[k] ? layers[k].addTo(map) : map.removeLayer(layers[k]);
  if (S.sim) styleAssets();
}

// Earth Engine tile layers (only when Earth Engine is connected on the server)
let eeLayers = {};
export async function loadEeTiles(tenantId) {
  try {
    const r = await fetch(`/api/gee/tiles/${tenantId}`).then((x) => x.json());
    Object.values(eeLayers).forEach((l) => map.removeLayer(l));
    eeLayers = {};
    const el = document.getElementById("maptools");
    el.querySelectorAll(".ee-row").forEach((n) => n.remove());
    if (!r.available) return;
    for (const [id, v] of Object.entries(r.layers)) {
      const layer = L.tileLayer(v.url, { opacity: 0.65, attribution: v.attribution, maxZoom: 18 });
      eeLayers[id] = layer;
      const lab = document.createElement("label");
      lab.className = "ee-row";
      lab.innerHTML = `<input type="checkbox"> ${v.label.replace(/</g, "&lt;")}`;
      lab.querySelector("input").addEventListener("change", (e) => (e.target.checked ? layer.addTo(map) : map.removeLayer(layer)));
      el.append(lab);
    }
  } catch { /* Earth Engine tiles are optional */ }
}

export function fitTenant() {
  const [s, w, n, e] = S.tenant.bbox;
  map.fitBounds([[s, w], [n, e]], { padding: [10, 10] });
}

export function renderSim() {
  const sim = S.sim;
  for (const k of Object.keys(layers)) layers[k].clearLayers();
  markers = {};
  if (inundation) { map.removeLayer(inundation); inundation = null; }
  if (pathways) { map.removeLayer(pathways); pathways = null; }
  const bounds = sim.layers.bounds;
  inundation = L.imageOverlay(sim.layers.inundation, bounds, { opacity: 0.75, interactive: false });
  pathways = L.imageOverlay(sim.layers.pathways, bounds, { opacity: 0.85, interactive: false });
  applyToggles();

  // storm track (observed solid, whole track dashed) + fixes
  const pts = sim.storm.track.map((f) => [f.lat, f.lon]);
  L.polyline(pts, { color: "#38bdf8", weight: 3, dashArray: "8 6", opacity: 0.9 }).addTo(layers.track);
  sim.storm.track.forEach((f) => L.circleMarker([f.lat, f.lon], { radius: 3, color: "#7dd3fc", weight: 1, fillOpacity: 1 })
    .bindTooltip(`${new Date(f.t).toUTCString().slice(5, 22)} UTC${f.vmax_kt ? ` - ${Math.round(f.vmax_kt)} kt` : ""}`).addTo(layers.track));
  L.circleMarker([sim.tenant.focus.lat, sim.tenant.focus.lon], { radius: 6, color: "#fff", weight: 2, fillColor: "#0ea5e9", fillOpacity: 1 })
    .bindTooltip(`Focus: ${esc(sim.tenant.focus.label)}`).addTo(layers.track);

  // coastal sectors with modelled surge
  sim.sectors.forEach((s) => L.circleMarker([s.lat, s.lon], { radius: 5, color: "#a5b4fc", fillColor: "#312e81", fillOpacity: 1, weight: 2 })
    .bindPopup(`<b>Coast sector ${esc(s.id)}</b><br>Surge ${num(s.surge_m, 2)} m (range ${num(s.surge_min_m, 2)}-${num(s.surge_max_m, 2)} m over 9 scenarios)<br>Peak ${esc(relLabel(s.peak_h))} = ${esc(clockAt(sim, S.tenant, s.peak_h))}<br><small>${esc(s.shelf)}<br>Screening-level; official surge guidance is IMD/INCOIS.</small>`)
    .addTo(layers.sectors));

  // assets
  for (const a of sim.assets) {
    const m = L.marker([a.lat, a.lon], { icon: iconFor(a, false), riseOnHover: true, status: a.status }).bindPopup(assetPopup(a));
    markers[a.id] = { m, a };
  }
  styleAssets();
  // affected roads
  L.geoJSON(sim.roads_geojson, { style: (f) => ({ color: f.properties.status === "cut" ? "#ef4444" : "#f97316", weight: f.properties.status === "cut" ? 5 : 3, opacity: 0.8 }),
    onEachFeature: (f, l) => l.bindTooltip(`${esc(f.properties.name || f.properties.highway)} - ${esc(STATUS_LABEL[f.properties.status] || f.properties.status)}`) }).addTo(layers.roads);
  // evacuation routes
  sim.evacuation.routes.filter((r) => r.status === "route" && r.coords).forEach((r) => {
    L.polyline(r.coords, { color: "#22c55e", weight: 3, opacity: 0.85 })
      .bindTooltip(`${esc(r.origin)} → ${esc(r.shelter)}: ${num(r.minutes, 0)} min` + (r.depart_by_h != null ? ` - leave before ${esc(clockAt(sim, S.tenant, r.depart_by_h))}` : "")).addTo(layers.routes);
  });
  sim.evacuation.routes.filter((r) => r.status !== "route" && r.lat).forEach((r) => {
    L.circleMarker([r.lat, r.lon], { radius: 6, color: "#ef4444", fillColor: "#7f1d1d", fillOpacity: 0.9, weight: 2 })
      .bindTooltip(`${esc(r.origin)}: no flood-safe route (${esc(r.status.replace("_", " "))}) - shelter in place / request assistance`).addTo(layers.routes);
  });
  setHour(S.hour);
}

function iconFor(a, future) {
  return L.divIcon({ className: "", html: `<div class="asset-icon ${a.status}${future ? " future" : ""}" title="${esc(a.name)}">${GLYPH[a.kind] || "•"}</div>`, iconSize: [22, 22], iconAnchor: [11, 11] });
}

function assetPopup(a) {
  const sim = S.sim;
  return `<b>${esc(a.name)}</b><br>${esc(a.kind)} ${statusPill(a.status)}${a.kind === "shelter" ? (a.usable ? " usable" : " NOT usable") : ""}
    <br>Peak wind ${num(a.peak_wind_kmh)} km/h at ${esc(clockAt(sim, S.tenant, a.peak_wind_h))}
    <br>Surge depth ${num(a.surge_depth_m, 1)} m - rain 24h ${num(a.rain24_mm)} mm (${esc(a.rain_class)})
    <br>First impact: ${esc(clockAt(sim, S.tenant, a.first_impact_h))}
    ${a.scenario_hits !== undefined ? `<br>Hit in ${a.scenario_hits} of 9 what-if scenarios` : ""}
    <ul style="margin:4px 0 0 16px;padding:0">${a.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`;
}

export function styleAssets() {
  // assets whose first impact is still in the future at the event clock are drawn faded
  for (const { m, a } of Object.values(markers)) {
    const hit = a.status !== "ok" && a.first_impact_h !== null && a.first_impact_h <= S.hour;
    const future = a.status !== "ok" && !hit;
    const show = toggles.assets && (a.status !== "ok" || a.kind === "hospital") && (toggles.upcoming || !future)
      && (a.kind !== "shelter" || a.props?.designated || toggles.candidates || a.usable === false);
    if (show) { if (!layers.assets.hasLayer(m)) layers.assets.addLayer(m); m.setIcon(iconFor(a, future)); }
    else if (layers.assets.hasLayer(m)) layers.assets.removeLayer(m);
  }
}

export function setHour(hr) {
  S.hour = hr;
  if (!S.sim) return;
  const tl = S.sim.timeline;
  if (!tl.length) return;
  const c = tl.reduce((best, x) => (Math.abs(x.h - hr) < Math.abs(best.h - hr) ? x : best), tl[0]);
  if (stormMarker) map.removeLayer(stormMarker);
  stormMarker = L.marker([c.lat, c.lon], { icon: L.divIcon({ className: "", html: '<div class="storm-icon">🌀</div>', iconSize: [30, 30], iconAnchor: [15, 15] }), zIndexOffset: 1000 })
    .bindTooltip(`${esc(S.sim.storm.name)} at ${esc(clockAt(S.sim, S.tenant, c.h))}: ${c.vmax_kt ? Math.round(c.vmax_kt) + " kt" : "-"}`).addTo(map);
  styleAssets();
  emit("hour", { hour: hr, point: c });
}

export function focusAsset(id) {
  const rec = markers[id];
  if (!rec) return;
  if (!layers.assets.hasLayer(rec.m)) layers.assets.addLayer(rec.m);
  // the marker may sit inside a cluster: zoom until it is visible, then open its popup
  layers.assets.zoomToShowLayer(rec.m, () => rec.m.openPopup());
}

export function focusLatLng(lat, lon, zoom = 14) { map.setView([lat, lon], zoom); }
export function invalidate() { map && map.invalidateSize(); }
