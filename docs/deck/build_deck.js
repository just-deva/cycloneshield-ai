// CycloneShield AI - pitch deck (12 slides). Academic style: white ground, serif headings, restrained palette,
// content carried by tables, diagrams and real screenshots.
// Build:  npm install pptxgenjs && node build_deck.js [out.pptx] [--url https://...]
const pptxgen = require("pptxgenjs");
const path = require("path");

const REPO = process.env.REPO || path.resolve(__dirname, "..", "..");   // repository root (screenshots live in docs/images)
const OUT = process.argv[2] && !process.argv[2].startsWith("--") ? process.argv[2] : "CycloneShield_AI_Pitch_Deck.pptx";
const urlIdx = process.argv.indexOf("--url");
const LIVE_URL = urlIdx > 0 ? process.argv[urlIdx + 1] : null;

const C = { ink: "16233A", body: "27303C", muted: "5B6675", rule: "C5CDD6", tint: "EAF0F5", tint2: "F4F6F8", blue: "1E5F7A", rust: "9E3F1C", white: "FFFFFF" };
const F = { head: "Cambria", body: "Calibri" };
const MX = 0.6, CW = 12.13; // left margin, content width (slide is 13.333 x 7.5 in)
const TOP = 1.85, TOP_ONE = 1.5;           // content starts here on every slide that has a two-line title

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "CycloneShield AI - asset-level cyclone impact forecasting and advisory dispatch";
pres.subject = "Build with AI: Code for Communities, Second Edition - Track 05";

pres.defineSlideMaster({
  title: "BASE",
  background: { color: C.white },
  objects: [
    { text: { text: "CycloneShield AI   |   Track 05: Track-Based Cyclone Impact & Infrastructure Vulnerability Forecaster", options: { x: MX, y: 7.03, w: 10, h: 0.28, fontFace: F.body, fontSize: 10, color: C.muted, margin: 0, isTextBox: true } } },
  ],
  slideNumber: { x: 11.6, y: 7.03, w: 1.13, h: 0.28, fontFace: F.body, fontSize: 10, color: C.muted, align: "right" },
});

// ---------- helpers ----------
function head(slide, section, title) {
  slide.addText(section, { x: MX, y: 0.38, w: 8, h: 0.3, fontFace: F.body, fontSize: 12, color: C.blue, bold: true, margin: 0, isTextBox: true });
  slide.addText(title, { x: MX, y: 0.7, w: CW, h: 1.0, fontFace: F.head, fontSize: 28, bold: true, color: C.ink, margin: 0, valign: "top", isTextBox: true });
  return title.length <= 64 ? TOP_ONE : TOP;   // one-line titles leave more room
}
const cell = (text, o = {}) => ({ text, options: { fontFace: F.body, fontSize: 14, color: C.body, valign: "top", margin: [4, 8, 4, 0], ...o } });
const hcell = (text, o = {}) => cell(text, { bold: true, color: C.ink, fontSize: 14, border: [{ type: "none" }, { type: "none" }, { type: "solid", pt: 1.25, color: C.ink }, { type: "none" }], ...o });
const rcell = (text, o = {}) => cell(text, { border: [{ type: "none" }, { type: "none" }, { type: "solid", pt: 0.5, color: C.rule }, { type: "none" }], ...o });
function table(slide, rows, x, y, w, colW, opts = {}) {
  slide.addTable(rows, { x, y, w, colW, rowH: opts.rowH, autoPage: false, ...opts.extra });
}
function bullets(slide, items, x, y, w, h, size = 16, gap = 8) {
  slide.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 16 }, breakLine: i < items.length - 1, paraSpaceAfter: gap } })),
    { x, y, w, h, fontFace: F.body, fontSize: size, color: C.body, valign: "top", margin: 0, isTextBox: true });
}
function label(slide, text, x, y, w) {
  slide.addText(text, { x, y, w, h: 0.32, fontFace: F.head, fontSize: 18, bold: true, color: C.ink, margin: 0, isTextBox: true });
}
function caption(slide, text, x, y, w, h = 0.5) {
  slide.addText(text, { x, y, w, h, fontFace: F.body, fontSize: 12, italic: false, color: C.muted, margin: 0, valign: "top", isTextBox: true });
}
function box(slide, x, y, w, h, text, o = {}) {
  slide.addText(text, {
    shape: pres.shapes.RECTANGLE, x, y, w, h, fontFace: F.body, fontSize: o.size || 14, color: o.color || C.ink, bold: !!o.bold, align: o.align || "center", valign: "middle",
    fill: { color: o.fill || C.white }, line: { color: o.line || C.blue, width: o.lw || 1 }, margin: [4, 6, 4, 6],
  });
}
function arrow(slide, x1, y1, x2, y2, color = C.muted) {
  slide.addShape(pres.shapes.LINE, { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), flipH: x2 < x1, flipV: y2 < y1, line: { color, width: 1.25, endArrowType: "triangle" } });
}

// =====================================================================
// 1. Title
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  s.addText("CycloneShield AI", { x: MX, y: 1.0, w: CW, h: 0.95, fontFace: F.head, fontSize: 48, bold: true, color: C.ink, margin: 0, isTextBox: true });
  s.addText("Asset-level cyclone impact forecasting and advisory dispatch for disaster-management authorities", { x: MX, y: 2.0, w: 10.6, h: 0.95, fontFace: F.head, fontSize: 24, color: C.ink, margin: 0, valign: "top", isTextBox: true });
  s.addText([
    { text: "Abstract. ", options: { bold: true, color: C.ink } },
    { text: "National early-warning systems now give days of notice of a tropical cyclone, yet turning a forecast track into asset-level action (which hospital, substation or road is affected, when, and who must act) remains largely manual. CycloneShield AI is a decision-support layer that sits downstream of the India Meteorological Department (IMD). A deterministic hazard-and-exposure engine computes every number; Gemini 3.7 Flash reads official bulletins, drafts validated multilingual advisories and answers officers' questions. Advisories are dispatched only after human approval and are recorded in a tamper-evident audit log." },
  ], { x: MX, y: 3.25, w: 10.6, h: 2.3, fontFace: F.body, fontSize: 16, color: C.body, margin: 0, valign: "top", paraSpaceAfter: 6, isTextBox: true });
  s.addText([
    { text: "Build with AI: Code for Communities, Second Edition (Google Cloud x Hack2skill)", options: { breakLine: true, bold: true, color: C.ink } },
    { text: "Track 05, Resilience: Track-Based Cyclone Impact & Infrastructure Vulnerability Forecaster", options: { breakLine: true } },
    { text: "Source code: github.com/just-deva/cycloneshield-ai (branch code-for-communities-2026)" + (LIVE_URL ? "     Live prototype: " + LIVE_URL : "") },
  ], { x: MX, y: 5.75, w: CW, h: 1.05, fontFace: F.body, fontSize: 14, color: C.muted, margin: 0, valign: "top", paraSpaceAfter: 3, isTextBox: true });
  s.addNotes("Opening. State the one-sentence claim: we do not forecast cyclones; IMD does. We convert its forecast into asset-level, time-stamped action for a district, with every number computed by code and every message approved by a person. Mention the deliverables: working prototype, source code, demo video, deck.");
}

// =====================================================================
// 2. Motivation
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "1. Motivation", "Early warning saves lives, but the last step from forecast to action is still manual");
  label(s, "Outcomes in Odisha over three storms", MX, T, 7.0);
  table(s, [
    [hcell("Event"), hcell("People evacuated"), hcell("Deaths")],
    [rcell("1999 Super Cyclone"), rcell("not comparable"), rcell("about 10,000")],
    [rcell("Phailin, 2013"), rcell("about 1 million"), rcell("double digits")],
    [rcell("Fani, 2019"), rcell("about 1.2 million"), rcell("double digits (16 to 64)")],
  ], MX, T + 0.45, 7.0, [2.5, 2.1, 2.4], { rowH: [0.42, 0.45, 0.45, 0.45] });
  caption(s, "Sources: World Bank (2023); UN ESCAP. Figures are rounded and reported tolls differ by source. The Global Commission on Adaptation (2019) estimates that 24 hours of warning reduce damage by about 30%.", MX, 4.35, 7.0, 0.7);
  bullets(s, [
    "Forecasts are accurate and widely disseminated; the bottleneck has moved to acting on them.",
    "Acting before landfall (evacuation planning, hardening, pre-arranged funds) protects lives and livelihoods; acting afterwards is recovery.",
  ], MX, 5.3, 7.0, 1.5, 16, 8);
  label(s, "Questions asked at T minus 72 h", 8.05, T, 4.7);
  s.addText([
    "Which hospitals lose power or access, and when?",
    "Which substations face flooding or destructive wind?",
    "Which roads and evacuation routes remain usable?",
    "Which shelters are safe, and by what time must people leave?",
    "Who must be told what, in which language, and who approves it?",
    "Should pre-arranged relief funds be released before landfall?",
  ].map((t, i, a) => ({ text: t, options: { bullet: { type: "number" }, breakLine: i < a.length - 1, paraSpaceAfter: 9 } })),
    { x: 8.05, y: T + 0.5, w: 4.68, h: 4.4, fontFace: F.body, fontSize: 16, color: C.body, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Odisha is the strongest evidence that early warning works: about 10,000 deaths in 1999 against double-digit tolls in 2013 and 2019 with around a million people evacuated each time. Fani tolls vary by source (16 to 64), so we say double digits. The point of the slide is the right-hand list: these are the questions officers still answer largely by hand.");
}

// =====================================================================
// 3. Gap and positioning
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "2. Positioning", "We complement India's warning chain at the asset level rather than replace any part of it");
  const bh = 0.85, bw = 3.5, gap = 0.82;
  const xs = [MX, MX + bw + gap, MX + 2 * (bw + gap)];
  // existing chain
  s.addText("Existing national chain", { x: MX, y: T, w: 5, h: 0.26, fontFace: F.body, fontSize: 13, color: C.muted, bold: true, margin: 0, isTextBox: true });
  const y1 = T + 0.32;
  box(s, xs[0], y1, bw, bh, "IMD: forecast track and four-stage cyclone warnings", { line: C.muted });
  box(s, xs[1], y1, bw, bh, "IMD / NDMA Web-DCRA: district-level hazard and risk atlas", { line: C.muted });
  box(s, xs[2], y1, bw, bh, "NDMA SACHET: Common Alerting Protocol alerts through SDMAs", { line: C.muted });
  arrow(s, xs[0] + bw, y1 + bh / 2, xs[1], y1 + bh / 2);
  arrow(s, xs[1] + bw, y1 + bh / 2, xs[2], y1 + bh / 2);
  // our layer
  const yt2 = y1 + bh + 0.3;
  s.addText("Proposed decision-support layer", { x: MX, y: yt2, w: 5, h: 0.26, fontFace: F.body, fontSize: 13, color: C.blue, bold: true, margin: 0, isTextBox: true });
  const y2 = yt2 + 0.32;
  box(s, xs[0], y2, bw, bh, "CycloneShield AI: asset-level impact, who-does-what-when, advisory drafts", { fill: C.tint, line: C.blue, lw: 1.75, bold: true });
  box(s, xs[1], y2, bw, bh, "Officer approval (two officers for orange and red)", { line: C.blue });
  box(s, xs[2], y2, bw, bh, "SDMA, DEOC and departments (CAP 1.2, Exercise / Restricted)", { line: C.blue });
  arrow(s, xs[0] + bw, y2 + bh / 2, xs[1], y2 + bh / 2, C.blue);
  arrow(s, xs[1] + bw, y2 + bh / 2, xs[2], y2 + bh / 2, C.blue);
  arrow(s, xs[0] + bw - 0.5, y1 + bh, xs[0] + bw - 0.5, y2, C.blue);
  caption(s, "Publishing into SACHET remains with authorised originators; our CAP output is always marked Exercise and Restricted.", MX, y2 + bh + 0.1, CW, 0.3);
  // text columns
  const yc = y2 + bh + 0.6;
  label(s, "Established", MX, yc, 5.5);
  bullets(s, ["Accurate IMD forecasts and a four-stage warning clock", "A national CAP platform and district hazard atlases"], MX, yc + 0.4, 5.7, 1.0, 15, 4);
  label(s, "Not yet covered at asset level", 6.75, yc, 6.0);
  bullets(s, ["Hour-by-hour exposure of each hospital, substation, road and shelter", "Local-language drafts with an approval trail and a link to anticipatory finance"], 6.75, yc + 0.4, 5.98, 1.0, 15, 4);
  s.addNotes("Be explicit that this is not a competitor to IMD, Web-DCRA or SACHET. We consume the official track and produce CAP files in the SACHET profile, always marked Exercise and Restricted, so an authorised originator could ingest them. The gap we fill is below district level and at the who-does-what-when step.");
}

// =====================================================================
// 4. Solution overview
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "3. Approach", "Five stages turn an official forecast into an approved, audited advisory for the district");
  const steps = [
    ["1  Read", "An IMD bulletin (PDF or image), or a replayed best track, becomes a validated storm track.", "Track, intensity, uncertainty"],
    ["2  Simulate", "Wind, storm surge, sea-connected flooding and rain pathways; nine what-if scenarios.", "Hazard fields and ranges"],
    ["3  Assess", "Hospitals, substations, roads and shelters from OpenStreetMap; flood-aware evacuation routes.", "Per-asset status and time of first impact"],
    ["4  Draft", "Gemini drafts audience-specific advisories from a facts packet; a validator checks every number.", "Validated multilingual drafts"],
    ["5  Approve and dispatch", "Maker-checker approval; CAP 1.2, Telegram with acknowledgement, webhook; hash-chained audit log.", "Delivered, acknowledged, auditable"],
  ];
  const bw = 2.2, gap = 0.28, y = T + 0.1, bhh = 2.5;
  steps.forEach((st, i) => {
    const x = MX + i * (bw + gap);
    s.addText([
      { text: st[0], options: { fontFace: F.head, fontSize: 18, bold: true, color: C.ink, breakLine: true, paraSpaceAfter: 8 } },
      { text: st[1], options: { fontFace: F.body, fontSize: 15, color: C.body } },
    ], { shape: pres.shapes.RECTANGLE, x, y, w: bw, h: bhh, fill: { color: i === 3 ? C.tint : C.white }, line: { color: C.blue, width: 1 }, margin: [10, 10, 8, 10], valign: "top" });
    if (i < steps.length - 1) arrow(s, x + bw, y + bhh / 2, x + bw + gap, y + bhh / 2);
    s.addText([
      { text: "Output", options: { bold: true, color: C.muted, fontSize: 12, breakLine: true } },
      { text: st[2], options: { color: C.ink, fontSize: 14 } },
    ], { x, y: y + bhh + 0.15, w: bw, h: 0.9, fontFace: F.body, margin: 0, valign: "top", isTextBox: true });
  });
  s.addText([
    { text: "Design principle. ", options: { bold: true, color: C.ink } },
    { text: "Numbers come from code; words come from the model. The model has no dispatch capability, and severity is set by rules from IMD's own warning clock (Watch 72 h, Alert 48 h, Warning 24 h, Outlook 12 h) combined with the modelled hazard." },
  ], { x: MX, y: 5.95, w: CW, h: 0.9, fontFace: F.body, fontSize: 16, color: C.body, margin: 0, valign: "top", isTextBox: true });
  s.addNotes("Walk the five stages left to right. Stress stage 4: Gemini only writes; the validator rejects any number that is not in the computed facts packet. Severity is decided by rules, the model never sets it, and it can never dispatch.");
}

// =====================================================================
// 5. Architecture
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "4. System architecture", "A layered design keeps computation deterministic and confines the language model to reading and writing");
  const labelW = 2.25, bx0 = MX + labelW + 0.2, bw = 2.3, gapx = 0.13, bh = 0.7, gapy = 0.18, y0 = T;
  const bands = [
    ["Inputs", ["IMD bulletin (PDF, image)", "Replayed best tracks (JTWC)", "OpenStreetMap infrastructure", "Terrain and Earth Engine layers"], C.white],
    ["Deterministic analysis", ["Hazard engine: wind, surge, flooding, rain", "Asset impact and evacuation routing", "Nine-scenario ensemble", "Finance trigger monitor"], C.white],
    ["Language model (Gemini 3.7 Flash)", ["Bulletin reader", "Advisory writer", "Officer copilot (function calling)", "Validator (code): numbers, places, injection"], C.tint],
    ["Control and delivery", ["Maker-checker approval", "CAP 1.2 (Exercise, Restricted)", "Telegram with acknowledgement", "Webhook to DEOC receiver"], C.white],
    ["Trust", ["Hash-chained audit log", "AI-call trace", "Cache of real Gemini outputs", "Methodology and calibration panel"], C.white],
  ];
  bands.forEach((b, r) => {
    const y = y0 + r * (bh + gapy);
    s.addText(b[0], { x: MX, y, w: labelW, h: bh, fontFace: F.head, fontSize: 15, bold: true, color: C.ink, margin: 0, valign: "middle", isTextBox: true });
    b[1].forEach((t, c) => box(s, bx0 + c * (bw + gapx), y, bw, bh, t, { fill: b[2], size: 13 }));
  });
  caption(s, "Figure 1. Layered architecture, read top to bottom; the shaded band is the only place a language model is involved. One FastAPI service serves the API and the single-page interface from one Cloud Run container; every dependency (Gemini, Earth Engine, Telegram) has a labelled degraded mode.", MX, 6.3, CW, 0.6);
  s.addNotes("Read the figure top to bottom. The shaded band is the only place a language model is involved, and even there the validator is ordinary code. Trust is a layer of its own: the audit chain, the AI-call trace and the cache of real outputs are visible in the interface.");
}

// =====================================================================
// 6. Google AI
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "5. Google AI and Google Cloud", "Gemini performs three distinct jobs, and each is bounded by a deterministic safeguard");
  const R = (a, b, c, d) => [rcell(a, { bold: true, color: C.ink }), rcell(b), rcell(c), rcell(d)];
  table(s, [
    [hcell("Component"), hcell("Google product"), hcell("Function"), hcell("Safeguard")],
    R("Bulletin reader", "Gemini 3.7 Flash: multimodal input, structured output", "Converts an IMD bulletin (PDF or image) into a validated track and intensity", "JSON schema; range and time-order checks; source shown beside extraction"),
    R("Advisory writer", "Gemini 3.7 Flash: structured output", "Drafts audience-specific advisories and translations (Telugu, Odia, Hindi, Bengali, Tamil, Vietnamese)", "Tier set by rules; numbers and names validated; labelled template fallback"),
    R("Officer copilot", "Gemini 3.7 Flash: function calling", "Answers questions by calling seven analysis tools on the current simulation", "No dispatch tool; numbers checked against tool output"),
    R("Geospatial data", "Google Earth Engine", "NOAA GFS rain; GHSL population and Open Buildings in the flood zone; map tiles", "Fails soft to open terrain tiles"),
    R("Hosting", "Cloud Run, Cloud Build, Secret Manager", "One container serves the API and the interface", "Configurable model ID; fallback chain; cached real outputs"),
  ], MX, T, CW, [1.9, 2.75, 4.0, 3.48], { rowH: [0.4, 0.8, 0.8, 0.6, 0.8, 0.6] });
  s.addText([
    { text: "Operational detail. ", options: { bold: true, color: C.ink } },
    { text: "The thinking level is set explicitly (Gemini 3 defaults to high, and MINIMAL is unsupported on 3.7 Flash); temperature is left at its default; a circuit breaker skips a model that returns quota or overload errors; every call appears in an in-app trace." },
  ], { x: MX, y: 6.2, w: CW, h: 0.7, fontFace: F.body, fontSize: 14, color: C.body, margin: 0, valign: "top", isTextBox: true });
  s.addNotes("The track names Gemini 3.7 Flash, so it is the primary model and the ID is configurable. Bulletin reading is the multimodal element: IMD publishes only PDFs and images. Earth Engine was tested live: GFS rain, three tile layers, and 1,327 people and 318 buildings inside the modelled Hudhud flood zone.");
}

// =====================================================================
// 7. Methods
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "6. Methodology", "Every quantity in an advisory is computed by code from cited, transparent methods, never generated by the model");
  const R = (a, b, c) => [rcell(a, { bold: true, color: C.ink }), rcell(b), rcell(c)];
  table(s, [
    [hcell("Module"), hcell("Method"), hcell("Basis")],
    R("Wind field", "Parametric radial profile; surface reduction 0.85; 20-degree inflow; translation asymmetry", "Holland (1980)"),
    R("Surge and flooding", "Inverse barometer, wind set-up and tide with a per-coast multiplier; sea-connected bathtub with 0.2 m per km inland attenuation", "Steady-state balance; Pielke and Pielke (1997)"),
    R("Rain and pathways", "R-CLIPER rain prior; priority-flood basins; D8 flow accumulation", "Tuleya et al. (2007); Barnes et al. (2014)"),
    R("Asset status", "Explicit thresholds: gale 62, damaging 89, destructive 118 km/h; 0.3 m road passability", "IMD classes; Pregnolato et al. (2017)"),
    R("Expected loss", "Sigmoid loss ratio, half-damage wind 58.7 m/s (Indian Ocean)", "Emanuel (2011); Eberenz et al. (2021)"),
    R("Uncertainty", "Nine scenarios (track \u00b140 km by intensity \u00b110 kt); share of scenarios that hit each asset", "Design choice"),
  ], MX, T, CW, [2.0, 6.1, 4.03], { rowH: [0.38, 0.55, 0.55, 0.4, 0.55, 0.4, 0.55] });
  const fo = { fontFace: F.head, fontSize: 15, color: C.ink };
  const sub = (t) => ({ text: t, options: { ...fo, subscript: true } });
  const sup = (t) => ({ text: t, options: { ...fo, superscript: true } });
  const tx = (t, br) => ({ text: t, options: { ...fo, breakLine: !!br } });
  s.addText([
    tx("\u03b7  =  k \u00b7 [ 0.01 \u00b7 (p"), sub("env"), tx(" \u2212 p"), sub("local"), tx(")  +  \u03c4 L / (\u03c1"), sub("w"), tx(" g h) ]  +  tide", true),
    tx("\u03c4  =  \u03c1"), sub("a"), tx(" C"), sub("d"), tx(" U"), sup("2"), tx(",      C"), sub("d"), tx("  =  min [ (0.75 + 0.067 U) \u00b7 10"), sup("\u22123"), tx(",  2.5 \u00b7 10"), sup("\u22123"), tx(" ]"),
  ], { x: MX, y: 5.85, w: CW, h: 0.6, margin: 0, valign: "top", paraSpaceAfter: 3, isTextBox: true });
  caption(s, "Storm-tide budget for a coastal sector (p in hPa; L and h: effective shelf width and mean depth; U: wind component toward land; k: per-coast calibration multiplier).", MX, 6.6, CW, 0.35);
  s.addNotes("Nothing here is a black box. The surge formula is a screening-level budget of the same class as IMD's nomograms; the operational hydrodynamic models (ADCIRC at INCOIS) are out of scope. The expected-loss sigmoid describes an aggregate fraction of exposed value, not the failure probability of any one building.");
}

// =====================================================================
// 8. Validation and limitations
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "7. Verification and limitations", "What is verified, what is calibrated, and what is not claimed");
  label(s, "Automated verification", MX, T, 5.6);
  bullets(s, [
    "55 automated tests cover parsers, physics benchmarks, the API, approval rules, CAP safety fields, audit tamper detection and cache integrity.",
    "A validator checks each draft: numbers must exist in the model output (digits of any script) and names must exist; no URLs, phone numbers or injected instructions; uncertainty is required.",
    "Severity is rule-based; orange and red need two distinct approvers.",
  ], MX, T + 0.45, 5.7, 3.3, 15, 8);
  label(s, "Surge calibration (in-sample fit)", 6.75, T, 6.0);
  table(s, [
    [hcell("Coast sector"), hcell("Modelled (m)"), hcell("Nine-scenario range (m)"), hcell("Observed (m)")],
    [rcell("Visakhapatnam port"), rcell("1.27"), rcell("0.41 to 1.46"), rcell("1.2 to 1.4")],
    [rcell("Puri beach"), rcell("1.53"), rcell("0.13 to 1.71"), rcell("about 1.5")],
  ], 6.75, T + 0.45, 5.98, [1.95, 1.2, 1.7, 1.13], { rowH: [0.6, 0.42, 0.42] });
  caption(s, "Observations: Hudhud 2014 (Visakhapatnam tide gauge, IMD RSMC report); Fani 2019 (media-reported; INCOIS guidance had been up to about 4 m). The multipliers k = 2.0 and k = 0.65 were fitted to these events, so agreement is by construction and is not a validation. Vietnam is uncalibrated.", 6.75, T + 2.1, 5.98, 1.3);
  s.addText([
    { text: "Not claimed. ", options: { bold: true, color: C.rust } },
    { text: "An official forecast; validated surge accuracy; flooding in built-up areas (the surface-model DEM is biased high, so it is under-predicted); rain for stalled or monsoon-interacting storms (R-CLIPER has no orography); distribution-pole outages or designated-shelter capacity (sparse in OpenStreetMap)." },
  ], { x: MX, y: 5.35, w: CW, h: 1.1, fontFace: F.body, fontSize: 16, color: C.body, margin: 0, valign: "top", isTextBox: true });
  s.addNotes("Be candid: one coast needs k of 2.0 and the other 0.65, which tells us the hand-set shelf geometry is the weakest part. That is why the interface labels surge as screening-level and shows this table. Out-of-sample validation against Sentinel-1 flood extents is the first item of future work.");
}

// =====================================================================
// 9. Prototype in use
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "8. Prototype", "Cyclone Hudhud replayed on today's Visakhapatnam infrastructure");
  const iw = 5.95, ih = iw * (482 / 800), gx = 0.23;
  s.addImage({ path: path.join(REPO, "docs/images/overview.jpg"), x: MX, y: T, w: iw, h: ih });
  s.addImage({ path: path.join(REPO, "docs/images/assets.jpg"), x: MX + iw + gx, y: T, w: iw, h: ih });
  const cy = T + ih + 0.1;
  caption(s, "Figure 2a. Overview: warning tier set by rule (orange at T minus 24 h), 206 km/h peak wind (JTWC 1-minute basis), 271 hospitals and 88 substations assessed, surge 0.6 to 2.0 m across nine scenarios, 14.5 km\u00b2 flooded.", MX, cy, iw, 0.75);
  caption(s, "Figure 2b. \"What gets hit, and when\": status, hazards, time of first impact and the share of scenarios (k of 9) in which each asset is hit.", MX + iw + gx, cy, iw, 0.75);
  s.addText([
    { text: "Also demonstrated: ", options: { bold: true, color: C.ink } },
    { text: "24 of 30 localities have a flood-safe route to a shelter with a latest safe departure time; a near-miss storm (Montha 2025) stays at Monitor, so no false alarm is raised; the same pipeline runs for Odisha and Vietnam." },
  ], { x: MX, y: 5.95, w: CW, h: 0.75, fontFace: F.body, fontSize: 16, color: C.body, margin: 0, valign: "top", isTextBox: true });
  s.addNotes("Screenshots are from the running prototype. Hudhud made landfall at Visakhapatnam in October 2014; we replay its track over current OpenStreetMap infrastructure, which is a what-if rather than a hindcast. Winds are on the JTWC one-minute basis, a few percent above IMD's three-minute values.");
}

// =====================================================================
// 10. Track 05 coverage
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "9. Coverage of the challenge", "Each element of the Track 05 brief maps to a working component");
  const st = (t) => rcell(t, { bold: true, color: t.startsWith("Partial") ? C.rust : C.ink });
  const R = (a, b, c) => [rcell(a, { bold: true, color: C.ink }), rcell(b), st(c)];
  table(s, [
    [hcell("Requirement"), hcell("Implementation"), hcell("Status")],
    R("Simulate cyclone storm surges", "Storm-tide budget per coastal sector; sea-connected flooding; nine scenarios", "Implemented (screening-level)"),
    R("Predict rainfall damage pathways", "R-CLIPER prior; waterlogging basins and runoff corridors; onset time per asset", "Implemented"),
    R("Map exposure: power grid", "OpenStreetMap substations and lines with wind and flood status", "Implemented"),
    R("Map exposure: arterial roads", "Road graph; cut and waterlogged segments; routes with depart-by times", "Implemented"),
    R("Map exposure: medical shelters", "Hospitals and candidate shelters; usable or not", "Implemented (shelter registers needed)"),
    R("Automated advisory dispatch", "Approval workflow; CAP 1.2, Telegram with acknowledgement, webhook", "Implemented (SMS, Cell Broadcast simulated)"),
    R("Earth Engine and real-time meteorology", "GFS forecast rain, GHSL, Open Buildings, MERIT Hydro tiles", "Implemented; live cyclone feed on roadmap"),
    R("Gemini 3.7 Flash multimodal reasoning", "Bulletin reader, advisory writer, officer copilot", "Implemented"),
    R("Parametric insurance liquidity", "Stage-keyed trigger tiers and release memo; no funds move", "Implemented (illustrative)"),
  ], MX, T, CW, [3.45, 5.25, 3.43], { rowH: [0.4, 0.5, 0.5, 0.45, 0.45, 0.45, 0.5, 0.5, 0.45, 0.45] });
  s.addNotes("Status is stated conservatively. SMS and Cell Broadcast are government or telecom gated and are simulated and labelled. Live cyclone feeds are not wired: the inputs are replays and bulletins; live NOAA GFS rain is already read through Earth Engine.");
}

// =====================================================================
// 11. Scale and deployability
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "10. Scalability and deployability", "A new region is a configuration file; a pilot can start in shadow mode within weeks");
  label(s, "Regions loaded in the prototype", MX, T, 6.5);
  table(s, [
    [hcell("Region"), hcell("Replay"), hcell("Infrastructure (OpenStreetMap)")],
    [rcell("Andhra Pradesh, Visakhapatnam"), rcell("Hudhud 2014"), rcell("271 hospitals, 88 substations, 3,110 road segments")],
    [rcell("Odisha, Puri"), rcell("Fani 2019"), rcell("22 hospitals, 4 substations; roads pending")],
    [rcell("Vietnam, Hai Phong"), rcell("Yagi 2024"), rcell("37 substations, 2,943 road segments; hospitals pending")],
  ], MX, T + 0.45, 6.4, [2.1, 1.3, 3.0], { rowH: [0.4, 0.6, 0.6, 0.6] });
  bullets(s, [
    "The core model uses only global inputs, so one code base serves the North Indian Ocean and the West Pacific; a new region is one JSON file and two data scripts.",
    "Rollout follows NCRMP Category I states first: Andhra Pradesh, Gujarat, Odisha, Tamil Nadu, West Bengal.",
  ], MX, 4.75, 6.4, 1.3, 14, 6);
  label(s, "Proposed pilot pathway", 7.35, T, 5.4);
  table(s, [
    [hcell("Phase"), hcell("Scope")],
    [rcell("Week 1"), rcell("Shadow mode with one SDMA on Visakhapatnam and other high-proneness districts")],
    [rcell("Weeks 2 to 3"), rcell("Second state: new region file, language pack, one data run")],
    [rcell("Week 4"), rcell("CAP feed to a state EOC or the SACHET test channel, via NDMA")],
    [rcell("Later"), rcell("NCRMP Category II states; BRICS and APAC partners through the same adapters")],
  ], 7.35, T + 0.45, 5.38, [1.35, 4.03], { rowH: [0.4, 0.75, 0.6, 0.6, 0.75] });
  s.addText([
    { text: "Constraints stated openly. ", options: { bold: true, color: C.rust } },
    { text: "Earth Engine is free for non-commercial use only, so a state pilot would need a paid plan. Gemini 3.7 Flash introductory pricing ends on 31 December 2026. State and audit data live in files; production would move them to Firestore and a retention-locked bucket." },
  ], { x: MX, y: 6.2, w: CW, h: 0.7, fontFace: F.body, fontSize: 14, color: C.body, margin: 0, valign: "top", isTextBox: true });
  s.addNotes("Regions differ in data richness: OpenStreetMap coverage is dense around Visakhapatnam and thinner for Odisha and Hai Phong, which the table shows rather than hides. The tenant mechanism is the scalability claim; the pilot path is a proposal, not a commitment from any authority.");
}

// =====================================================================
// 12. Impact, future work, references
// =====================================================================
{
  const s = pres.addSlide({ masterName: "BASE" });
  const T = head(s, "11. Impact, future work and references", "Asset-level lead time bridges the gap between warning and action");
  label(s, "Expected impact", MX, T, 6.0);
  bullets(s, [
    "Converts a district-level warning into hospital-, substation- and road-level times of first impact.",
    "Odisha's fall from about 10,000 deaths (1999) to double digits (2013, 2019) shows the value of acting before landfall.",
    "Relevant to 13 coastal States and Union Territories and about 84 coastal districts (NCRMP).",
  ], MX, T + 0.4, 6.05, 1.9, 14, 6);
  label(s, "Future work", MX, 4.05, 6.0);
  bullets(s, [
    "Live forecast ingestion with IMD as the authority; NWP rainfall ensembles.",
    "Shelf parameters from bathymetry; out-of-sample validation against Sentinel-1 flood extents.",
    "Designated-shelter registers; Firestore state and a KMS-signed audit chain; SDMA integration through NDMA.",
  ], MX, 4.45, 6.05, 2.3, 14, 6);
  label(s, "References", 7.1, T, 5.6);
  s.addText([
    "Barnes, R., Lehman, C., Mulla, D. (2014). Priority-flood: an optimal depression-filling and watershed-labeling algorithm. Computers & Geosciences 62, 117-127.",
    "Eberenz, S., L\u00fcthi, S., Bresch, D. N. (2021). Regional tropical cyclone impact functions for globally consistent risk assessments. Nat. Hazards Earth Syst. Sci. 21, 393-415.",
    "Emanuel, K. (2011). Global warming effects on U.S. hurricane damage. Weather, Climate, and Society 3, 261-268.",
    "Global Commission on Adaptation (2019). Adapt Now: A Global Call for Leadership on Climate Resilience.",
    "Holland, G. J. (1980). An analytic model of the wind and pressure profiles in hurricanes. Mon. Wea. Rev. 108, 1212-1218.",
    "OASIS (2010). Common Alerting Protocol Version 1.2.",
    "Pielke, R. A., Pielke, R. A. (1997). Hurricanes: Their Nature and Impacts on Society. Wiley.",
    "Pregnolato, M. et al. (2017). The impact of flooding on road transport: a depth-disruption function. Transp. Res. D 55, 67-81.",
    "Tuleya, R. E., DeMaria, M., Kuligowski, R. J. (2007). Evaluation of GFDL and simple statistical model rainfall forecasts for U.S. landfalling tropical storms. Weather and Forecasting 22, 56-70.",
    "World Bank (2023). Odisha's turnaround in disaster management has lessons for the world.",
  ].map((t, i, a) => ({ text: t, options: { breakLine: i < a.length - 1, paraSpaceAfter: 4 } })),
    { x: 7.1, y: T + 0.4, w: 5.63, h: 4.7, fontFace: F.body, fontSize: 11, color: C.body, valign: "top", margin: 0, isTextBox: true });
  s.addNotes("Close by restating the claim and the safeguards: numbers computed by code, every AI output validated, a person approves, everything is logged. Invite questions on calibration and limitations first, since those are the honest weak points.");
}

pres.writeFile({ fileName: OUT }).then((f) => console.log("wrote", f));
