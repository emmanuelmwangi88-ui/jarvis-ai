/* ==========================================================================
   Sakura AI — application logic (chat, streaming, tools, voice, palette)
   Depends on: themes.js (window.SakuraTheme, window.openSettings) loaded first.
   Exposes window.svg and window.toast for the theme/settings module.
   ========================================================================== */

/* ---------- icons ---------- */
const ICONS = {
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-4-.9L3 21l1.9-4a8.4 8.4 0 1 1 16.1-5.5Z"/>',
  code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18Z"/>',
  term: '<polyline points="5 7 10 12 5 17"/><line x1="12" y1="17" x2="19" y2="17"/>',
  wave: '<path d="M2 12h2l2-6 3 14 3-12 2 8 2-4h4"/>',
  cmd: '<path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/><circle cx="12" cy="12" r="2.5"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/>',
  send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>',
  pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  activity: '<polyline points="3 12 7 12 10 5 14 19 17 12 21 12"/>',
  brain: '<path d="M9 3a3 3 0 0 0-3 3 3 3 0 0 0-1 5 3 3 0 0 0 2 5 3 3 0 0 0 5 1V4a3 3 0 0 0-2-1Z"/><path d="M15 3a3 3 0 0 1 3 3 3 3 0 0 1 1 5 3 3 0 0 1-2 5 3 3 0 0 1-5 1"/>',
  check: '<path d="M20 6 9 17l-5-5"/>', ban: '<circle cx="12" cy="12" r="9"/><line x1="5" y1="5" x2="19" y2="19"/>',
  bolt: '<polygon points="13 2 4 14 11 14 10 22 20 9 13 9 13 2"/>', lock: '<rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  refresh: '<polyline points="21 4 21 10 15 10"/><path d="M20.5 15a8.5 8.5 0 1 1-2-9L21 10"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1Z"/>',
  ai: '<circle cx="12" cy="12" r="4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/>',
};
const svg = (n) => `<svg class="ic" viewBox="0 0 24 24">${ICONS[n] || ""}</svg>`;
window.svg = svg;
document.querySelectorAll("[data-ic]").forEach((e) => e.innerHTML = svg(e.getAttribute("data-ic")));

/* ---------- helpers ---------- */
const $ = (s) => document.querySelector(s);
const feed = $("#feed"), input = $("#input"), activity = $("#activity");
let busy = false, pending = null, pendingImages = [], lastSentImages = [];
function renderAttachments() {
  let el = $("#attachments"); if (!el) return;
  el.innerHTML = pendingImages.map((src, i) => `<div class="attach"><img src="${src}"><button data-i="${i}" title="Remove image">×</button></div>`).join("");
  el.querySelectorAll("button").forEach((b) => b.onclick = () => { pendingImages.splice(+b.dataset.i, 1); renderAttachments(); });
}
function addImageFile(file) {
  if (!file || !file.type.startsWith("image/") || pendingImages.length >= 4) return;
  const r = new FileReader(); r.onload = () => { pendingImages.push(r.result); renderAttachments(); }; r.readAsDataURL(file);
}
const now = () => new Date().toLocaleTimeString("en-GB");
function esc(s) { return (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function md(s) {
  s = esc(s);
  s = s.replace(/```([\s\S]*?)```/g, (_, c) => `<pre><code>${c.replace(/^\n/, "")}</code></pre>`);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  s = s.replace(/(https?:\/\/[^\s<]+)/g, (m) => /href=/.test(s) ? m : `<a href="${m}" target="_blank">${m}</a>`);
  return s.split(/\n{2,}/).map((p) => `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
}
function scroll() { feed.scrollTop = feed.scrollHeight; }
function toast(m) { const t = document.createElement("div"); t.className = "tst"; t.textContent = m; $("#toast").appendChild(t); setTimeout(() => t.remove(), 3000); }
window.toast = toast;

/* ---------- orb state ---------- */
function orb(state, sub) {
  const o = $("#orb"); o.className = "orb " + (state || "");
  const L = { "": "Idle", thinking: "Thinking", acting: "Acting", speaking: "Speaking", listening: "Listening" };
  $("#orbState").textContent = L[state || ""] || "Idle";
  if (sub !== undefined) $("#orbSub").textContent = sub;
}
/* classification badge under the orb — shows how the prompt was routed */
function setCat(label) {
  const c = $("#orbCat"); if (!c) return;
  if (label) { c.textContent = label; c.hidden = false; } else { c.hidden = true; }
}

/* ---------- messages ---------- */
function addTurn(role) {
  const t = document.createElement("div"); t.className = "turn " + (role === "me" ? "me" : "");
  t.innerHTML = `<div class="av ${role === "me" ? "me" : "ai"}">${role === "me" ? "You" : svg("ai")}</div><div class="bubble"></div>${role === "me" ? "" : '<button class="copymsg" title="Copy this reply">Copy</button>'}`;
  feed.appendChild(t); scroll(); return t.querySelector(".bubble");
}
function addUser(text, images = []) { const b = addTurn("me"); b.innerHTML = md(text) + (images.length ? `<div class="imgchips">${images.map((x) => `<img src="${x}" alt="attached image">`).join("")}</div>` : ""); }
feed.addEventListener("click", async (e) => {
  const btn = e.target.closest(".copymsg"); if (!btn) return;
  const bubble = btn.closest(".turn").querySelector(".bubble");
  try { await navigator.clipboard.writeText(bubble.innerText); btn.textContent = "Copied"; toast("Reply copied"); setTimeout(() => btn.textContent = "Copy", 1400); }
  catch (err) { toast("Clipboard permission unavailable"); }
});

/* ---------- activity + skills ---------- */
const AMAP = {
  run_command: ["EXEC", "ok"], write_file: ["WRITE", "write"], write_clipboard: ["CLIPBOARD", "write"],
  read_file: ["READ", "ok"], list_dir: ["LIST", "ok"], search_files: ["FIND", "ok"], find_files: ["FIND", "ok"],
  web_search: ["SEARCH", "net"], fetch_url: ["FETCH", "net"], open_url: ["OPEN", "net"],
  open_app: ["LAUNCH", "ok"], open_path: ["OPEN", "ok"], delete_path: ["DELETE", "deny"],
  send_email: ["EMAIL", "write"], screenshot: ["SCREEN", "ok"], ocr_image: ["OCR", "ok"],
  remember: ["REMEMBER", "learn"], learn: ["LEARN", "learn"], skills: ["SKILLS", "ok"],
  remember_document: ["INDEX", "learn"], search_knowledge: ["RECALL", "ok"], recall_notes: ["RECALL", "ok"], system_info: ["SYS", "ok"],
};
const KI = { ok: "check", write: "lock", deny: "ban", net: "globe", learn: "brain" };
function act(label, detail, kind) {
  const el = document.createElement("div"); el.className = "act";
  el.innerHTML = `<div class="ai ${kind}">${svg(KI[kind] || "check")}</div><div><div class="tx">${esc(label)} · <span style="color:var(--muted)">${esc(detail)}</span></div><div class="tt">${now()}</div></div>`;
  activity.prepend(el); while (activity.children.length > 24) activity.lastChild.remove();
}
function actTool(t) {
  const err = (t.result || "").startsWith("ERROR"); let [l, k] = AMAP[t.name] || ["TOOL", "ok"]; if (err) k = "deny";
  const a = Object.values(t.args || {})[0]; act(err ? l + " denied" : l, a != null ? String(a).slice(0, 40) : t.name, k);
  if (t.name === "learn" || t.name === "remember" || t.name === "remember_document") loadLearning();
}

/* ---------- streaming chat ---------- */
async function send(text, confirm) {
  if (busy && confirm === undefined) return;
  let images = confirm === undefined ? pendingImages.slice() : lastSentImages.slice();
  if (confirm === undefined) { text = (text || "").trim(); if (!text && !images.length) return; addUser(text || "", images); lastSentImages = images; pendingImages = []; renderAttachments(); }
  busy = true; input.value = ""; grow(); $("#sendBtn").disabled = true;
  orb("thinking", "processing…"); setCat(null);
  const bubble = addTurn("ai"); let raw = ""; let toolCalls = []; let meta = "";
  bubble.innerHTML = '<span class="caret"></span>';
  try {
    const resp = await fetch("/api/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, confirm: confirm ?? null, images }),
    });
    const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = "";
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true }); let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 2);
        if (!line.startsWith("data: ")) continue; let ev; try { ev = JSON.parse(line.slice(6)); } catch (e) { continue; }
        if (ev.t === "route") { meta = `${ev.label || ev.role} · ${ev.model}`; setCat(ev.label || ev.role); }
        else if (ev.t === "token") { raw += ev.d; bubble.innerHTML = md(raw) + '<span class="caret"></span>'; scroll(); }
        else if (ev.t === "tool") {
          orb("acting", "running " + ev.name); toolCalls.push(ev); actTool(ev);
          bubble.querySelector(".caret") && (bubble.innerHTML = md(raw) + renderTools(toolCalls) + '<span class="caret"></span>'); scroll();
        }
        else if (ev.t === "confirm") { bubble.closest(".turn").remove(); pending = { text }; orb("", "awaiting authorization"); renderConfirm(ev.info); busy = false; $("#sendBtn").disabled = false; return; }
        else if (ev.t === "error") { raw = (raw ? raw + "\n\n" : "") + "⚠️ " + ev.message; bubble.innerHTML = md(raw); }
        else if (ev.t === "done") { meta = `${ev.label || ev.role} · ${ev.model}`; if (ev.reply && !raw) raw = ev.reply; }
      }
    }
    bubble.innerHTML = md(raw || "(no reply)") + renderTools(toolCalls) + (meta ? `<div class="meta">${esc(meta)}</div>` : "");
    orb("speaking", "done"); setTimeout(() => orb("", profSub()), 1200);
    loadMetrics();
  } catch (e) { bubble.innerHTML = md("⚠️ Backend unreachable — is the Sakura server running?"); orb("", profSub()); }
  finally { busy = false; $("#sendBtn").disabled = false; scroll(); }
}
function renderTools(tc) {
  if (!tc.length) return "";
  return '<div class="toolrow">' + tc.map((t) => {
    const err = (t.result || "").startsWith("ERROR"); return `<span class="toolchip ${err ? "err" : ""}">${svg("bolt")}${esc(t.name)}</span>`;
  }).join("") + "</div>";
}
function renderConfirm(info) {
  const el = document.createElement("div"); el.className = "confirm";
  el.innerHTML = `<h4>${svg("shield")} Authorization required</h4><div>${md(info.message || "Confirm this action?")}</div>
    <div class="b"><button class="y">Authorize</button><button class="n">Deny</button></div>`;
  feed.appendChild(el); scroll();
  el.querySelector(".y").onclick = () => { el.remove(); act("EXEC authorized", info.args?.command || info.action || "action", "ok"); send(pending.text, true); };
  el.querySelector(".n").onclick = () => { el.remove(); act("EXEC denied", info.args?.command || info.action || "action", "deny"); send(pending.text, false); };
}

/* ---------- telemetry sparklines (smooth 60fps, interpolated + scrolling) ---------- */
const SPARK_N = 64, PUSH_MS = 220;
const SPARK = {
  cpu:  { buf: [], cur: 0, target: 0, el: "#sparkCpu",  color: "--teal", max: 100 },
  mem:  { buf: [], cur: 0, target: 0, el: "#sparkMem",  color: "--gold", max: 100 },
  tps:  { buf: [], cur: 0, target: 0, el: "#sparkTps",  color: "--cyan", max: 12 },
  temp: { buf: [], cur: 0, target: 0, el: "#sparkTemp", color: "--rose", max: 90, off: true },
};
let peakTps = 0, sparkLast = 0;
function seedSpark(k, v) { const s = SPARK[k]; s.target = v; if (!s.buf.length) { s.cur = v; for (let i = 0; i < SPARK_N; i++) s.buf.push(v); } }
function drawSpark(s, phase) {
  const cv = document.querySelector(s.el); if (!cv) return;
  const w = cv.clientWidth || 190, h = cv.clientHeight || 34;
  if (cv.width !== w) cv.width = w; if (cv.height !== h) cv.height = h;
  const ctx = cv.getContext("2d"); ctx.clearRect(0, 0, w, h);
  const buf = s.buf; if (buf.length < 2) return;
  const col = getComputedStyle(document.documentElement).getPropertyValue(s.color).trim() || "#38bdf8";
  const max = Math.max(s.max, ...buf) * 1.1 || 1;
  const step = w / (SPARK_N - 2);
  const px = (i) => (i - phase) * step;
  const py = (v) => h - (v / max) * (h - 5) - 2;
  ctx.beginPath(); ctx.moveTo(px(0), h);
  buf.forEach((v, i) => ctx.lineTo(px(i), py(v)));
  ctx.lineTo(px(buf.length - 1), h); ctx.closePath();
  ctx.globalAlpha = 0.15; ctx.fillStyle = col; ctx.fill();
  ctx.globalAlpha = 1; ctx.beginPath();
  buf.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
  ctx.strokeStyle = col; ctx.lineWidth = 1.6; ctx.lineJoin = "round"; ctx.stroke();
  const lx = px(buf.length - 1), ly = py(buf[buf.length - 1]);
  ctx.beginPath(); ctx.arc(lx, ly, 2.4, 0, 7); ctx.fillStyle = col; ctx.fill();
}
function sparkLoop(t) {
  if (!sparkLast) sparkLast = t;
  for (const k in SPARK) { const s = SPARK[k]; s.cur += (s.target - s.cur) * 0.12; }
  if (t - sparkLast >= PUSH_MS) {
    sparkLast = t;
    for (const k in SPARK) { const s = SPARK[k]; if (s.off) continue; s.buf.push(s.cur); while (s.buf.length > SPARK_N) s.buf.shift(); }
  }
  const phase = Math.min(1, (t - sparkLast) / PUSH_MS);
  for (const k in SPARK) { const s = SPARK[k]; if (s.off) continue; drawSpark(s, phase); }
  requestAnimationFrame(sparkLoop);
}
requestAnimationFrame(sparkLoop);
function fmtUptime(sec) { sec = sec || 0; const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60); return h ? `${h}h ${m}m` : `${m}m`; }

/* ---------- metrics + status ---------- */
function loadMetrics() {
  fetch("/api/metrics").then((r) => r.json()).then((m) => {
    const tps = +(m.tokens_per_sec || 0);
    $("#stTps").textContent = tps.toFixed(1);
    $("#stCpu").textContent = (m.cpu_percent ?? "—");
    $("#stMem").textContent = (m.mem_used_gb ?? "—");
    seedSpark("cpu", +(m.cpu_percent || 0));
    seedSpark("mem", +(m.mem_percent || 0));
    seedSpark("tps", tps);
    const tg = $("#tempGraph");
    if (m.temp_c != null) { SPARK.temp.off = false; if (tg) tg.style.display = ""; $("#stTemp").textContent = m.temp_c; seedSpark("temp", +m.temp_c); }
    else { SPARK.temp.off = true; if (tg) tg.style.display = "none"; }
    if (tps > peakTps) { peakTps = tps; $("#ssPeak").textContent = peakTps.toFixed(1); }
    if (m.uptime_s != null) $("#ssUp").textContent = fmtUptime(m.uptime_s);
    $("#ssMsg").textContent = document.querySelectorAll("#feed .turn.me").length;
  }).catch(() => {});
}

/* ---------- scheduled tasks ---------- */
function loadTasks() {
  fetch("/api/tasks").then((r) => r.json()).then((d) => {
    $("#taskCount").textContent = d.count;
    const el = $("#taskList");
    if (!d.tasks || !d.tasks.length) {
      el.innerHTML = '<div class="empty">No scheduled tasks. Ask Sakura to "remind me…" or "every hour…".</div>'; return;
    }
    el.innerHTML = d.tasks.map((t) => {
      const rep = t.every_minutes ? `every ${t.every_minutes}m` : "once";
      const s = t.in_seconds;
      const when = s > 3600 ? `in ${Math.round(s / 3600)}h` : s > 60 ? `in ${Math.round(s / 60)}m` : `in ${s}s`;
      return `<div class="task"><div class="tinfo"><div class="tn">${esc(t.instruction).slice(0, 90)}</div><div class="tm">${rep} · ${when}</div></div><button class="tx" data-id="${t.id}" title="Cancel task">✕</button></div>`;
    }).join("");
    el.querySelectorAll(".tx").forEach((b) => b.onclick = async () => {
      await fetch("/api/tasks/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: b.dataset.id }) }).catch(() => {});
      toast("Task cancelled"); act("SCHED", "cancelled " + b.dataset.id, "warn"); loadTasks();
    });
  }).catch(() => {});
}

/* ---------- model card (read-only — chosen automatically) ---------- */
function loadModels() {
  fetch("/api/models").then((r) => r.json()).then((d) => {
    if ($("#modelName")) $("#modelName").textContent = d.primary || "—";
    if ($("#ctxTag")) $("#ctxTag").textContent = d.num_ctx ? `ctx ${d.num_ctx}` : "—";
    if ($("#modelMeta")) $("#modelMeta").textContent = `auto-selected · ${d.installed ? d.installed.length : 0} installed${d.single_model ? " · single-model" : ""}`;
  }).catch(() => {});
}
if ($("#modelRetry")) $("#modelRetry").onclick = async () => {
  const b = $("#modelRetry"), note = $("#modelRetryNote"); b.disabled = true; note.textContent = "Connecting to Ollama and warming the model…";
  try {
    const r = await fetch("/api/models/retry", { method: "POST" }).then((x) => x.json());
    note.textContent = r.connected ? `${r.installed?.length || 0} model(s) found${r.loaded ? " · primary model loaded" : " · primary model not loaded"}` : (r.message || "Ollama is unavailable");
    toast(r.connected ? "Models refreshed" : "Could not connect to Ollama"); loadModels(); loadStatus();
  } catch (e) { note.textContent = "Retry failed — check that Ollama is installed and running."; }
  finally { b.disabled = false; }
};

/* ---------- memory & knowledge ---------- */
function loadMemory() {
  fetch("/api/learning").then((r) => r.json()).then((d) => {
    const el = $("#memList"); if (!el) return;
    const notes = (d.notes || []).slice().reverse();
    if (!notes.length) {
      el.innerHTML = '<div class="empty">Nothing remembered yet. Sakura saves durable facts about you and your setup as it learns.</div>';
    } else {
      el.innerHTML = notes.slice(0, 8).map((n) => `<div class="mem"><span class="dt"></span>${esc(n).slice(0, 140)}</div>`).join("");
    }
  }).catch(() => {});
}
let prof = "trusted";
function profSub() { return prof.charAt(0).toUpperCase() + prof.slice(1) + " · ready"; }
function loadStatus() {
  fetch("/api/status").then((r) => r.json()).then((s) => {
    const d = $("#connDot"), t = $("#connTxt");
    if (!s.connected) { d.className = "d bad"; t.textContent = "Ollama offline"; }
    else if (s.missing && s.missing.length) { d.className = "d warn"; t.textContent = `${s.installed.length}/${s.required.length} models`; }
    else { d.className = "d ok"; t.textContent = s.primary_model || "ready"; }
    if (s.primary_model) $("#ctxMeta").textContent = s.primary_model;
    if (s.profile) { prof = s.profile; syncProf(); }
    syncAuto(s);
    if (s.skills != null) $("#skillCount").textContent = s.skills + " skill" + (s.skills === 1 ? "" : "s");
    if (s.rag && $("#memTag")) $("#memTag").textContent = (s.rag.documents || 0) + " doc" + (s.rag.documents === 1 ? "" : "s");
    const h = s.hardware, hl = $("#hwLine");
    if (h && hl) {
      const badge = h.low_ram_mode ? '<b style="color:var(--gold)">Low-RAM profile</b>' : '<b style="color:var(--emerald)">Standard profile</b>';
      hl.innerHTML = `${badge} · ${h.total_ram_gb} GB RAM (${h.free_ram_gb} free) · ${h.physical_cores} cores<br>ctx ${h.num_ctx} · ${h.num_threads} threads · CPU inference`;
    }
  }).catch(() => { $("#connDot").className = "d bad"; $("#connTxt").textContent = "backend offline"; });
}

/* ---------- autonomy + caps ---------- */
const PROFNOTES = {
  locked: "Read-mostly. Shell & file writes are OFF. Safe browsing only.",
  trusted: "Full capability. Only genuinely destructive commands ask once.",
  unleashed: "⚠ Maximum freedom — nothing is gated except email. It can do anything on this machine.",
};
function syncProf() {
  document.querySelectorAll("#profSeg button").forEach((b) => b.classList.toggle("on", b.dataset.p === prof));
  $("#profTag").textContent = prof; $("#profNote").textContent = PROFNOTES[prof] || ""; $("#orbSub").textContent = profSub();
  loadSettings();
}
document.querySelectorAll("#profSeg button").forEach((b) => b.onclick = async () => {
  const p = b.dataset.p;
  if (p === "unleashed" && !confirm("Unleashed mode lets the AI run ANY command on your machine without asking, including destructive ones. Continue?")) return;
  prof = p; syncProf();
  try {
    await fetch("/api/autonomy", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: p }) });
    act("PROFILE", p + " engaged", p === "unleashed" ? "write" : "ok"); toast("Autonomy: " + p);
  } catch (e) {}
});

/* ---------- performance tier + GPU ---------- */
/* Performance is fully automatic — the panel just REPORTS what Sakura chose,
   sized to the machine's RAM / CPU. Users don't (and can't) tune it by hand. */
function syncAuto(s) {
  const h = s.hardware || {};
  const tier = s.perf_tier || "auto";
  if ($("#perfTag")) $("#perfTag").textContent = "auto";
  const gpu = h.gpu_layers > 0 ? "iGPU offload" : "CPU inference";
  const line = `${tier} profile · ctx ${h.num_ctx ?? "—"} · ${h.num_threads ?? "—"} threads · ${gpu}`;
  if ($("#autoTune")) $("#autoTune").textContent = line;
}
function loadSettings() {
  fetch("/api/settings").then((r) => r.json()).then((s) => {
    document.querySelectorAll(".cap[data-key]").forEach((c) => c.classList.toggle("on", !!s.runtime[c.dataset.key]));
  }).catch(() => {});
}
document.querySelectorAll(".cap[data-key]").forEach((c) => c.onclick = async () => {
  const on = !c.classList.contains("on"); c.classList.toggle("on", on);
  try {
    await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: c.dataset.key, value: on }) });
    act("POLICY", c.dataset.key + " " + (on ? "on" : "off"), on ? "ok" : "deny");
  } catch (e) { c.classList.toggle("on", !on); }
});

/* ---------- learning panel ---------- */
function loadLearning() {
  fetch("/api/learning").then((r) => r.json()).then((d) => {
    $("#skillCount").textContent = d.skill_count + " skill" + (d.skill_count === 1 ? "" : "s");
    const el = $("#skillList");
    if (!d.skills.length) { el.innerHTML = '<div class="empty">No skills learned yet. As Sakura works, it teaches itself reusable procedures.</div>'; return; }
    el.innerHTML = d.skills.slice(0, 6).map((s) => `<div class="skill"><div class="n">${esc(s.name)}<span class="u">${s.uses}x</span></div><div class="c">${esc(s.content).slice(0, 110)}</div></div>`).join("");
  }).catch(() => {});
}

/* ---------- voice ---------- */
let media, chunks = [], rec = false; const mic = $("#micBtn");
mic.onmousedown = start; mic.onmouseup = stop; mic.onmouseleave = stop;
mic.ontouchstart = (e) => { e.preventDefault(); start(); }; mic.ontouchend = (e) => { e.preventDefault(); stop(); };
async function start() {
  if (rec) return;
  try {
    const st = await navigator.mediaDevices.getUserMedia({ audio: true });
    media = new MediaRecorder(st); chunks = []; media.ondataavailable = (e) => chunks.push(e.data);
    media.onstop = async () => {
      st.getTracks().forEach((t) => t.stop());
      const fd = new FormData(); fd.append("audio", new Blob(chunks, { type: "audio/webm" }), "c.webm");
      orb("thinking", "transcribing…");
      try {
        const d = await (await fetch("/api/voice", { method: "POST", body: fd })).json();
        if (d.transcript) addUser(d.transcript);
        const b = addTurn("ai"); b.innerHTML = md(d.reply || "") + renderTools(d.tool_calls || []);
        (d.tool_calls || []).forEach(actTool);
        if (d.audio_b64) { orb("speaking", "speaking"); new Audio("data:audio/wav;base64," + d.audio_b64).play(); }
        orb("", profSub()); loadMetrics();
      } catch (e) { orb("", profSub()); toast("voice failed"); }
    };
    media.start(); rec = true; mic.classList.add("rec"); orb("listening", "listening…");
  } catch (e) { toast("Mic unavailable"); }
}
function stop() { if (rec && media) { media.stop(); rec = false; mic.classList.remove("rec"); } }

/* ---------- recent chats (browse & reopen past conversations) ---------- */
function fmtTime(ts) { try { return new Date(ts * 1000).toLocaleString("en-GB", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" }); } catch (e) { return ""; } }
function openHistory() {
  const body = $("#histBody"); if (!body) return;
  body.innerHTML = '<div class="empty">Loading…</div>';
  $("#history").classList.add("open");
  fetch("/api/sessions").then((r) => r.json()).then((d) => {
    const list = d.sessions || [];
    if (!list.length) { body.innerHTML = '<div class="empty">No past chats yet. Start talking with Sakura and your conversations will be saved here — you can reopen any of them later.</div>'; return; }
    body.innerHTML = '<div class="sesslist">' + list.map((s) => `
      <button class="sesscard ${s.active ? "active" : ""}" data-id="${s.id}">
        <div class="st">${esc(s.title || "New chat")}</div>
        <div class="sm"><span>${s.count} message${s.count === 1 ? "" : "s"}</span><span>${fmtTime(s.last_ts)}</span></div>
        ${s.active ? '<span class="cur">current</span>' : ""}
        <span class="improve" data-title-id="${s.id}" title="Ask Sakura to improve this title">✦</span>
      </button>`).join("") + "</div>";
    body.querySelectorAll(".improve").forEach((b) => b.onclick = async (e) => {
      e.stopPropagation(); b.textContent = "…";
      const r = await fetch("/api/sessions/title", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: +b.dataset.titleId, improve: true }) }).then((x) => x.json()).catch(() => ({}));
      if (r.title) openHistory(); else { b.textContent = "✦"; toast("Could not improve title"); }
    });
    body.querySelectorAll(".sesscard").forEach((c) => c.onclick = () => reopenSession(c.dataset.id));
  }).catch(() => { body.innerHTML = '<div class="empty">Couldn\'t load chats — is the server running?</div>'; });
}
function reopenSession(id) {
  fetch("/api/sessions/load", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: +id }) })
    .then((r) => r.json()).then((d) => {
      feed.innerHTML = "";
      const msgs = (d.messages || []).filter((m) => m.role === "user" || m.role === "assistant");
      if (!msgs.length) { welcome(); }
      else msgs.forEach((m) => {
        if (m.role === "user") { const b = addTurn("me"); b.innerHTML = md(m.content); }
        else { const b = addTurn("ai"); b.innerHTML = md(m.content) + (m.model ? `<div class="meta">${esc(m.model)}</div>` : ""); }
      });
      closeHistory(); scroll(); toast("Reopened chat");
    }).catch(() => toast("Couldn't reopen chat"));
}
function closeHistory() { $("#history").classList.remove("open"); }
if ($("#historyBtn")) $("#historyBtn").onclick = openHistory;
if ($("#histClose")) $("#histClose").onclick = closeHistory;
if ($("#history")) $("#history").addEventListener("click", (e) => { if (e.target.id === "history") closeHistory(); });

/* ---------- fullscreen (F11) ---------- */
function toggleFullscreen() {
  const d = document, el = d.documentElement;
  try {
    if (!d.fullscreenElement && !d.webkitFullscreenElement) {
      (el.requestFullscreen || el.webkitRequestFullscreen || function () {}).call(el);
    } else {
      (d.exitFullscreen || d.webkitExitFullscreen || function () {}).call(d);
    }
  } catch (e) {
    // Desktop (pywebview) fallback if the Fullscreen API is blocked.
    if (window.pywebview && window.pywebview.api && window.pywebview.api.toggle_fullscreen) window.pywebview.api.toggle_fullscreen();
  }
}
window.addEventListener("keydown", (e) => { if (e.key === "F11") { e.preventDefault(); toggleFullscreen(); } });

/* ---------- misc actions ---------- */
$("#newBtn").onclick = async () => { await fetch("/api/reset", { method: "POST" }).catch(() => {}); feed.innerHTML = ""; welcome(); toast("New chat"); };
$("#screenBtn").onclick = () => send("take a screenshot and tell me what you see on my screen");
$("#reflectBtn").onclick = async () => {
  orb("thinking", "reflecting…");
  const r = await fetch("/api/reflect", { method: "POST" }).then((r) => r.json()).catch(() => ({ result: "offline" }));
  act("LEARN", r.result, "learn"); toast(r.result); loadLearning(); orb("", profSub());
};
if ($("#settingsBtn")) $("#settingsBtn").onclick = () => window.openSettings();
document.querySelectorAll(".rail button[data-tab]").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".rail button[data-tab]").forEach((x) => x.classList.remove("active")); b.classList.add("active");
  const P = {
    chat: "Ask Sakura anything — it can act on your machine, search the web, and learn…",
    code: "Describe code to write, debug, or refactor — I'll build it…",
    research: "Ask a research question — I'll search the web and synthesize with sources…",
    terminal: "Tell me what to run or automate on this machine…", voice: "Hold the mic and talk…",
  };
  input.placeholder = P[b.dataset.tab] || P.chat; input.focus();
});

/* ---------- command palette ---------- */
const CMDS = [
  { n: "New chat", k: "⌘N", f: () => $("#newBtn").click() },
  { n: "Open settings & themes", f: () => window.openSettings() },
  { n: "Reflect & learn now", f: () => $("#reflectBtn").click() },
  { n: "Analyze my screen", f: () => $("#screenBtn").click() },
  { n: "Autonomy: Trusted", f: () => document.querySelector("#profSeg [data-p=trusted]").click() },
  { n: "Autonomy: Unleashed", f: () => document.querySelector("#profSeg [data-p=unleashed]").click() },
  { n: "Autonomy: Locked", f: () => document.querySelector("#profSeg [data-p=locked]").click() },
  { n: "Run benchmark", f: async () => { toast("benchmarking…"); const r = await fetch("/api/benchmark", { method: "POST" }).then((r) => r.json()).catch(() => ({ message: "offline" })); toast(r.message); loadMetrics(); } },
  { n: "Flush model cache", f: async () => { const r = await fetch("/api/unload", { method: "POST" }).then((r) => r.json()).catch(() => ({ message: "offline" })); toast(r.message); } },
  {
    n: "Export session log", f: async () => {
      const r = await fetch("/api/history?limit=500").then((r) => r.json()).catch(() => ({ messages: [] }));
      const b = new Blob([(r.messages || []).map((m) => `[${m.role}] ${m.content}`).join("\n\n") || "(empty)"], { type: "text/plain" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "sakura-" + Date.now() + ".txt"; a.click(); toast("Exported");
    },
  },
];
let palSel = 0, palShown = CMDS;
function openPal() { $("#pal").classList.add("open"); $("#palIn").value = ""; palShown = CMDS; palSel = 0; renderPal(); $("#palIn").focus(); }
function closePal() { $("#pal").classList.remove("open"); }
function renderPal() {
  $("#palOpts").innerHTML = palShown.map((c, i) => `<div class="opt ${i === palSel ? "sel" : ""}" data-i="${i}">${esc(c.n)}${c.k ? `<span class="k">${c.k}</span>` : ""}</div>`).join("");
  document.querySelectorAll("#palOpts .opt").forEach((o) => o.onclick = () => { palShown[+o.dataset.i].f(); closePal(); });
}
$("#palBtn").onclick = openPal;
$("#palIn").oninput = (e) => { const q = e.target.value.toLowerCase(); palShown = CMDS.filter((c) => c.n.toLowerCase().includes(q)); palSel = 0; renderPal(); };
$("#palIn").onkeydown = (e) => {
  if (e.key === "ArrowDown") { palSel = (palSel + 1) % palShown.length; renderPal(); }
  else if (e.key === "ArrowUp") { palSel = (palSel - 1 + palShown.length) % palShown.length; renderPal(); }
  else if (e.key === "Enter") { palShown[palSel] && palShown[palSel].f(); closePal(); }
  else if (e.key === "Escape") closePal();
};
$("#pal").onclick = (e) => { if (e.target.id === "pal") closePal(); };

/* settings modal dismissal */
const setModal = $("#settings");
if (setModal) setModal.onclick = (e) => { if (e.target.id === "settings") window.closeSettings(); };
if ($("#setClose")) $("#setClose").onclick = () => window.closeSettings();

/* ---------- composer ---------- */
function grow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 150) + "px"; }
input.addEventListener("input", grow);
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); } });
input.addEventListener("paste", (e) => { for (const item of (e.clipboardData?.items || [])) if (item.type.startsWith("image/")) { e.preventDefault(); addImageFile(item.getAsFile()); } });
const composer = $(".composer");
if (composer) {
  composer.addEventListener("dragover", (e) => { e.preventDefault(); composer.classList.add("dragover"); });
  composer.addEventListener("dragleave", () => composer.classList.remove("dragover"));
  composer.addEventListener("drop", (e) => { e.preventDefault(); composer.classList.remove("dragover"); [...(e.dataTransfer?.files || [])].forEach(addImageFile); });
}
$("#sendBtn").onclick = () => send(input.value);
window.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); openPal(); }
  if ((e.metaKey || e.ctrlKey) && e.key === "n") { e.preventDefault(); $("#newBtn").click(); }
  if (e.key === "Escape") { closeHistory(); if (window.closeSettings) window.closeSettings(); }
});

/* ---------- boot ---------- */
function welcome() {
  const b = addTurn("ai");
  b.innerHTML = md("Hi — I'm **Sakura AI**, your autonomous local agent. I can open your apps, find and open files, run the terminal, search the web, and I **learn as I go**. Tell me what you want done and I'll just do it.\n\nOpen **Settings** (top-right ⚙) to change the theme and background, switch **Unleashed** mode to remove guardrails, or keep **Trusted** so destructive actions ask once.");
}
/* ---------- quick actions ---------- */
document.querySelectorAll("#qaGrid button").forEach((b) => b.onclick = () => {
  if (busy) { toast("Busy — one moment…"); return; }
  const q = b.dataset.q; input.value = q; send(q);
});

welcome(); loadStatus(); loadMetrics(); loadSettings(); loadLearning();
loadTasks(); loadModels(); loadMemory();
setInterval(loadStatus, 10000); setInterval(loadMetrics, 4000);
setInterval(loadTasks, 15000); setInterval(loadMemory, 20000); setInterval(loadModels, 30000);
act("DAEMON", "Sakura AI online", "ok");
