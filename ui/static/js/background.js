/* ==========================================================================
   Sakura AI — animated background scene engine
   One full-screen canvas renders a different scene per theme:
     particle types  petal · snow · leaf · bubble · ember · star · dust
     scenery         fish + waves (ocean) · fireflies (forest) · comets (galaxy)
   Colors, particle type and scenery all come from the active theme via the
   'sakura:bg' event dispatched by themes.js. Kept lightweight for 8GB laptops.
   ========================================================================== */
(function () {
  const cv = document.getElementById("petals");
  if (!cv) return;
  const ctx = cv.getContext("2d");
  let W = 0, H = 0;
  let colors = ["#fbcfe8", "#f9a8d4", "#fb7185"];
  let scene = { particle: "petal", dir: "down", trees: "blossom" };
  let intensity = 1, particlesOn = true, sceneryOn = true;
  let parts = [], fish = [], flies = [], comets = [], wavePhase = 0, running = false;

  const rnd = (a, b) => a + Math.random() * (b - a);
  const pick = (arr) => arr[(Math.random() * arr.length) | 0];

  function count() {
    if (!particlesOn) return 0;
    const base = scene.particle === "star" ? 46000 : 34000;
    return Math.min(90, Math.round((W * H / base) * intensity));
  }

  function newPart(seed) {
    const up = scene.dir === "up";
    const tw = scene.dir === "twinkle";
    return {
      x: Math.random() * W,
      y: tw ? Math.random() * H : seed ? Math.random() * H : (up ? H + 20 : -20),
      r: scene.particle === "star" || scene.particle === "dust" ? rnd(1, 3.2) : rnd(5, 12),
      c: pick(colors),
      vy: (up ? -1 : 1) * rnd(0.4, 1.3),
      vx: rnd(-0.6, 0.6),
      a: Math.random() * Math.PI * 2, va: rnd(-0.03, 0.03),
      sway: rnd(0.5, 1.6), ph: Math.random() * Math.PI * 2,
      o: rnd(0.4, 0.95), life: rnd(0, 1),
    };
  }

  function newFish() {
    const dir = Math.random() < 0.5 ? 1 : -1;
    return {
      x: dir > 0 ? -40 : W + 40, y: rnd(H * 0.15, H * 0.9),
      s: rnd(10, 22), c: pick(colors), dir, v: rnd(0.5, 1.4),
      ph: Math.random() * Math.PI * 2,
    };
  }
  function newFly() {
    return { x: Math.random() * W, y: rnd(H * 0.35, H), r: rnd(1.2, 2.6),
      ph: Math.random() * Math.PI * 2, vx: rnd(-0.3, 0.3), vy: rnd(-0.25, 0.25) };
  }

  function resize() {
    W = cv.width = innerWidth; H = cv.height = innerHeight;
    parts = Array.from({ length: count() }, () => newPart(true));
    const wantFish = sceneryOn && scene.fish ? Math.min(9, Math.round(W / 220)) : 0;
    fish = Array.from({ length: wantFish }, newFish);
    const wantFly = sceneryOn && scene.fireflies ? Math.min(26, Math.round(W * H / 60000)) : 0;
    flies = Array.from({ length: wantFly }, newFly);
  }

  /* ---- particle shapes ---- */
  function drawPart(p) {
    ctx.save(); ctx.globalAlpha = p.o; ctx.fillStyle = p.c; ctx.strokeStyle = p.c;
    ctx.translate(p.x, p.y); ctx.rotate(p.a);
    const r = p.r, s = scene.particle;
    if (s === "petal") {
      ctx.beginPath(); ctx.moveTo(0, -r);
      ctx.bezierCurveTo(r * 0.9, -r * 0.9, r * 0.9, r * 0.5, 0, r);
      ctx.bezierCurveTo(-r * 0.9, r * 0.5, -r * 0.9, -r * 0.9, 0, -r);
      ctx.fill();
    } else if (s === "leaf") {
      ctx.beginPath(); ctx.moveTo(0, -r);
      ctx.quadraticCurveTo(r, 0, 0, r); ctx.quadraticCurveTo(-r, 0, 0, -r);
      ctx.fill();
      ctx.globalAlpha = p.o * 0.5; ctx.lineWidth = 0.8;
      ctx.beginPath(); ctx.moveTo(0, -r); ctx.lineTo(0, r); ctx.stroke();
    } else if (s === "snow") {
      ctx.lineWidth = 1.1; ctx.globalAlpha = p.o;
      for (let i = 0; i < 6; i++) {
        ctx.rotate(Math.PI / 3);
        ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, r); ctx.stroke();
      }
    } else if (s === "bubble") {
      ctx.globalAlpha = p.o * 0.6; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(0, 0, r, 0, 7); ctx.stroke();
      ctx.globalAlpha = p.o * 0.5;
      ctx.beginPath(); ctx.arc(-r * 0.3, -r * 0.3, r * 0.28, 0, 7); ctx.fill();
    } else if (s === "ember") {
      ctx.shadowBlur = 8; ctx.shadowColor = p.c;
      ctx.beginPath(); ctx.arc(0, 0, r * 0.4, 0, 7); ctx.fill();
    } else if (s === "star") {
      const tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(p.ph));
      ctx.globalAlpha = p.o * tw;
      ctx.beginPath(); ctx.arc(0, 0, r, 0, 7); ctx.fill();
    } else { // dust
      ctx.globalAlpha = p.o * 0.5;
      ctx.beginPath(); ctx.arc(0, 0, r, 0, 7); ctx.fill();
    }
    ctx.restore();
  }

  function drawFish(f) {
    ctx.save(); ctx.globalAlpha = 0.8; ctx.fillStyle = f.c;
    ctx.translate(f.x, f.y + Math.sin(f.ph) * 6); ctx.scale(f.dir, 1);
    ctx.beginPath(); ctx.ellipse(0, 0, f.s, f.s * 0.5, 0, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.moveTo(-f.s, 0); ctx.lineTo(-f.s * 1.6, -f.s * 0.5);
    ctx.lineTo(-f.s * 1.6, f.s * 0.5); ctx.closePath(); ctx.fill();
    ctx.globalAlpha = 0.9; ctx.fillStyle = "#0b1622";
    ctx.beginPath(); ctx.arc(f.s * 0.5, -f.s * 0.1, f.s * 0.1, 0, 7); ctx.fill();
    ctx.restore();
  }

  function drawWaves() {
    const rootStyle = getComputedStyle(document.documentElement);
    const c1 = rootStyle.getPropertyValue("--teal").trim() || "#38bdf8";
    for (let layer = 0; layer < 2; layer++) {
      ctx.save(); ctx.globalAlpha = 0.10 - layer * 0.03; ctx.fillStyle = c1;
      const base = H - 8 - layer * 26, amp = 16 + layer * 10, len = 260 + layer * 80;
      ctx.beginPath(); ctx.moveTo(0, H);
      for (let x = 0; x <= W; x += 12) {
        ctx.lineTo(x, base + Math.sin((x / len) + wavePhase + layer) * amp);
      }
      ctx.lineTo(W, H); ctx.closePath(); ctx.fill(); ctx.restore();
    }
  }

  function drawFly(f) {
    const glow = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(f.ph));
    ctx.save(); ctx.globalAlpha = glow; ctx.fillStyle = "#fde68a";
    ctx.shadowBlur = 10; ctx.shadowColor = "#fde68a";
    ctx.beginPath(); ctx.arc(f.x, f.y, f.r, 0, 7); ctx.fill(); ctx.restore();
  }

  function maybeComet() {
    if (scene.shooting && Math.random() < 0.006 && comets.length < 3) {
      comets.push({ x: rnd(0, W), y: rnd(0, H * 0.4), v: rnd(6, 11), len: rnd(80, 160), life: 1 });
    }
  }
  function drawComet(c) {
    ctx.save(); ctx.globalAlpha = c.life; ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(c.x - c.len, c.y - c.len * 0.4); ctx.stroke();
    ctx.restore();
  }

  function tick() {
    ctx.clearRect(0, 0, W, H);
    if (sceneryOn && scene.waves) drawWaves();
    wavePhase += 0.02;

    for (const p of parts) {
      p.ph += 0.02; p.a += p.va;
      if (scene.dir !== "twinkle") { p.y += p.vy; p.x += p.vx + Math.sin(p.ph) * p.sway; }
      else { p.ph += 0.04; }
      drawPart(p);
      const out = scene.dir === "up" ? p.y < -20 : p.y > H + 20;
      if (out || p.x < -40 || p.x > W + 40) Object.assign(p, newPart(false));
    }
    if (sceneryOn) {
      for (const f of fish) { f.x += f.dir * f.v; f.ph += 0.05; drawFish(f);
        if ((f.dir > 0 && f.x > W + 60) || (f.dir < 0 && f.x < -60)) Object.assign(f, newFish()); }
      for (const f of flies) { f.ph += 0.05; f.x += f.vx; f.y += f.vy;
        if (Math.random() < 0.02) { f.vx = rnd(-0.3, 0.3); f.vy = rnd(-0.25, 0.25); }
        if (f.x < 0 || f.x > W) f.vx *= -1; if (f.y < H * 0.3 || f.y > H) f.vy *= -1;
        drawFly(f); }
      maybeComet();
      for (const c of comets) { c.x += c.v; c.y += c.v * 0.4; c.life -= 0.012; drawComet(c); }
      comets = comets.filter((c) => c.life > 0 && c.x < W + 200);
    }
    requestAnimationFrame(tick);
  }

  function apply(detail) {
    if (detail.particles) colors = detail.particles;
    if (detail.scene) scene = detail.scene;
    if (detail.bg) {
      particlesOn = detail.bg.particles !== false;
      sceneryOn = detail.bg.scenery !== false;
      intensity = detail.bg.intensity ?? 1;
    }
    resize();
  }

  window.addEventListener("sakura:bg", (e) => apply(e.detail || {}));
  addEventListener("resize", resize);

  if (window.SakuraTheme) {
    const t = window.SakuraTheme.current();
    apply({ particles: t.particles, scene: t.scene, bg: window.SakuraTheme.state.bg });
  } else {
    resize();
  }
  if (!running) { running = true; requestAnimationFrame(tick); }
})();
