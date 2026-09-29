import React from "react";
import { CircleMarker, MapContainer, Marker, Polygon, Polyline, Popup, TileLayer, Tooltip } from "react-leaflet";
import L from "leaflet";

const colors = { Low: "#22c55e", Moderate: "#eab308", High: "#f97316", Critical: "#dc2626" };
const shelterIcon = L.divIcon({ className: "shelter-marker", html: "⌂", iconSize: [28, 28], iconAnchor: [14, 14] });
export default function TrackMap({ scenario, simulation }) {
  if (!scenario || !simulation) return <div className="map-loading">Loading operations map…</div>;
  const riskByWard = Object.fromEntries(simulation.ward_risks.map((risk) => [risk.ward_id, risk]));
  const nodes = Object.fromEntries(scenario.road_network.nodes.map((node) => [node.id, node]));
  const blocked = new Set(simulation.flooded_road_ids);
  return <MapContainer center={[17.6868, 83.2185]} zoom={12} className="map"><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
    {scenario.wards.map((ward) => { const risk = riskByWard[ward.id]; return <Polygon key={ward.id} positions={ward.geojson.coordinates[0].map(([lng, lat]) => [lat, lng])} pathOptions={{ color: colors[risk?.risk_level] || colors.Low, fillOpacity: .28, weight: 2 }}><Tooltip>{ward.name}: {risk?.risk_level}</Tooltip></Polygon>; })}
    {scenario.road_network.edges.map((edge) => { const a = nodes[edge.from], b = nodes[edge.to], closed = blocked.has(edge.id); return <Polyline key={edge.id} positions={[[a.lat, a.lng], [b.lat, b.lng]]} pathOptions={{ color: closed ? "#dc2626" : "#64748b", dashArray: closed ? "7 8" : undefined, weight: closed ? 4 : 2 }}><Tooltip>{edge.name}{closed ? " — blocked" : ""}</Tooltip></Polyline>; })}
    {simulation.routes.filter((item) => item.route).map((item) => <Polyline key={item.ward_id} positions={item.route.coordinates} pathOptions={{ color: "#16a34a", weight: 5 }} />)}
    <Polyline positions={scenario.cyclone_track.map((point) => [point.lat, point.lng])} pathOptions={{ color: "#0ea5e9", dashArray: "10 8", weight: 4 }} />
    <CircleMarker center={[simulation.active_track_point.lat, simulation.active_track_point.lng]} radius={12} pathOptions={{ color: "white", fillColor: "#2563eb", fillOpacity: 1, weight: 3 }}><Popup><b>Cyclone centre</b><br/>{simulation.active_track_point.wind_speed_kmh} km/h</Popup></CircleMarker>
    {scenario.shelters.map((shelter) => <Marker key={shelter.id} position={[shelter.lat, shelter.lng]} icon={shelterIcon}><Popup><b>{shelter.name}</b><br/>{shelter.current_occupancy}/{shelter.capacity} occupied</Popup></Marker>)}</MapContainer>;
}
