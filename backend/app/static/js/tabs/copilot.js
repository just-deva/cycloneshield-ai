import { S, lead } from "../state.js";
import { api } from "../api.js";
import { esc, h } from "../util.js";

const SUGGEST = [
  "Which hospitals are most at risk and when does it start?",
  "Can people evacuate safely? Which places are stranded?",
  "What is the storm surge range and how sure are we?",
  "Which roads will be cut first?",
  "Draft a hospital advisory in Telugu",
  "How does the surge model work and what are its limits?",
];

export function render(el) {
  if (!S.sim) { el.innerHTML = '<p class="note">No simulation yet.</p>'; return; }
  const gem = S.health?.features?.gemini;
  el.innerHTML = `
    <h2>Officer copilot</h2>
    <p class="note">Gemini answers by <b>calling our analysis tools</b> (assets, roads, evacuation, surge, methodology, advisory drafts). It cannot dispatch anything, and every number in an answer is checked against what the tools returned.</p>
    ${gem ? "" : '<div class="warnbox">GEMINI_API_KEY is not configured on the server, so the copilot is unavailable. Everything else works without it.</div>'}
    <div class="suggest">${SUGGEST.map((q) => `<button class="ghost" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div class="chat" id="chat" style="margin-top:10px"></div>
    <div class="row"><input type="text" id="q" placeholder="Ask in English, Telugu, Hindi ..." style="flex:1" ${gem ? "" : "disabled"}><button id="send" ${gem ? "" : "disabled"}>Ask</button></div>`;
  const chat = el.querySelector("#chat");
  S.chat.forEach((m) => chat.append(bubble(m)));
  const send = async (text) => {
    if (!text.trim()) return;
    el.querySelector("#q").value = "";
    const um = { role: "user", text }; S.chat.push(um); chat.append(bubble(um));
    const pending = h('<div class="msg bot note">Thinking and calling tools...</div>'); chat.append(pending);
    try {
      const r = await api.post("/api/copilot", { sim_id: S.sim.sim_id, lead_h: lead(), question: text, history: S.chat.slice(-8).map((m) => ({ role: m.role, text: m.text })) });
      const bm = { role: "bot", text: r.answer, tools: r.tool_calls, verified: r.numbers_verified, note: r.note, model: r.model, ms: r.latency_ms };
      S.chat.push(bm); pending.replaceWith(bubble(bm));
    } catch (e) { pending.replaceWith(h(`<div class="errbox">${esc(e.message)}</div>`)); }
    chat.scrollTop = chat.scrollHeight;
  };
  el.querySelector("#send").onclick = () => send(el.querySelector("#q").value);
  el.querySelector("#q").onkeydown = (e) => { if (e.key === "Enter") send(e.target.value); };
  el.querySelectorAll("[data-q]").forEach((b) => (b.onclick = () => send(b.dataset.q)));
}

function bubble(m) {
  if (m.role === "user") return h(`<div class="msg user">${esc(m.text)}</div>`);
  const tools = (m.tools || []).map((t) => `<span class="toolchip" title="${esc(JSON.stringify(t.args))}">${esc(t.name)}</span>`).join("");
  return h(`<div class="msg bot">${esc(m.text)}<div style="margin-top:6px">${tools}</div>
    <div class="note">${m.verified ? '<span style="color:#22c55e">✔ numbers verified against tool outputs</span>' : `<span style="color:#f59e0b">⚠ ${esc(m.note || "unverified numbers")}</span>`} - ${esc(m.model || "")} ${m.ms ? m.ms + " ms" : ""}</div></div>`);
}
