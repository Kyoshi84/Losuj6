/* Arcade 49 — logika strony. Bez bibliotek. */
"use strict";

// ------------------------------------------------------------------ konfiguracja
const params = new URLSearchParams(location.search);
const API = (params.get("api") || (window.LOSUJ6_CONFIG || {}).apiBase || "").replace(/\/$/, "");
const TIER_LABEL = { legenda: "Legenda", epicka: "Epicka", rzadka: "Rzadka", "zwykła": "Zwykła", underdog: "Underdog" };
const TIER_QUOTE = {
  legenda: "Widziana w bębnie częściej niż ktokolwiek. Publiczność zna ją na pamięć.",
  epicka: "Stały bywalec finałów. Rzadko zawodzi.",
  rzadka: "Solidna, przewidywalna — dokładnie tak, jak każe statystyka.",
  "zwykła": "Gra swoje, bez fajerwerków. Czeka na swoją chwilę.",
  underdog: "Rzadziej na scenie, ale każdy jej powrót to wydarzenie.",
};
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const store = {
  get(k, d) { try { const v = localStorage.getItem("a49:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("a49:" + k, JSON.stringify(v)); } catch { /* prywatne okno */ } },
};
let STATS = null;

// ------------------------------------------------------------------ pomocnicze
const colorClass = n => "c" + (n < 10 ? 1 : n < 20 ? 2 : n < 30 ? 3 : n < 40 ? 4 : 5);
const BALL_COLORS = ["#ffd23f", "#ff4fa8", "#3fd8ff", "#7dff5a", "#b57bff"];
const ballColor = n => BALL_COLORS[n < 10 ? 0 : n < 20 ? 1 : n < 30 ? 2 : n < 40 ? 3 : 4];
function ballEl(n, extra = "") {
  const d = document.createElement("div");
  d.className = `ball ${colorClass(n)} ${extra}`.trim();
  d.innerHTML = `<span>${n}</span>`;
  d.setAttribute("aria-label", `kula ${n}`);
  return d;
}
const fmt = n => n.toLocaleString("pl-PL");
const fmtDate = iso => iso ? new Date(iso + "T12:00:00").toLocaleDateString("pl-PL", { day: "numeric", month: "long", year: "numeric" }) : "—";
const plural = (n, one, few, many) => {
  const m10 = n % 10, m100 = n % 100;
  return n === 1 ? one : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? few : many;
};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

function toast(title, text) {
  const t = document.createElement("div");
  t.className = "toast";
  t.innerHTML = `<b>${title}</b>${text}`;
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 450); }, 4800);
}

// ------------------------------------------------------------------ dźwięk (8-bit, WebAudio)
const Sound = {
  on: store.get("sound", true), ctx: null,
  init() {
    const b = $("#soundBtn");
    const paint = () => { b.textContent = this.on ? "♪ ON" : "♪ OFF"; b.setAttribute("aria-pressed", String(this.on)); };
    paint();
    b.addEventListener("click", () => { this.on = !this.on; store.set("sound", this.on); paint(); if (this.on) this.beep(880, .08); });
  },
  beep(freq, dur = .1, type = "square", vol = .05, when = 0) {
    if (!this.on) return;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      const t0 = this.ctx.currentTime + when;
      const o = this.ctx.createOscillator(), g = this.ctx.createGain();
      o.type = type; o.frequency.setValueAtTime(freq, t0);
      g.gain.setValueAtTime(vol, t0); g.gain.exponentialRampToValueAtTime(.0001, t0 + dur);
      o.connect(g).connect(this.ctx.destination); o.start(t0); o.stop(t0 + dur + .02);
    } catch { /* brak audio */ }
  },
  coin() { [988, 1319].forEach((f, i) => this.beep(f, .12, "square", .05, i * .08)); },
  pop(i) { this.beep(440 + i * 110, .14, "triangle", .08); },
  win() { [523, 659, 784, 1047, 784, 1047].forEach((f, i) => this.beep(f, .14, "square", .045, i * .09)); },
  tick() { this.beep(1800 + Math.random() * 900, .02, "square", .015); },
  err() { [330, 220].forEach((f, i) => this.beep(f, .2, "sawtooth", .05, i * .18)); },
};

// ------------------------------------------------------------------ bęben z kulkami (fizyka 2D)
const Drum = (() => {
  const cv = $("#drum"), ctx = cv.getContext("2d");
  const W = 560, H = 560, C = { x: 280, y: 268 }, R = 236, r = 19, G = 1900;
  const PADDLES = 4, PADDLE_LEN = 62;
  const EXIT = { x: C.x + R * .64, y: C.y + R * .9 };
  let angle = 0, omega = .35, target = .35, balls = [], leaving = [], running = true, last = 0, tickAcc = 0;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function spawn(n, fromTop) {
    const a = Math.random() * Math.PI * 2, d = Math.random() * (R - r - 10);
    const b = fromTop
      ? { n, x: C.x + (Math.random() - .5) * 120, y: C.y - R + r + 8 + Math.random() * 30, vx: (Math.random() - .5) * 200, vy: 0 }
      : { n, x: C.x + Math.cos(a) * d, y: C.y + Math.sin(a) * d * .6 + R * .3, vx: 0, vy: 0 };
    balls.push(b);
  }
  for (let n = 1; n <= 49; n++) spawn(n, false);

  function step(dt) {
    omega += (target - omega) * Math.min(1, dt * 1.8);
    angle += omega * dt;
    const e = .55, mu = .12, churn = omega > 1.5 ? 2600 : 0;   // dmuchawa przy szybkich obrotach
    for (const b of balls) {
      b.vy += G * dt;
      if (churn) { b.vx += (Math.random() - .5) * churn * dt; b.vy += (Math.random() - .62) * churn * dt; }
      b.vx *= .999; b.vy *= .999;
      b.x += b.vx * dt; b.y += b.vy * dt;
      // ścianka bębna
      let dx = b.x - C.x, dy = b.y - C.y, d = Math.hypot(dx, dy);
      if (d > R - r) {
        const nx = dx / d, ny = dy / d;
        b.x = C.x + nx * (R - r); b.y = C.y + ny * (R - r);
        const vn = b.vx * nx + b.vy * ny;
        if (vn > 0) { b.vx -= (1 + e) * vn * nx; b.vy -= (1 + e) * vn * ny; }
        const tx = -ny, ty = nx, rimV = omega * (R - r), vt = b.vx * tx + b.vy * ty;
        b.vx += tx * (rimV - vt) * mu; b.vy += ty * (rimV - vt) * mu;
      }
      // łopatki obracające się z bębnem
      for (let k = 0; k < PADDLES; k++) {
        const a = angle + k * Math.PI * 2 / PADDLES, ca = Math.cos(a), sa = Math.sin(a);
        const x1 = C.x + ca * R, y1 = C.y + sa * R, x2 = C.x + ca * (R - PADDLE_LEN), y2 = C.y + sa * (R - PADDLE_LEN);
        const sx = x2 - x1, sy = y2 - y1, L2 = sx * sx + sy * sy;
        let t = ((b.x - x1) * sx + (b.y - y1) * sy) / L2; t = Math.max(0, Math.min(1, t));
        const px = x1 + sx * t, py = y1 + sy * t, ex = b.x - px, ey = b.y - py, ed = Math.hypot(ex, ey);
        const rad = r + 4;
        if (ed < rad && ed > 0) {
          const nx = ex / ed, ny = ey / ed;
          b.x = px + nx * rad; b.y = py + ny * rad;
          const pvx = -omega * (py - C.y), pvy = omega * (px - C.x);   // prędkość punktu łopatki
          const rel = (b.vx - pvx) * nx + (b.vy - pvy) * ny;
          if (rel < 0) { b.vx -= (1 + e) * rel * nx; b.vy -= (1 + e) * rel * ny; }
        }
      }
    }
    // zderzenia kul
    for (let i = 0; i < balls.length; i++) {
      const a = balls[i];
      for (let j = i + 1; j < balls.length; j++) {
        const b = balls[j], dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy;
        if (d2 >= 4 * r * r || d2 === 0) continue;
        const d = Math.sqrt(d2), nx = dx / d, ny = dy / d, ov = (2 * r - d) / 2;
        a.x -= nx * ov; a.y -= ny * ov; b.x += nx * ov; b.y += ny * ov;
        const rv = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
        if (rv < 0) { const im = -(1 + .85) * rv / 2; a.vx -= im * nx; a.vy -= im * ny; b.vx += im * nx; b.vy += im * ny; }
      }
    }
    // kule wypadające do rynny
    for (const l of leaving) l.t = Math.min(1, l.t + dt / l.dur);
    leaving = leaving.filter(l => { if (l.t >= 1) { l.done(); return false; } return true; });
    // grzechot przy szybkich obrotach
    if (omega > 1.5) { tickAcc += dt * omega * 2; if (tickAcc > 1.4) { tickAcc = 0; Sound.tick(); } }
  }

  function drawBall(x, y, n, s = 1) {
    const rr = r * s;
    const g = ctx.createRadialGradient(x - rr * .35, y - rr * .4, rr * .1, x, y, rr);
    const c = ballColor(n);
    g.addColorStop(0, "#ffffff"); g.addColorStop(.25, c); g.addColorStop(1, shade(c, -.45));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, rr, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,.88)"; ctx.beginPath(); ctx.arc(x, y, rr * .55, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#120832"; ctx.font = `700 ${Math.round(15 * s)}px "Chakra Petch", sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(n, x, y + 1);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    // szklany bęben — tło
    const bg = ctx.createRadialGradient(C.x - 60, C.y - 80, 20, C.x, C.y, R + 10);
    bg.addColorStop(0, "rgba(120,70,255,.25)"); bg.addColorStop(1, "rgba(10,3,30,.9)");
    ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(C.x, C.y, R + 6, 0, Math.PI * 2); ctx.fill();
    // tylne pręty klatki
    ctx.strokeStyle = "rgba(32,240,255,.12)"; ctx.lineWidth = 2;
    for (let k = 0; k < 12; k++) {
      const a = -angle * .5 + k * Math.PI / 6;
      ctx.beginPath(); ctx.moveTo(C.x + Math.cos(a) * R, C.y + Math.sin(a) * R);
      ctx.lineTo(C.x - Math.cos(a) * R, C.y - Math.sin(a) * R); ctx.stroke();
    }
    for (const b of balls) drawBall(b.x, b.y, b.n);
    for (const l of leaving) {
      const t = easeInOut(l.t), x = l.x + (EXIT.x - l.x) * t, y = l.y + (EXIT.y - l.y) * t - Math.sin(t * Math.PI) * 60;
      drawBall(x, y, l.n, 1 + t * .5);
    }
    // łopatki
    ctx.lineCap = "round";
    for (let k = 0; k < PADDLES; k++) {
      const a = angle + k * Math.PI * 2 / PADDLES, ca = Math.cos(a), sa = Math.sin(a);
      ctx.strokeStyle = "#ff2bd6"; ctx.lineWidth = 8; ctx.shadowColor = "#ff2bd6"; ctx.shadowBlur = 14;
      ctx.beginPath(); ctx.moveTo(C.x + ca * R, C.y + sa * R); ctx.lineTo(C.x + ca * (R - PADDLE_LEN), C.y + sa * (R - PADDLE_LEN)); ctx.stroke();
    }
    ctx.shadowBlur = 0;
    // przednie szprychy i oś
    ctx.strokeStyle = "rgba(255,255,255,.16)"; ctx.lineWidth = 3;
    for (let k = 0; k < 6; k++) {
      const a = angle + k * Math.PI / 3 + Math.PI / 6;
      ctx.beginPath(); ctx.moveTo(C.x, C.y); ctx.lineTo(C.x + Math.cos(a) * R, C.y + Math.sin(a) * R); ctx.stroke();
    }
    const hub = ctx.createRadialGradient(C.x - 6, C.y - 6, 2, C.x, C.y, 24);
    hub.addColorStop(0, "#fff"); hub.addColorStop(.4, "#b7a6ff"); hub.addColorStop(1, "#3b2a7a");
    ctx.fillStyle = hub; ctx.beginPath(); ctx.arc(C.x, C.y, 22, 0, Math.PI * 2); ctx.fill();
    // obręcz z neonem
    ctx.lineWidth = 12; ctx.strokeStyle = "#20f0ff"; ctx.shadowColor = "#20f0ff"; ctx.shadowBlur = 24;
    ctx.beginPath(); ctx.arc(C.x, C.y, R + 6, 0, Math.PI * 2); ctx.stroke(); ctx.shadowBlur = 0;
    ctx.lineWidth = 3; ctx.strokeStyle = "rgba(255,255,255,.7)";
    ctx.beginPath(); ctx.arc(C.x, C.y, R + 6, 0, Math.PI * 2); ctx.stroke();
    // nity na obręczy
    ctx.fillStyle = "#ffe14d";
    for (let k = 0; k < 24; k++) {
      const a = angle + k * Math.PI / 12;
      ctx.beginPath(); ctx.arc(C.x + Math.cos(a) * (R + 6), C.y + Math.sin(a) * (R + 6), 2.6, 0, Math.PI * 2); ctx.fill();
    }
    // odblask szkła
    ctx.strokeStyle = "rgba(255,255,255,.22)"; ctx.lineWidth = 10;
    ctx.beginPath(); ctx.arc(C.x, C.y, R - 22, Math.PI * 1.08, Math.PI * 1.42); ctx.stroke();
    // podstawa
    ctx.fillStyle = "#2a1366";
    ctx.beginPath(); ctx.moveTo(C.x - 70, C.y + R + 4); ctx.lineTo(C.x + 70, C.y + R + 4);
    ctx.lineTo(C.x + 110, H); ctx.lineTo(C.x - 110, H); ctx.closePath(); ctx.fill();
  }

  function frame(ts) {
    if (!running) return;
    const dt = Math.min(.033, (ts - (last || ts)) / 1000); last = ts;
    const sub = omega > 1.5 ? 4 : 2;
    for (let i = 0; i < sub; i++) step(dt / sub);
    draw();
    requestAnimationFrame(frame);
  }
  function start() { if (!running) { running = true; last = 0; requestAnimationFrame(frame); } }
  function stop() { running = false; }

  resize();
  addEventListener("resize", resize);
  new IntersectionObserver(es => es[0].isIntersecting ? start() : stop()).observe(cv);
  requestAnimationFrame(frame);

  return {
    spin(fast) { target = fast ? (REDUCED ? 1.6 : 2.7) : .35; },
    /** Wyjmuje kulę n z bębna; promise kończy się, gdy kula dotrze do rynny. */
    extract(n) {
      return new Promise(res => {
        const i = balls.findIndex(b => b.n === n);
        if (i < 0) return res();
        const [b] = balls.splice(i, 1);
        leaving.push({ n, x: b.x, y: b.y, t: 0, dur: REDUCED ? .2 : .6, done: res });
        if (!running) { leaving.at(-1).t = 1; res(); }
      });
    },
    refill() {
      const inDrum = new Set(balls.map(b => b.n));
      for (let n = 1; n <= 49; n++) if (!inDrum.has(n)) spawn(n, true);
    },
    shake() { for (const b of balls) { b.vx += (Math.random() - .5) * 500; b.vy -= Math.random() * 600; } },
  };
})();

function shade(hex, p) {
  const n = parseInt(hex.slice(1), 16);
  const f = c => Math.max(0, Math.min(255, Math.round(c + c * p)));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
}
const easeInOut = t => t < .5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;

// ------------------------------------------------------------------ generator (API)
async function callGenerator(strength) {
  const ctl = new AbortController();
  const kill = setTimeout(() => ctl.abort(), 90_000);
  const slow = setTimeout(() => setStatus("Budzę serwer API… darmowy hosting śpi, to potrwa do minuty"), 3500);
  try {
    const r = await fetch(`${API}/api/losuj?strength=${strength}&count=1`, { signal: ctl.signal, cache: "no-store" });
    if (!r.ok) throw new Error(`API odpowiedziało ${r.status}`);
    return (await r.json()).results[0];
  } finally { clearTimeout(kill); clearTimeout(slow); }
}
const setStatus = t => { $("#drumStatus").textContent = t; };

let busy = false;
async function play() {
  if (busy) return;
  busy = true;
  const btn = $("#losujBtn"), lever = $("#lever");
  btn.disabled = true; btn.classList.add("pressed"); lever.classList.add("pull");
  setTimeout(() => { btn.classList.remove("pressed"); lever.classList.remove("pull"); }, 380);
  Sound.coin();
  const strength = Number($("#strength").value);

  // przygotowanie: kule wracają do bębna, tacka pusta
  $$("#tray .slot").forEach(s => s.replaceChildren());
  Drum.refill(); Drum.shake(); Drum.spin(true);
  setStatus("Mieszanie…");
  $("#readout").innerHTML = `<p class="big">MIESZANIE KUL…</p><p class="muted">Generator Losuj 6 v 0.1 liczy wagi z ${STATS ? fmt(STATS.meta.draws) : "całej"} historii losowań.</p>`;

  try {
    const [res] = await Promise.all([callGenerator(strength), sleep(REDUCED ? 300 : 1800)]);
    setStatus("Losowanie!");
    const order = [...res.numbers].sort(() => Math.random() - .5);   // kule wypadają w losowej kolejności
    const slots = $$("#tray .slot");
    for (let i = 0; i < order.length; i++) {
      await Drum.extract(order[i]);
      Sound.pop(i);
      const pos = [...res.numbers].indexOf(order[i]);
      slots[pos].replaceChildren(ballEl(order[i], "drop"));
      await sleep(REDUCED ? 60 : 260);
    }
    Drum.spin(false);
    Sound.win();
    setStatus("Gotowe! " + res.numbers.join(" · "));
    showResult(res, strength);
  } catch (e) {
    Drum.spin(false); Sound.err();
    const msg = e.name === "AbortError" ? "Serwer API nie odpowiedział w 90 s." : e.message;
    setStatus("Błąd: automat API niedostępny");
    $("#readout").innerHTML = `<p class="big" style="color:var(--red)">GAME OVER?</p>
      <p>Nie udało się połączyć z generatorem (${msg}). Darmowy serwer mógł się jeszcze nie obudzić — spróbuj ponownie za chwilę.</p>`;
  } finally {
    busy = false; btn.disabled = false;
  }
}

function showResult(res, strength) {
  const sum = res.numbers.reduce((a, b) => a + b, 0);
  const even = res.numbers.filter(n => n % 2 === 0).length;
  const N = STATS ? Object.fromEntries(STATS.numbers.map(x => [x.number, x])) : {};
  const tiers = res.numbers.map(n => N[n] && N[n].tier);
  $("#readout").innerHTML = `
    <p class="big">${res.never_drawn_before ? "NOWA KOMBINACJA!" : "WYNIK"}</p>
    <p>${res.never_drawn_before ? "Ta szóstka nie padła ani razu od 1957 r." : ""}</p>
    <div class="stat-line">
      <span>suma <b>${sum}</b></span>
      <span>parzyste <b>${even}/6</b></span>
      <span>moc <b>×${res.strength_used}</b></span>
      <span>prób <b>${res.attempts}</b></span>
      <span>odrzucone z historii <b>${res.rejected_history}</b></span>
    </div>
    <div class="stat-line" style="margin-top:6px">${res.numbers.map(n =>
      `<span>${n}: <b>${fmt(res.frequencies[n])}×</b> ${N[n] ? "· " + TIER_LABEL[N[n].tier].toLowerCase() : ""}</span>`).join("")}</div>`;

  // osiągnięcia
  const ach = [];
  const legends = tiers.filter(t => t === "legenda").length, unders = tiers.filter(t => t === "underdog").length;
  if (legends >= 2) ach.push(["DRUŻYNA LEGEND", `${legends} legendy w jednym kuponie.`]);
  if (unders >= 2) ach.push(["UNDERDOG SQUAD", `${unders} underdogi — odważnie!`]);
  if (even === 6) ach.push(["PARZYSTA EKIPA", "Same parzyste liczby."]);
  if (even === 0) ach.push(["NIEPARZYSTA EKIPA", "Same nieparzyste liczby."]);
  if (sum >= 200) ach.push(["WYSOKI LOT", `Suma ${sum} — rzadko spotykana.`]);
  if (sum <= 100) ach.push(["NISKIE LOTY", `Suma tylko ${sum}.`]);
  if (STATS) {
    const hot = res.numbers.filter(n => STATS.hot_recent.includes(n)).length;
    const ice = res.numbers.filter(n => STATS.longest_absent.includes(n)).length;
    if (hot >= 2) ach.push(["W OGNIU", `${hot} liczby z najgorętszej dziesiątki.`]);
    if (ice >= 1) ach.push(["ODMRAŻANIE", "Masz liczbę z dziesiątki najdłużej nieobecnych."]);
  }
  if (res.rejected_history > 0) ach.push(["UNIK!", `Generator odrzucił ${res.rejected_history} kombinacji z historii.`]);
  if (!ach.length) ach.push(["NOWY KUPON", "Szóstka, której jeszcze nie było."]);
  ach.slice(0, 2).forEach(([t, x], i) => setTimeout(() => toast("🏆 " + t, x), 300 + i * 700));

  const sets = [{ n: res.numbers, s: strength, t: Date.now() }, ...store.get("sets", [])].slice(0, 8);
  store.set("sets", sets);
  renderSets(sets);
}

function renderSets(sets = store.get("sets", [])) {
  const ol = $("#mySets");
  if (!sets.length) return;
  ol.replaceChildren(...sets.map(s => {
    const li = document.createElement("li");
    s.n.forEach(n => li.append(ballEl(n)));
    const m = document.createElement("span");
    m.className = "muted"; m.style.fontSize = "12px";
    m.textContent = `moc ×${s.s} · ${new Date(s.t).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" })}`;
    li.append(m);
    return li;
  }));
}

// ------------------------------------------------------------------ statystyki
async function loadStats() {
  try {
    const r = await fetch("data/stats.json");
    if (!r.ok) throw new Error(r.status);
    STATS = await r.json();
  } catch {
    try { STATS = await (await fetch(`${API}/api/stats`)).json(); }
    catch { $("#cards").innerHTML = `<p class="muted">Nie udało się wczytać statystyk.</p>`; return; }
  }
  renderAll();
}

function renderAll() {
  const S = STATS, N = S.numbers;
  $$("[data-recent]").forEach(e => { e.textContent = S.recent_window; });

  if (S.latest) {
    $("#lastDate").textContent = `nr ${S.latest.draw_id} · ${fmtDate(S.latest.draw_date)}`;
    $("#lastBalls").replaceChildren(...S.latest.numbers.map(n => ballEl(n)));
  }
  renderCards();

  const max = Math.max(...N.map(x => x.count)), min = Math.min(...N.map(x => x.count));
  const row = (x, cls) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="pos">${String(x.rank).padStart(2, "0")}</span>`;
    li.append(ballEl(x.number));
    li.insertAdjacentHTML("beforeend",
      `<span class="bar"><i style="width:${(8 + 92 * (x.count - min) / (max - min)).toFixed(1)}%"></i></span><span class="val">${fmt(x.count)}</span>`);
    li.addEventListener("click", () => openCard(x.number));
    li.tabIndex = 0; li.addEventListener("keydown", e => { if (e.key === "Enter") openCard(x.number); });
    return li;
  };
  $("#topMost").replaceChildren(...S.most_frequent.map(n => row(N[n - 1])));
  $("#topLeast").replaceChildren(...S.least_frequent.map(n => row(N[n - 1])));
  $("#topLeast").classList.add("least");

  const chip = (n, label) => {
    const d = document.createElement("div");
    d.className = "chipball"; d.tabIndex = 0;
    d.append(ballEl(n)); d.insertAdjacentHTML("beforeend", `<span>${label}</span>`);
    d.addEventListener("click", () => openCard(n));
    d.addEventListener("keydown", e => { if (e.key === "Enter") openCard(n); });
    return d;
  };
  $("#hotBalls").replaceChildren(...S.hot_recent.map(n => chip(n, `${N[n - 1].recent_count}×`)));
  $("#iceBalls").replaceChildren(...S.longest_absent.map(n => chip(n, `${N[n - 1].draws_since} los.`)));

  $("#heat").replaceChildren(...N.map(x => {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = x.number;
    b.style.background = heatColor((x.count - min) / (max - min));
    b.title = `${x.number}: ${fmt(x.count)} wystąpień`;
    b.addEventListener("click", () => openCard(x.number));
    return b;
  }));

  const u = S.uniformity;
  if (u && u.p != null) {
    $("#fairness").innerHTML = `<b>Czy bęben jest uczciwy?</b> Test χ² zgodności z rozkładem równomiernym:
      χ² = ${u.chi2.toFixed(1)} przy ${u.df} stopniach swobody, p = ${u.p.toFixed(3)}.
      ${u.p > .05 ? "Różnice między liczbami mieszczą się w granicach przypadku — legendy i underdogi to głównie efekt losu, a nie „magii” liczb."
        : "Różnice są większe, niż wynikałoby z czystego przypadku — warto sprawdzić dane."}`;
  }
  const m = S.meta;
  const gaps = (m.missing_ids || []).map(([a, b]) => a === b ? a : `${a}–${b}`).join(", ");
  $("#dbInfo").innerHTML = `Baza: <b>${fmt(m.draws)}</b> losowań od ${fmtDate(m.first_date)} do ${fmtDate(m.last_date)}
    (numery ${m.first_id}–${m.last_id}${gaps ? `; brakuje: ${gaps}` : ""}). Pliki do pobrania działają zawsze;
    API na żywo służy do filtrowania i do generatora.`;
}

function heatColor(t) {
  const stops = [[43, 75, 255], [125, 60, 255], [255, 43, 214], [255, 138, 31], [255, 225, 77]];
  const x = t * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(x)), f = x - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${c.join(",")})`;
}

let tierFilter = "all";
function renderCards() {
  const N = STATS.numbers;
  const max = Math.max(...N.map(x => x.count)), min = Math.min(...N.map(x => x.count));
  const sort = $("#sortBy").value;
  const list = N.filter(x => tierFilter === "all" || x.tier === tierFilter).sort((a, b) =>
    sort === "count" ? b.count - a.count || a.number - b.number
      : sort === "form" ? b.recent_count - a.recent_count || a.number - b.number
        : sort === "since" ? (b.draws_since ?? 1e9) - (a.draws_since ?? 1e9) || a.number - b.number
          : a.number - b.number);
  $("#cards").replaceChildren(...list.map(x => {
    const c = document.createElement("button");
    c.type = "button";
    c.className = `card t-${x.tier}${x.tier === "legenda" ? " legend-glow" : ""}`;
    const form = x.recent_form >= 2 ? "🔥" : x.recent_form <= -2 ? "❄️" : "•";
    c.innerHTML = `<div class="card-top"></div>
      <div class="lvl">LVL ${fmt(x.count)}</div>
      <div class="bar"><i style="width:${(8 + 92 * (x.count - min) / (max - min)).toFixed(1)}%"></i></div>
      <div class="card-meta"><span>${form} forma ${x.recent_count}</span><span>#${x.rank}</span></div>
      <div class="card-meta"><span>ostatnio</span><span>${x.draws_since === 0 ? "w ostatnim" : x.draws_since + " los. temu"}</span></div>`;
    const top = $(".card-top", c);
    top.append(ballEl(x.number));
    top.insertAdjacentHTML("beforeend", `<span class="tier">${TIER_LABEL[x.tier]}</span>`);
    c.setAttribute("aria-label", `Liczba ${x.number}, ${TIER_LABEL[x.tier]}, ${x.count} wystąpień`);
    c.addEventListener("click", () => openCard(x.number));
    return c;
  }));
}

function openCard(n) {
  const x = STATS.numbers[n - 1], S = STATS;
  const exp100 = 600 / 49;
  const bars = x.per_decade, hi = Math.max(...bars, exp100) * 1.1;
  const bw = 520 / bars.length;
  const svg = `<svg class="decade-chart" viewBox="0 0 560 196" role="img" aria-label="Wystąpienia na 100 losowań w kolejnych dekadach">
    <line x1="30" x2="550" y1="${150 - 130 * exp100 / hi}" y2="${150 - 130 * exp100 / hi}" stroke="#a99bd6" stroke-dasharray="4 4"/>
    <line x1="34" x2="54" y1="182" y2="182" stroke="#a99bd6" stroke-dasharray="4 4"/>
    <text x="60" y="186" fill="#a99bd6" font-size="11">średnia przy równym losowaniu: ${exp100.toFixed(1)}</text>
    ${bars.map((v, i) => {
      const h = 130 * v / hi, X = 34 + i * bw;
      return `<rect x="${X}" y="${150 - h}" width="${bw - 12}" height="${h}" rx="4" fill="${v >= exp100 ? "#ff2bd6" : "#20f0ff"}"/>
        <text x="${X + (bw - 12) / 2}" y="${144 - h}" fill="#efe9ff" font-size="11" text-anchor="middle">${v.toFixed(1)}</text>
        <text x="${X + (bw - 12) / 2}" y="166" fill="#a99bd6" font-size="11" text-anchor="middle">${S.decades[i]}s</text>`;
    }).join("")}
  </svg>`;
  const body = $("#modalBody");
  body.className = "modal-in";
  body.style.setProperty("--t", `var(--t-${x.tier})`);
  body.innerHTML = `<div class="m-head"></div>
    <div class="m-grid">
      <div class="m-stat"><span>poziom (wystąpienia)</span><b>${fmt(x.count)}</b></div>
      <div class="m-stat"><span>ranking</span><b>#${x.rank} / 49</b></div>
      <div class="m-stat"><span>% losowań</span><b>${x.percent.toFixed(2)}%</b></div>
      <div class="m-stat"><span>vs oczekiwane</span><b>${x.deviation >= 0 ? "+" : ""}${x.deviation_pct}%</b></div>
      <div class="m-stat"><span>forma (${S.recent_window} los.)</span><b>${x.recent_count}×</b></div>
      <div class="m-stat"><span>ostatnio</span><b>${x.draws_since} los.</b></div>
    </div>
    <p class="label">NA 100 LOSOWAŃ W DEKADACH</p>${svg}
    <p class="muted" style="font-size:13px;margin:8px 0 0">Ostatnie wystąpienie: ${fmtDate(x.last_date)}. Oczekiwanie przy równym losowaniu: ${fmt(Math.round(x.expected))} wystąpień.</p>`;
  const head = $(".m-head", body);
  head.append(ballEl(n));
  head.insertAdjacentHTML("beforeend", `<div><span class="tier" style="background:var(--t)">${TIER_LABEL[x.tier]}</span>
    <h3 class="m-title" id="modalTitle">Liczba ${n}</h3><p class="m-quote">${TIER_QUOTE[x.tier]}</p></div>`);
  $("#modal").showModal();
  Sound.beep(660, .08, "triangle", .06);
}

// ------------------------------------------------------------------ start
function init() {
  Sound.init();
  $("#losujBtn").addEventListener("click", play);
  $("#lever").addEventListener("click", play);
  const s = $("#strength"), out = $("#strengthOut");
  s.value = store.get("strength", 1);
  const paint = () => { out.textContent = "×" + s.value; };
  paint();
  s.addEventListener("input", () => { paint(); store.set("strength", Number(s.value)); });
  $$("#tierFilter .chip").forEach(b => b.addEventListener("click", () => {
    $$("#tierFilter .chip").forEach(x => x.classList.toggle("on", x === b));
    tierFilter = b.dataset.tier; renderCards();
  }));
  $("#sortBy").addEventListener("change", renderCards);
  $("#modal").addEventListener("click", e => { if (e.target.id === "modal") e.target.close(); });

  $("#docsLink").href = `${API}/docs`;
  $("#curlExample").textContent = `curl "${API}/api/losuj?strength=1&count=3"\ncurl "${API}/api/draws?year=2025&format=csv" -o 2025.csv`;
  renderSets();
  loadStats();
  // budzimy darmowy serwer API od razu po wejściu, zanim ktoś naciśnie przycisk
  fetch(`${API}/api/health`, { cache: "no-store" }).catch(() => { });
}
init();
