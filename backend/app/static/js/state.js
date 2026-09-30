// Shared application state + a tiny event bus. No framework: modules read S and subscribe to events.

export const S = {
  health: null,
  tenants: [],
  storms: [],
  tenant: null,           // tenant object from /api/tenants
  stormId: null,
  sim: null,              // last /api/simulate result
  hour: -24,              // event clock: hours relative to closest approach (T0)
  scenario: { cross_track_km: 0, delta_kt: 0, tide_m: null },
  severity: null,         // rule-based tier at the current lead time
  actor: "Duty officer (maker)",
  role: "district_collector",
  language: "English",
  activeAdvisory: null,
  chat: [],
  pool: 10,
  bulletinStorms: [],     // storms read by Gemini in this session
};

const listeners = {};
export const on = (evt, fn) => { (listeners[evt] ||= []).push(fn); };
export const emit = (evt, payload) => (listeners[evt] || []).forEach((fn) => fn(payload));

export const lead = () => Math.max(0, -S.hour);
export const ACTORS = ["Duty officer (maker)", "Approver A", "Approver B"];
