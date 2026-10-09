/* ==========================================================================
   Sakura AI — theme engine + settings panel
   Each theme = a color palette (CSS variables) + a "scene" describing its
   animated background (particle type, direction, and scenery like trees, fish,
   waves, fireflies or shooting stars). Selecting one rewrites the variables on
   <html>, persists to localStorage, and broadcasts 'sakura:bg' so the background
   engine switches its animation.
   ========================================================================== */
(function () {
  const THEMES = {
    sakura: {
      name: "Sakura", desc: "Pink · cherry blossoms",
      dots: ["#fb7185", "#f9a8d4", "#fcd34d"],
      vars: {
        "--bg": "#0b0709", "--bg2": "#0f0a0d",
        "--panel": "rgba(26,17,22,.7)", "--panel2": "rgba(34,22,29,.6)",
        "--line": "rgba(255,255,255,.07)", "--line2": "rgba(255,255,255,.13)",
        "--on": "#f5e9ee", "--muted": "#a68a94", "--dim": "#6e5860",
        "--teal": "#fb7185", "--emerald": "#f9a8d4", "--gold": "#fcd34d", "--cyan": "#f0abfc",
        "--rose": "#fb7185", "--amber": "#f59e0b", "--red": "#f87171", "--green": "#4ade80",
        "--tealglow": "rgba(251,113,133,.45)",
        "--au1": "#9d174d", "--au2": "#a21caf", "--au3": "#be185d",
        "--tree-trunk": "#3b1f2b", "--tree-blossom": "#f9a8d4", "--tree-blossom2": "#fbcfe8",
      },
      particles: ["#fbcfe8", "#f9a8d4", "#fb7185", "#f5b8cf", "#fecdd3"],
      scene: { particle: "petal", dir: "down", trees: "blossom" },
    },
    winter: {
      name: "Winter", desc: "White · snowflakes",
      dots: ["#e0f2fe", "#bae6fd", "#7dd3fc"],
      vars: {
        "--bg": "#080b10", "--bg2": "#0c1016",
        "--panel": "rgba(22,28,36,.7)", "--panel2": "rgba(30,38,48,.6)",
        "--line": "rgba(255,255,255,.09)", "--line2": "rgba(255,255,255,.16)",
        "--on": "#eef6fb", "--muted": "#9fb2c2", "--dim": "#647688",
        "--teal": "#bae6fd", "--emerald": "#e0f2fe", "--gold": "#f8fafc", "--cyan": "#7dd3fc",
        "--rose": "#f9a8d4", "--amber": "#fde68a", "--red": "#f87171", "--green": "#6ee7b7",
        "--tealglow": "rgba(186,230,253,.4)",
        "--au1": "#1e3a5f", "--au2": "#334e68", "--au3": "#0e7490",
        "--tree-trunk": "#33404d", "--tree-blossom": "#e0f2fe", "--tree-blossom2": "#ffffff",
      },
      particles: ["#ffffff", "#e0f2fe", "#bae6fd", "#f0f9ff", "#dbeafe"],
      scene: { particle: "snow", dir: "down", trees: false },
    },
    autumn: {
      name: "Autumn", desc: "Orange · falling leaves",
      dots: ["#fb923c", "#f59e0b", "#dc2626"],
      vars: {
        "--bg": "#0c0805", "--bg2": "#130c07",
        "--panel": "rgba(32,20,12,.7)", "--panel2": "rgba(44,26,16,.6)",
        "--line": "rgba(255,255,255,.07)", "--line2": "rgba(255,255,255,.14)",
        "--on": "#f8ebe0", "--muted": "#b39079", "--dim": "#7a5c46",
        "--teal": "#fb923c", "--emerald": "#f59e0b", "--gold": "#fbbf24", "--cyan": "#f97316",
        "--rose": "#ef4444", "--amber": "#f59e0b", "--red": "#dc2626", "--green": "#a3a025",
        "--tealglow": "rgba(251,146,60,.42)",
        "--au1": "#7c2d12", "--au2": "#92400e", "--au3": "#b45309",
        "--tree-trunk": "#3a2416", "--tree-blossom": "#f59e0b", "--tree-blossom2": "#fb923c",
      },
      particles: ["#fdba74", "#fb923c", "#f59e0b", "#dc2626", "#eab308"],
      scene: { particle: "leaf", dir: "down", trees: "autumn" },
    },
    ocean: {
      name: "Ocean", desc: "Blue · fish, waves & bubbles",
      dots: ["#38bdf8", "#22d3ee", "#0ea5e9"],
      vars: {
        "--bg": "#04080f", "--bg2": "#071019",
        "--panel": "rgba(11,22,34,.7)", "--panel2": "rgba(16,30,46,.6)",
        "--line": "rgba(255,255,255,.07)", "--line2": "rgba(255,255,255,.13)",
        "--on": "#e4f1fb", "--muted": "#7c93a8", "--dim": "#4f6478",
        "--teal": "#38bdf8", "--emerald": "#22d3ee", "--gold": "#67e8f9", "--cyan": "#7dd3fc",
        "--rose": "#f472b6", "--amber": "#fcd34d", "--red": "#fb7185", "--green": "#2dd4bf",
        "--tealglow": "rgba(56,189,248,.42)",
        "--au1": "#075985", "--au2": "#0c4a6e", "--au3": "#155e75",
        "--tree-trunk": "#0e2a3a", "--tree-blossom": "#38bdf8", "--tree-blossom2": "#7dd3fc",
      },
      particles: ["#7dd3fc", "#38bdf8", "#22d3ee", "#a5f3fc", "#bae6fd"],
      scene: { particle: "bubble", dir: "up", fish: true, waves: true, trees: false },
    },
    forest: {
      name: "Forest", desc: "Green · leaves & fireflies",
      dots: ["#4ade80", "#22c55e", "#a3e635"],
      vars: {
        "--bg": "#060a07", "--bg2": "#0a110c",
        "--panel": "rgba(15,26,18,.7)", "--panel2": "rgba(20,34,24,.6)",
        "--line": "rgba(255,255,255,.07)", "--line2": "rgba(255,255,255,.13)",
        "--on": "#e7f2e8", "--muted": "#84947f", "--dim": "#566450",
        "--teal": "#4ade80", "--emerald": "#22c55e", "--gold": "#a3e635", "--cyan": "#2dd4bf",
        "--rose": "#fb7185", "--amber": "#eab308", "--red": "#f87171", "--green": "#4ade80",
        "--tealglow": "rgba(74,222,128,.4)",
        "--au1": "#166534", "--au2": "#3f6212", "--au3": "#115e59",
        "--tree-trunk": "#1f3325", "--tree-blossom": "#4ade80", "--tree-blossom2": "#86efac",
      },
      particles: ["#86efac", "#4ade80", "#a3e635", "#bbf7d0", "#65a30d"],
      scene: { particle: "leaf", dir: "down", trees: "green", fireflies: true },
    },
    sunset: {
      name: "Sunset", desc: "Coral · rising embers",
      dots: ["#fb7185", "#fb923c", "#fbbf24"],
      vars: {
        "--bg": "#0c0708", "--bg2": "#130a09",
        "--panel": "rgba(30,17,15,.7)", "--panel2": "rgba(40,22,19,.6)",
        "--line": "rgba(255,255,255,.07)", "--line2": "rgba(255,255,255,.14)",
        "--on": "#faeeea", "--muted": "#b18c84", "--dim": "#795a54",
        "--teal": "#fb7185", "--emerald": "#fb923c", "--gold": "#fbbf24", "--cyan": "#f9a8d4",
        "--rose": "#f43f5e", "--amber": "#f59e0b", "--red": "#ef4444", "--green": "#f59e0b",
        "--tealglow": "rgba(251,113,133,.42)",
        "--au1": "#9a3412", "--au2": "#9d174d", "--au3": "#b45309",
        "--tree-trunk": "#3a201a", "--tree-blossom": "#fb923c", "--tree-blossom2": "#fdba74",
      },
      particles: ["#fdba74", "#fb923c", "#fb7185", "#fbbf24", "#fca5a5"],
      scene: { particle: "ember", dir: "up", trees: false },
    },
    galaxy: {
      name: "Galaxy", desc: "Indigo · stars & comets",
      dots: ["#818cf8", "#c084fc", "#22d3ee"],
      vars: {
        "--bg": "#05060f", "--bg2": "#090a18",
        "--panel": "rgba(18,18,34,.7)", "--panel2": "rgba(26,26,46,.6)",
        "--line": "rgba(255,255,255,.08)", "--line2": "rgba(255,255,255,.15)",
        "--on": "#e9e8fb", "--muted": "#8b8ab0", "--dim": "#585679",
        "--teal": "#818cf8", "--emerald": "#c084fc", "--gold": "#fcd34d", "--cyan": "#22d3ee",
        "--rose": "#f472b6", "--amber": "#fbbf24", "--red": "#f87171", "--green": "#4ade80",
        "--tealglow": "rgba(129,140,248,.42)",
        "--au1": "#312e81", "--au2": "#6d28d9", "--au3": "#1e3a8a",
        "--tree-trunk": "#2a2a45", "--tree-blossom": "#c084fc", "--tree-blossom2": "#a5b4fc",
      },
      particles: ["#ffffff", "#c4b5fd", "#a5b4fc", "#e9d5ff", "#67e8f9"],
      scene: { particle: "star", dir: "twinkle", shooting: true, trees: false },
    },
    lavender: {
      name: "Lavender", desc: "Purple · drifting petals",
      dots: ["#c084fc", "#d8b4fe", "#a78bfa"],
      vars: {
        "--bg": "#0a070f", "--bg2": "#0f0b16",
        "--panel": "rgba(28,20,38,.7)", "--panel2": "rgba(38,26,52,.6)",
        "--line": "rgba(255,255,255,.08)", "--line2": "rgba(255,255,255,.15)",
        "--on": "#f2ebfb", "--muted": "#a493b8", "--dim": "#6c5c80",
        "--teal": "#c084fc", "--emerald": "#d8b4fe", "--gold": "#f0abfc", "--cyan": "#a78bfa",
        "--rose": "#f472b6", "--amber": "#fbbf24", "--red": "#f87171", "--green": "#4ade80",
        "--tealglow": "rgba(192,132,252,.42)",
        "--au1": "#6d28d9", "--au2": "#7e22ce", "--au3": "#9d174d",
        "--tree-trunk": "#33234a", "--tree-blossom": "#d8b4fe", "--tree-blossom2": "#ede9fe",
      },
      particles: ["#ede9fe", "#d8b4fe", "#c084fc", "#e9d5ff", "#a78bfa"],
      scene: { particle: "petal", dir: "down", trees: "blossom" },
    },
    ruby: {
      name: "Ruby", desc: "Red · fiery sparks",
      dots: ["#f43f5e", "#ef4444", "#fb7185"],
      vars: {
        "--bg": "#0c0608", "--bg2": "#14080b",
        "--panel": "rgba(34,14,18,.7)", "--panel2": "rgba(46,18,24,.6)",
        "--line": "rgba(255,255,255,.08)", "--line2": "rgba(255,255,255,.15)",
        "--on": "#fce8ec", "--muted": "#b98891", "--dim": "#7e5560",
        "--teal": "#f43f5e", "--emerald": "#fb7185", "--gold": "#fbbf24", "--cyan": "#fda4af",
        "--rose": "#f43f5e", "--amber": "#f97316", "--red": "#ef4444", "--green": "#f59e0b",
        "--tealglow": "rgba(244,63,94,.45)",
        "--au1": "#9f1239", "--au2": "#b91c1c", "--au3": "#7c2d12",
        "--tree-trunk": "#3a1620", "--tree-blossom": "#fb7185", "--tree-blossom2": "#fda4af",
      },
      particles: ["#fecaca", "#fb7185", "#f43f5e", "#fca5a5", "#f97316"],
      scene: { particle: "ember", dir: "up", trees: false },
    },
    mono: {
      name: "Monochrome", desc: "Slate · quiet dust",
      dots: ["#e2e8f0", "#94a3b8", "#64748b"],
      vars: {
        "--bg": "#0a0b0d", "--bg2": "#101114",
        "--panel": "rgba(24,26,30,.7)", "--panel2": "rgba(32,35,40,.6)",
        "--line": "rgba(255,255,255,.08)", "--line2": "rgba(255,255,255,.16)",
        "--on": "#eef1f5", "--muted": "#8b93a1", "--dim": "#5b6472",
        "--teal": "#cbd5e1", "--emerald": "#94a3b8", "--gold": "#e2e8f0", "--cyan": "#a5b4fc",
        "--rose": "#f472b6", "--amber": "#fbbf24", "--red": "#f87171", "--green": "#4ade80",
        "--tealglow": "rgba(203,213,225,.35)",
        "--au1": "#334155", "--au2": "#475569", "--au3": "#1e293b",
        "--tree-trunk": "#2b3240", "--tree-blossom": "#cbd5e1", "--tree-blossom2": "#e2e8f0",
      },
      particles: ["#e2e8f0", "#cbd5e1", "#94a3b8", "#f1f5f9", "#64748b"],
      scene: { particle: "dust", dir: "down", trees: false },
    },
  };

  const DEFAULT_BG = { particles: true, scenery: true, intensity: 1 };

  const state = {
    theme: localStorage.getItem("sakura.theme") || "sakura",  // may be "auto"
    resolved: "sakura",
    bg: Object.assign({}, DEFAULT_BG, JSON.parse(localStorage.getItem("sakura.bg") || "{}")),
  };
  if (state.theme !== "auto" && !THEMES[state.theme]) state.theme = "sakura";

  function pickByTime() {
    const h = new Date().getHours();
    if (h >= 6 && h < 11) return "sakura";
    if (h >= 11 && h < 16) return "ocean";
    if (h >= 16 && h < 20) return "autumn";
    return "galaxy";
  }

  let autoTimer = null;
  function paint(id) {
    const t = THEMES[id]; if (!t) return;
    const root = document.documentElement;
    for (const [k, v] of Object.entries(t.vars)) root.style.setProperty(k, v);
    state.resolved = id;
    applyScenery();
    broadcast();
  }
  function applyTheme(id) {
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
    if (id === "auto") {
      state.theme = "auto"; localStorage.setItem("sakura.theme", "auto");
      paint(pickByTime());
      autoTimer = setInterval(() => { const p = pickByTime(); if (p !== state.resolved) paint(p); }, 60000);
      return;
    }
    if (!THEMES[id]) return;
    state.theme = id; localStorage.setItem("sakura.theme", id);
    paint(id);
  }

  // Show/hide the SVG trees depending on the theme's scene + the scenery toggle,
  // and tag the tree variant so CSS can tweak the canopy look.
  function applyScenery() {
    const trees = document.getElementById("trees");
    if (!trees) return;
    const sc = (THEMES[state.resolved] || {}).scene || {};
    const on = state.bg.scenery && !!sc.trees;
    trees.style.display = on ? "" : "none";
    trees.dataset.variant = sc.trees || "";
  }

  function applyBg() {
    const petals = document.getElementById("petals");
    const aurora = document.getElementById("aurora");
    if (petals) petals.style.display = state.bg.particles ? "" : "none";
    if (aurora) aurora.style.display = "";
    applyScenery();
    localStorage.setItem("sakura.bg", JSON.stringify(state.bg));
    broadcast();
  }

  function broadcast() {
    const t = THEMES[state.resolved] || THEMES.sakura;
    window.dispatchEvent(new CustomEvent("sakura:bg", {
      detail: { particles: t.particles, scene: t.scene, bg: state.bg, theme: state.resolved },
    }));
  }

  window.SakuraTheme = {
    themes: THEMES, state,
    apply: applyTheme,
    setBg(k, v) { state.bg[k] = v; applyBg(); },
    current() { return THEMES[state.resolved] || THEMES.sakura; },
  };

  /* ---------- per-theme icons (animated in the picker) ---------- */
  // Which glyph + motion represents each theme by name.
  const ICON_FOR = {
    sakura: "blossom", winter: "snow", autumn: "leaf", ocean: "fish",
    forest: "tree", sunset: "flame", galaxy: "star", lavender: "petal",
    ruby: "spark", mono: "dust", auto: "auto",
  };
  // Motion class applied so each swatch icon animates like its scene.
  const ANIM_FOR = {
    blossom: "sway", petal: "sway", leaf: "sway", tree: "sway",
    snow: "spin", fish: "swim", flame: "flicker", spark: "flicker",
    star: "twinkle", dust: "pulse", auto: "spin-slow",
  };
  const ICONS = {
    blossom: `<g fill="currentColor"><circle cx="12" cy="12" r="2.4" opacity=".9"/>
      <g><ellipse cx="12" cy="5.5" rx="2.4" ry="3.6"/></g>
      <g transform="rotate(72 12 12)"><ellipse cx="12" cy="5.5" rx="2.4" ry="3.6"/></g>
      <g transform="rotate(144 12 12)"><ellipse cx="12" cy="5.5" rx="2.4" ry="3.6"/></g>
      <g transform="rotate(216 12 12)"><ellipse cx="12" cy="5.5" rx="2.4" ry="3.6"/></g>
      <g transform="rotate(288 12 12)"><ellipse cx="12" cy="5.5" rx="2.4" ry="3.6"/></g></g>`,
    petal: `<path fill="currentColor" d="M12 3c4 4 5 9 0 18-5-9-4-14 0-18z"/>`,
    snow: `<g stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
      <line x1="12" y1="3" x2="12" y2="21"/><line x1="3.5" y1="7.5" x2="20.5" y2="16.5"/>
      <line x1="20.5" y1="7.5" x2="3.5" y2="16.5"/>
      <g stroke-width="1.3"><path d="M12 6l-2.2 2M12 6l2.2 2M12 18l-2.2-2M12 18l2.2-2"/></g></g>`,
    leaf: `<g><path fill="currentColor" d="M5 19C4 11 10 4 19 4c1 9-5 16-14 15z"/>
      <path stroke="rgba(0,0,0,.35)" stroke-width="1.2" fill="none" d="M6 18C10 13 14 9 18 6"/></g>`,
    tree: `<g fill="currentColor"><path d="M12 2l5 7h-3l4 6h-4l3 5H7l3-5H6l4-6H7z"/>
      <rect x="11" y="19" width="2" height="3" fill="rgba(0,0,0,.4)"/></g>`,
    fish: `<g fill="currentColor"><ellipse cx="10" cy="12" rx="7" ry="4"/>
      <path d="M17 12l5-3v6z"/><circle cx="6" cy="11" r="1" fill="rgba(0,0,0,.5)"/></g>`,
    flame: `<path fill="currentColor" d="M12 2c3 4 1 6 3 8 1-1 1-2 1-3 2 2 3 5 3 7a7 7 0 11-14 0c0-3 2-6 5-8-1 3 0 4 1 4 1-3-2-5 0-8z"/>`,
    spark: `<g fill="currentColor"><path d="M12 2l1.6 6.4L20 10l-6.4 1.6L12 18l-1.6-6.4L4 10l6.4-1.6z"/>
      <circle cx="18.5" cy="17.5" r="1.6"/><circle cx="5.5" cy="17" r="1.2"/></g>`,
    star: `<path fill="currentColor" d="M12 2l2.6 6.6L21 9.3l-5 4.3 1.6 6.8L12 16.9 6.4 20.4 8 13.6l-5-4.3 6.4-.7z"/>`,
    dust: `<g fill="currentColor"><circle cx="7" cy="9" r="1.7"/><circle cx="13" cy="14" r="2.1"/>
      <circle cx="17" cy="8" r="1.3"/><circle cx="10" cy="18" r="1.1"/></g>`,
    auto: `<g><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/>
      <path fill="currentColor" d="M12 3a9 9 0 000 18z"/></g>`,
  };
  function svgIcon(id) {
    const key = ICON_FOR[id] || "blossom";
    const anim = ANIM_FOR[key] || "";
    return `<svg class="sw-ic anim-${anim}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[key]}</svg>`;
  }

  /* ---------- live mini scene preview inside each swatch ----------
     A tiny canvas fills each theme card and animates that theme's own
     particles (petals fall, snow drifts, bubbles rise, stars twinkle…),
     so the picker previews the real scene. Runs only while Settings is
     open — stopped on close — to spare the CPU on low-RAM machines. */
  const _rnd = (a, b) => a + Math.random() * (b - a);
  const mini = { running: false, items: [] };

  function miniPart(cv, sc, cols, seed) {
    const up = sc.dir === "up", tw = sc.dir === "twinkle";
    const small = sc.particle === "star" || sc.particle === "dust";
    return {
      x: Math.random() * cv.width,
      y: tw ? Math.random() * cv.height : seed ? Math.random() * cv.height : (up ? cv.height + 6 : -6),
      r: small ? _rnd(1, 2.4) : _rnd(2.4, 5),
      c: cols[(Math.random() * cols.length) | 0],
      vy: (up ? -1 : 1) * _rnd(0.25, 0.8), vx: _rnd(-0.3, 0.3),
      ph: Math.random() * 6.28, a: Math.random() * 6.28,
    };
  }
  function miniDraw(s) {
    const ctx = s.ctx;
    ctx.clearRect(0, 0, s.cv.width, s.cv.height);
    const t = s.sc.particle;
    for (const p of s.parts) {
      ctx.save(); ctx.translate(p.x, p.y);
      ctx.fillStyle = p.c; ctx.strokeStyle = p.c; ctx.globalAlpha = 0.9;
      if (t === "snow") {
        ctx.rotate(p.a); ctx.lineWidth = 1;
        for (let i = 0; i < 3; i++) { ctx.rotate(Math.PI / 3); ctx.beginPath(); ctx.moveTo(0, -p.r); ctx.lineTo(0, p.r); ctx.stroke(); }
      } else if (t === "bubble") {
        ctx.globalAlpha = 0.6; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(0, 0, p.r, 0, 7); ctx.stroke();
      } else if (t === "star") {
        ctx.globalAlpha = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(p.ph)); ctx.beginPath(); ctx.arc(0, 0, p.r, 0, 7); ctx.fill();
      } else if (t === "ember") {
        ctx.shadowBlur = 6; ctx.shadowColor = p.c; ctx.beginPath(); ctx.arc(0, 0, p.r * 0.7, 0, 7); ctx.fill();
      } else if (t === "petal" || t === "leaf") {
        ctx.rotate(p.a); ctx.beginPath(); ctx.ellipse(0, 0, p.r * 0.7, p.r, 0, 0, 7); ctx.fill();
      } else { ctx.globalAlpha = 0.55; ctx.beginPath(); ctx.arc(0, 0, p.r, 0, 7); ctx.fill(); }
      ctx.restore();
    }
  }
  function miniTick() {
    if (!mini.running) return;
    for (const s of mini.items) {
      for (const p of s.parts) {
        p.ph += 0.05; p.a += 0.02;
        if (s.sc.dir !== "twinkle") { p.y += p.vy; p.x += p.vx + Math.sin(p.ph) * 0.4; }
        const out = s.sc.dir === "up" ? p.y < -6 : p.y > s.cv.height + 6;
        if (out || p.x < -8 || p.x > s.cv.width + 8) Object.assign(p, miniPart(s.cv, s.sc, s.cols, false));
      }
      miniDraw(s);
    }
    requestAnimationFrame(miniTick);
  }
  function miniStart() {
    mini.items = [];
    document.querySelectorAll(".swatch").forEach((sw) => {
      const cv = sw.querySelector(".swprev"); if (!cv) return;
      const id = sw.dataset.theme;
      const theme = id === "auto" ? THEMES[state.resolved] : THEMES[id];
      if (!theme) return;
      cv.width = sw.clientWidth || 160; cv.height = sw.clientHeight || 92;
      const n = Math.max(8, Math.round(cv.width * cv.height / 1400));
      const parts = Array.from({ length: n }, () => miniPart(cv, theme.scene, theme.particles, true));
      mini.items.push({ cv, ctx: cv.getContext("2d"), sc: theme.scene, cols: theme.particles, parts });
    });
    if (!mini.running) { mini.running = true; requestAnimationFrame(miniTick); }
  }
  function miniStop() { mini.running = false; mini.items = []; }

  /* ---------- settings modal ---------- */
  function buildSettings() {
    const wrap = document.getElementById("settings");
    if (!wrap) return;
    const autoCard = `
      <div class="swatch ${state.theme === "auto" ? "on" : ""}" data-theme="auto">
        <canvas class="swprev"></canvas>
        <span class="tick">${window.svg ? window.svg("check") : "✓"}</span>
        <div class="swhead">
          <span class="swicon" style="color:#fb7185">${svgIcon("auto")}</span>
          <div class="dots"><i style="background:#fb7185"></i><i style="background:#38bdf8"></i><i style="background:#fb923c"></i></div>
        </div>
        <div class="nm">Auto</div><div class="ds">Follows time of day</div>
      </div>`;
    const themeCards = autoCard + Object.entries(THEMES).map(([id, t]) => `
      <div class="swatch ${id === state.theme ? "on" : ""}" data-theme="${id}">
        <canvas class="swprev"></canvas>
        <span class="tick">${window.svg ? window.svg("check") : "✓"}</span>
        <div class="swhead">
          <span class="swicon" style="color:${t.dots[0]}">${svgIcon(id)}</span>
          <div class="dots">${t.dots.map((d) => `<i style="background:${d}"></i>`).join("")}</div>
        </div>
        <div class="nm">${t.name}</div><div class="ds">${t.desc}</div>
      </div>`).join("");

    wrap.querySelector(".setbody").innerHTML = `
      <div class="setsec">
        <h4>Theme &amp; scene</h4>
        <div class="swatches" id="swatches">${themeCards}</div>
      </div>
      <div class="setsec">
        <h4>Background</h4>
        <div class="switchrow">
          <div class="lbl"><div class="t">Particle animation</div><div class="s">Petals, snow, leaves, bubbles, embers, stars…</div></div>
          <div class="tgl ${state.bg.particles ? "on" : ""}" data-bg="particles"></div>
        </div>
        <div class="switchrow">
          <div class="lbl"><div class="t">Scenery</div><div class="s">Trees, fish, waves & fireflies where the theme has them</div></div>
          <div class="tgl ${state.bg.scenery ? "on" : ""}" data-bg="scenery"></div>
        </div>
        <div class="rangerow">
          <div class="lbl"><div class="t">Density</div><div class="s">How busy the animation is</div></div>
          <input type="range" id="intensity" min="0.3" max="1.6" step="0.1" value="${state.bg.intensity}">
        </div>
      </div>
      <div class="setsec">
        <h4>Using Sakura — instructions &amp; policies</h4>
        <div class="policy">
          <p><b>What Sakura can do.</b> Sakura is an autonomous local agent. It can open apps,
          find, read, create and delete files, run terminal commands, browse and search the web,
          create documents, schedule tasks, and control your screen — all on <b>this machine</b>.</p>

          <p><b>Autonomy levels</b> (set in the AI Core panel):</p>
          <ul>
            <li><b>Locked</b> — read-mostly. Shell and file writes are off. Safest.</li>
            <li><b>Trusted</b> (recommended) — full capability; only genuinely destructive
            actions (delete, shutdown, send email, risky commands) ask you once.</li>
            <li><b>Unleashed</b> — maximum freedom; nothing is gated. Use only when you fully
            trust the task.</li>
          </ul>

          <p><b>Be cautious about:</b></p>
          <ul>
            <li>Deleting files or folders — deletions may be permanent. Read the confirmation.</li>
            <li>Running commands or scripts you don't understand, especially from the web.</li>
            <li>Sharing passwords, secrets or financial details — treat prompts like a public note.</li>
            <li>"Unleashed" mode on unfamiliar tasks — it won't ask before acting.</li>
            <li>Web results can be wrong — verify anything important before you rely on it.</li>
          </ul>

          <p><b>Your controls.</b> Every risky action shows an <b>Authorize / Deny</b> prompt.
          Performance, GPU, RAM and CPU usage are tuned <b>automatically</b> to keep your machine
          stable — there's nothing you need to configure. Your chats and learned facts stay
          <b>local</b> to this computer; use <b>New chat</b> to start fresh or <b>Recent chats</b>
          to reopen a past conversation.</p>
        </div>
      </div>`;

    wrap.querySelectorAll(".swatch").forEach((s) => s.onclick = () => {
      const id = s.dataset.theme;
      applyTheme(id);
      wrap.querySelectorAll(".swatch").forEach((x) => x.classList.toggle("on", x === s));
      const label = id === "auto" ? "Auto (" + THEMES[state.resolved].name + ")" : THEMES[id].name;
      if (window.toast) window.toast("Theme: " + label);
    });
    wrap.querySelectorAll(".tgl[data-bg]").forEach((t) => t.onclick = () => {
      const k = t.dataset.bg; const v = !t.classList.contains("on");
      t.classList.toggle("on", v); window.SakuraTheme.setBg(k, v);
    });
    const range = wrap.querySelector("#intensity");
    if (range) range.oninput = (e) => window.SakuraTheme.setBg("intensity", parseFloat(e.target.value));
  }

  window.openSettings = function () {
    buildSettings();
    document.getElementById("settings").classList.add("open");
    requestAnimationFrame(miniStart);  // start previews once the modal is visible & sized
  };
  window.closeSettings = function () {
    document.getElementById("settings").classList.remove("open");
    miniStop();  // stop the preview loop to save CPU when closed
  };

  applyTheme(state.theme);
  document.addEventListener("DOMContentLoaded", applyBg);
})();
