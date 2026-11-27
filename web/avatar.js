/* Arcade 49 — Orb: awatar-przewodnik po stronie (w stylu ElevenLabs Orb). Bez bibliotek.
 *
 * Co robi:
 *  - chodzi (podskakuje) po ekranie; kolory losuje przy każdym wejściu z palety strony,
 *  - reaguje na losowanie (zdarzenia a49:mix / a49:ball / a49:done / a49:error z app.js),
 *  - odpowiada tylko na pytania o stronę i jej moduły (lokalna baza wiedzy poniżej),
 *  - opcjonalnie rozmawia głosem przez agenta ElevenLabs: wpisz jego ID w config.js (elevenAgentId).
 */
"use strict";

(() => {
  const CFG = window.LOSUJ6_CONFIG || {};
  const REDUCED_MOTION = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const KEY = "a49:avatar";
  const S = () => (typeof STATS !== "undefined" ? STATS : null);     // statystyki z app.js (globalne)
  const q = (sel, el = document) => el.querySelector(sel);
  const esc = t => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const fmtN = n => Number(n).toLocaleString("pl-PL");
  const TIER = { legenda: "Legenda", epicka: "Epicka", rzadka: "Rzadka", "zwykła": "Zwykła", underdog: "Underdog" };

  // ---------------------------------------------------------------- kolory: losowa para z palety strony
  const PALETTE_VARS = ["--pink", "--cyan", "--yellow", "--green", "--violet", "--red", "--orange", "--ice",
    "--t-legenda", "--t-epicka", "--t-rzadka", "--t-underdog"];
  function hexToRgb(h) {
    h = h.trim().replace("#", "");
    if (h.length === 3) h = h.split("").map(c => c + c).join("");
    const v = parseInt(h, 16);
    return Number.isNaN(v) ? null : [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  function pickColors() {
    const css = getComputedStyle(document.documentElement);
    const pool = PALETTE_VARS.map(v => hexToRgb(css.getPropertyValue(v))).filter(Boolean);
    if (pool.length < 2) return [[255, 43, 214], [32, 240, 255]];
    const a = Math.floor(Math.random() * pool.length);
    let b = Math.floor(Math.random() * (pool.length - 1));
    if (b >= a) b++;
    return [pool[a], pool[b]];
  }
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const rgba = (c, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

  // ---------------------------------------------------------------- baza wiedzy (tylko o stronie)
  const strip = t => t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
  const TOPICS = [
    {
      id: "automat", label: "Automat", go: "#automat",
      keys: ["automat", "beben", "maszyn", "losuj 6", "losuj6", "przycisk", "kupon", "tack", "osiagniec", "jak grac", "generator"],
      answer: () => `<b>Automat</b> to serce strony. Naciśnij <b>LOSUJ 6</b>: kule mieszają się w bębnie, a generator
        „Losuj 6 v 0.1” wybiera szóstkę. Generator waży liczby według historii, odrzuca kombinacje, które już padły
        od 1957 r., i nie dopuszcza 3 kolejnych liczb. Pod tacką widzisz statystyki każdej kuli, a Twoje ostatnie
        kupony zapisują się w „Twoje kupony”. Za ciekawe wyniki dostajesz osiągnięcia 🏆.`,
    },
    {
      id: "moc", label: "Moc statystyk", go: "#automat",
      keys: ["moc", "suwak", "statystyk", "waga", "wagi", "czysty los", "strength"],
      answer: () => `<b>Moc statystyk</b> (suwak 0–3) mówi, jak mocno historia wpływa na losowanie.
        <b>0</b> = czysty los, każda liczba ma tę samą wagę. <b>1</b> = waga proporcjonalna do liczby wystąpień.
        <b>3</b> = mocno faworyzuje „legendy”. To zmienia, <i>które</i> liczby dostajesz, a nie szansę na wygraną.`,
    },
    {
      id: "filtry", label: "Filtry ekspert", go: "#expert",
      keys: ["filtr", "ekspert", "pula", "kombinacj", "parzyst", "suma"],
      answer: () => `<b>Filtry · tryb ekspert</b> to 12 przełączników, które zawężają pulę kombinacji
        (np. suma, parzyste/nieparzyste, pary i trójki, „bez podobnych do historii”). Przy każdym filtrze widać,
        ile kombinacji zostaje i jaki % prawdziwych losowań by go przeszedł. Filtry o przeciwnych celach
        blokują się nawzajem. Nie zwiększają szansy: każda z 13 983 816 kombinacji jest tak samo prawdopodobna.`,
    },
    {
      id: "postacie", label: "Postacie", go: "#postacie",
      keys: ["postac", "karta", "karty", "player", "poziom", "lvl", "forma", "klasa", "legend", "epick", "rzadk", "zwykl", "underdog"],
      answer: () => {
        const s = S(), top = s && s.numbers[s.most_frequent[0] - 1];
        return `<b>Postacie</b>: każda z 49 liczb to bohater z kartą. <b>Poziom (LVL)</b> = ile razy padła
          od 1957 r., <b>forma</b> = ile razy w ostatnich ${s ? s.recent_window : 100} losowaniach (🔥 dobra, ❄️ słaba).
          Klasy wynikają z rankingu: 5 najczęstszych to <b>Legendy</b>, potem Epickie, Rzadkie, Zwykłe,
          a 5 najrzadszych to <b>Underdogi</b>.${top ? ` Obecny lider: <b>${top.number}</b> (LVL ${fmtN(top.count)}).` : ""}
          Kliknij kartę, żeby zobaczyć pełne statystyki.`;
      },
    },
    {
      id: "highscore", label: "High score", go: "#ranking",
      keys: ["high score", "highscore", "ranking", "top 10", "top10", "najczesc", "najrzadz", "wynik", "rekord"],
      answer: () => {
        const s = S();
        return `<b>High score</b> to dwie tablice wyników jak w salonie gier: <b>TOP 10 najczęściej</b>
          i <b>TOP 10 najrzadziej</b> padających liczb w całej historii.${s ? ` Dziś prowadzi
          <b>${s.most_frequent[0]}</b>, a na końcu stawki jest <b>${s.least_frequent[0]}</b>.` : ""}
          Kliknij wiersz, żeby otworzyć kartę liczby.`;
      },
    },
    {
      id: "ogienlod", label: "Ogień i lód", go: "#ogien-lod",
      keys: ["ogien", "ogniu", "lod", "zamroz", "gorac", "zimn", "status", "mapa ciepla", "ciepla", "heat"],
      answer: () => {
        const s = S();
        return `<b>Ogień &amp; lód</b> to „efekty statusu”. 🔥 <b>W ogniu</b> = liczby z największą liczbą
          trafień w ostatnich ${s ? s.recent_window : 100} losowaniach${s ? ` (teraz m.in. ${s.hot_recent.slice(0, 3).join(", ")})` : ""}.
          ❄️ <b>Zamrożone</b> = liczby, które najdłużej nie padły${s ? ` (np. ${s.longest_absent.slice(0, 3).join(", ")})` : ""}.
          Niżej jest <b>mapa ciepła</b> 49 liczb. Uwaga: „gorąca” liczba nie ma większej szansy w kolejnym losowaniu.`;
      },
    },
    {
      id: "kolory", label: "Kolory kul", go: "#ogien-lod",
      keys: ["kolor", "barw", "rozow", "zolt", "niebiesk", "fiolet"],
      answer: () => `Kolor kuli pochodzi z <b>mapy ciepła</b>: niebieskie/fioletowe padały rzadziej,
        różowe i pomarańczowe częściej, a żółte najczęściej. Ja mam kolory losowane przy każdym wejściu 🙂`,
    },
    {
      id: "api", label: "API i dane", go: "#api",
      keys: ["api", "endpoint", "pobierz", "pobrac", "csv", "json", "baza", "dane", "curl", "docs", "dokumentac", "render", "loot"],
      answer: () => {
        const s = S(), api = (CFG.apiBase || "").replace(/\/$/, "");
        return `<b>API i dane</b>: całą historię pobierzesz za darmo jako <b>CSV</b> lub <b>JSON</b> (sekcja „Loot”).
          Otwarte API${api ? ` (<code>${esc(api)}</code>)` : ""} ma m.in. <code>/api/draws</code>, <code>/api/stats</code>,
          <code>/api/losuj</code> i <code>/api/filters</code>, a dokumentację „na żywo” pod <code>/docs</code>.
          API stoi na darmowym serwerze, który usypia, więc pierwsze zapytanie po przerwie może trwać do minuty.
          ${s ? `Baza: ${fmtN(s.meta.draws)} losowań, ostatnie z ${s.meta.last_date}.` : ""}`;
      },
    },
    {
      id: "szanse", label: "Czy to zwiększa szanse?",
      keys: ["szans", "wygra", "prawdopodob", "przewid", "prognoz", "trafi", "pewn", "skuteczn", "oszuk", "system"],
      answer: () => `Nie. Przy uczciwym losowaniu każda kombinacja 6 z 49 ma tę samą szansę:
        <b>1 do 13 983 816</b>. Statystyki, moc i filtry zmieniają tylko to, <i>które</i> liczby wybierasz.
        Arcade 49 to zabawa ze statystyką, gra odpowiedzialnie (18+).`,
    },
    {
      id: "dane-zrodlo", label: "Skąd dane?",
      keys: ["skad", "zrodl", "1957", "historia", "lata", "2007", "luka", "aktualiz", "ostatnie losowanie"],
      answer: () => {
        const s = S(), m = s && s.meta;
        return `Dane to historia losowań Lotto od 1957 r.${m ? ` W bazie jest ${fmtN(m.draws)} losowań
          (do ${m.last_date}).${m.missing_ids && m.missing_ids.length ? " Brakuje losowań z 2007 r., więc nie są liczone." : ""}` : ""}
          Arcade 49 to niezależny projekt hobbystyczny, niezwiązany z Totalizatorem Sportowym.`;
      },
    },
    {
      id: "kawa", label: "Postaw kawę",
      keys: ["kawa", "kawe", "wesprz", "donat", "buy me", "coffee"],
      answer: () => `Jeśli automat Ci się podoba, możesz postawić autorowi kawę ☕ przyciskiem „Postaw mi kawę”
        pod automatem. Dzięki!`,
    },
    {
      id: "orb", label: "Kim jesteś?",
      keys: ["kim jestes", "kto ty", "orb", "awatar", "asystent", "czym jestes", "jak sie nazywasz", "pomoc", "help"],
      answer: () => `Jestem <b>Orb</b>, przewodnik po Arcade 49. Spaceruję po ekranie, kibicuję kulom przy losowaniu
        i odpowiadam na pytania o stronę: automat, postacie, high score, ogień i lód, API.
        ${CFG.elevenAgentId ? "Możesz też porozmawiać ze mną głosem 🎙." : ""}`,
    },
  ];
  const MENU = ["automat", "postacie", "highscore", "ogienlod", "api", "szanse"];

  function numberAnswer(n) {
    const s = S(), x = s && s.numbers[n - 1];
    if (!x) return `Liczba <b>${n}</b> ma swoją kartę w sekcji <b>Postacie</b>. Statystyki jeszcze się wczytują.`;
    const hot = s.hot_recent.includes(n), ice = s.longest_absent.includes(n);
    return `Postać <b>${n}</b>: klasa <b>${TIER[x.tier] || x.tier}</b>, LVL <b>${fmtN(x.count)}</b>
      (miejsce ${x.rank} z 49), forma ${x.recent_count} w ostatnich ${s.recent_window} losowaniach.
      ${x.draws_since === 0 ? "Padła w ostatnim losowaniu." : `Nie padła od ${x.draws_since} losowań.`}
      ${hot ? "🔥 Jest teraz w ogniu." : ""}${ice ? " ❄️ Jest wśród zamrożonych." : ""}`;
  }

  function answer(text) {
    const t = strip(text);
    const num = t.match(/(?:^|\D)([1-9]|[1-4]\d)(?!\d)/);
    const scored = TOPICS.map(tp => ({ tp, s: tp.keys.reduce((a, k) => a + (t.includes(k) ? k.length : 0), 0) }))
      .filter(x => x.s > 0).sort((a, b) => b.s - a.s);
    if (num && (!scored.length || /liczb|postac|kul|karta|numer/.test(t) || t.trim() === num[1]))
      return { html: numberAnswer(Number(num[1])), go: "#postacie" };
    if (scored.length) return { html: scored[0].tp.answer(), go: scored[0].tp.go, id: scored[0].tp.id };
    return {
      html: `Hmm, na to nie odpowiem 🙂 Jestem przewodnikiem po <b>Arcade 49</b> i rozmawiam tylko o tej stronie:
        automat, postacie, high score, ogień i lód, API. Wybierz temat poniżej albo zapytaj inaczej.`,
      off: true,
    };
  }

  // ---------------------------------------------------------------- DOM
  const root = document.createElement("div");
  root.className = "a49-avatar";
  root.innerHTML = `
    <div class="a49-shadow" aria-hidden="true"></div>
    <div class="a49-body">
      <div class="a49-bubble" role="status" aria-live="polite"></div>
      <button class="a49-orb" type="button" aria-haspopup="dialog" aria-controls="a49Panel"
        title="Orb — zapytaj mnie o stronę"><canvas aria-hidden="true"></canvas><span class="sr">Orb, przewodnik po stronie. Otwórz pytania.</span></button>
    </div>`;
  const panel = document.createElement("section");
  panel.className = "a49-panel";
  panel.id = "a49Panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Zapytaj Orba o stronę");
  panel.hidden = true;
  panel.innerHTML = `
    <header class="a49-head">
      <span class="a49-dot" aria-hidden="true"></span>
      <div><b>ORB</b><small>przewodnik po Arcade 49</small></div>
      <button class="a49-x" type="button" data-act="close" aria-label="Zamknij">✕</button>
    </header>
    <div class="a49-log" aria-live="polite"></div>
    <div class="a49-chips"></div>
    <form class="a49-form" autocomplete="off">
      <input type="text" name="q" maxlength="200" placeholder="Zapytaj o automat, postacie, API…" aria-label="Twoje pytanie">
      <button type="submit" aria-label="Wyślij">▶</button>
    </form>
    <div class="a49-foot">
      <button type="button" class="a49-voice" data-act="voice" hidden>🎙 Porozmawiaj głosem</button>
      <button type="button" class="a49-hide" data-act="hide">Schowaj Orba</button>
    </div>`;
  const restore = document.createElement("button");
  restore.className = "a49-restore";
  restore.type = "button";
  restore.title = "Przywołaj Orba";
  restore.innerHTML = `<span aria-hidden="true">◉</span> Orb`;
  restore.hidden = true;
  document.body.append(root, panel, restore);

  const body = q(".a49-body", root), bubble = q(".a49-bubble", root), orbBtn = q(".a49-orb", root);
  const shadow = q(".a49-shadow", root), cv = q("canvas", root), ctx = cv.getContext("2d");
  const log = q(".a49-log", panel), chips = q(".a49-chips", panel), form = q(".a49-form", panel);

  chips.innerHTML = MENU.map(id => {
    const t = TOPICS.find(x => x.id === id);
    return `<button type="button" class="a49-chip" data-topic="${id}">${t.label}</button>`;
  }).join("");

  // ---------------------------------------------------------------- stan
  let [C1, C2] = pickColors();
  const baseC2 = C2;
  let flash = null;                  // { rgb, t } — chwilowy kolor wylosowanej kuli
  let energy = 0.15;                 // 0..1: jak żywo wiruje orb
  let voiceLevel = 0;
  const size = () => (innerWidth < 640 ? 58 : 76);
  const st = { x: innerWidth - 90, y: innerHeight - 110, tx: 0, ty: 0, wait: 1.5, phase: 0, hop: 0, speed: 70,
    hover: false, mode: "wander", face: 1, squash: 0 };
  st.tx = st.x; st.ty = st.y;
  root.style.setProperty("--c1", rgba(C1));
  root.style.setProperty("--c2", rgba(C2));
  panel.style.setProperty("--c1", rgba(C1));
  panel.style.setProperty("--c2", rgba(C2));
  q(".a49-dot", panel).style.background = `linear-gradient(135deg, ${rgba(C1)}, ${rgba(C2)})`;

  // ---------------------------------------------------------------- dymek
  let bubbleTimer = 0;
  function say(html, ms = 4200) {
    if (!visible()) return;
    bubble.innerHTML = html;
    bubble.classList.add("on");
    clearTimeout(bubbleTimer);
    bubbleTimer = setTimeout(() => bubble.classList.remove("on"), ms);
  }
  const visible = () => !root.hidden;

  // ---------------------------------------------------------------- rysowanie orba (canvas 2D)
  const blobs = Array.from({ length: 5 }, (_, i) => ({
    c: i % 2, a: Math.random() * 6.28, sp: (0.4 + Math.random() * 0.6) * (i % 2 ? 1 : -1),
    orbit: 0.18 + Math.random() * 0.22, r: 0.45 + Math.random() * 0.3,
  }));
  let dpr = 1, px = 76;
  function fitCanvas() {
    px = size();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = cv.height = Math.round(px * dpr);
    cv.style.width = cv.style.height = px + "px";
    root.style.setProperty("--size", px + "px");
  }
  fitCanvas();

  function drawOrb(t) {
    const W = cv.width, R = W / 2;
    const c2 = flash ? mix(baseC2, flash.rgb, Math.min(1, flash.t * 3) * Math.min(1, flash.left * 2)) : C2;
    const lvl = Math.max(energy, voiceLevel);
    ctx.clearRect(0, 0, W, W);
    ctx.save();
    ctx.beginPath(); ctx.arc(R, R, R * (0.97 + lvl * 0.03), 0, Math.PI * 2); ctx.clip();
    // tło: ciemna mieszanka obu kolorów
    const base = ctx.createRadialGradient(R, R, 0, R, R, R);
    base.addColorStop(0, rgba(mix(C1, [11, 4, 32], 0.25), 1));
    base.addColorStop(1, rgba(mix(c2, [11, 4, 32], 0.6), 1));
    ctx.fillStyle = base; ctx.fillRect(0, 0, W, W);
    // wirujące plamy kolorów
    ctx.globalCompositeOperation = "source-over";
    for (const b of blobs) {
      const ang = b.a + t * b.sp * (0.6 + lvl * 2.4);
      const orb = b.orbit * (1 + lvl * 0.5);
      const x = R + Math.cos(ang) * orb * W, y = R + Math.sin(ang * 1.3) * orb * W;
      const rr = b.r * W * (0.8 + lvl * 0.35);
      const col = b.c ? c2 : C1;
      const g = ctx.createRadialGradient(x, y, 0, x, y, rr);
      g.addColorStop(0, rgba(col, 0.9)); g.addColorStop(0.5, rgba(col, 0.4)); g.addColorStop(1, rgba(col, 0));
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, W);
    }
    // połysk i cień brzegu (efekt kuli)
    ctx.globalCompositeOperation = "source-over";
    const hi = ctx.createRadialGradient(W * 0.34, W * 0.28, 0, W * 0.34, W * 0.28, W * 0.3);
    hi.addColorStop(0, "rgba(255,255,255,.5)"); hi.addColorStop(0.3, "rgba(255,255,255,.1)"); hi.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = hi; ctx.fillRect(0, 0, W, W);
    const rim = ctx.createRadialGradient(R, R, R * 0.62, R, R, R);
    rim.addColorStop(0, "rgba(0,0,0,0)"); rim.addColorStop(1, "rgba(10,4,30,.45)");
    ctx.fillStyle = rim; ctx.fillRect(0, 0, W, W);
    ctx.restore();
    root.style.setProperty("--glow", rgba(c2, 0.55 + lvl * 0.4));
  }

  // ---------------------------------------------------------------- ruch po ekranie
  const bounds = () => {
    const h = size() / 2 + 8;
    return { x0: h, x1: innerWidth - h, y0: Math.max(h + 70, 90), y1: innerHeight - h - 14 };
  };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function newTarget() {
    const b = bounds();
    // częściej trzymaj się brzegów ekranu, żeby nie zasłaniać treści
    const edge = Math.random() < 0.65;
    if (edge) {
      const side = Math.random();
      st.tx = side < 0.5 ? (side < 0.25 ? b.x0 + Math.random() * 90 : b.x1 - Math.random() * 90) : b.x0 + Math.random() * (b.x1 - b.x0);
      st.ty = side < 0.5 ? b.y0 + Math.random() * (b.y1 - b.y0) : b.y1 - Math.random() * 60;
    } else {
      st.tx = b.x0 + Math.random() * (b.x1 - b.x0);
      st.ty = b.y0 + Math.random() * (b.y1 - b.y0);
    }
    st.speed = 55 + Math.random() * 40;
  }
  function goTo(x, y, speed = 260) {
    const b = bounds();
    st.tx = clamp(x, b.x0, b.x1); st.ty = clamp(y, b.y0, b.y1); st.speed = speed; st.wait = 0;
  }
  function goToDrum() {
    const d = q("#drum");
    if (!d) return false;
    const r = d.getBoundingClientRect();
    if (r.bottom < 60 || r.top > innerHeight - 40) return false;     // bęben poza ekranem
    goTo(r.left + r.width * 0.95, r.top + r.height * 0.9, 320);
    return true;
  }

  let last = 0;
  function frame(ts) {
    const dt = Math.min(0.05, last ? (ts - last) / 1000 : 0.016);
    last = ts;
    const t = ts / 1000;
    energy += (0.15 - energy) * Math.min(1, dt * 0.9);
    if (flash) { flash.t += dt; flash.left -= dt; if (flash.left <= 0) flash = null; }
    if (voice.conv) {
      try { voiceLevel = Math.min(1, (voice.conv.getOutputVolume() || 0) * 2.2); } catch { voiceLevel = 0; }
    } else voiceLevel = 0;

    if (visible()) {
      const stop = st.hover || !panel.hidden || REDUCED_MOTION;
      const dx = st.tx - st.x, dy = st.ty - st.y, dist = Math.hypot(dx, dy);
      let moving = false;
      if (!stop && dist > 2) {
        const v = Math.min(dist, st.speed * dt);
        st.x += (dx / dist) * v; st.y += (dy / dist) * v;
        st.phase += v / 26;                              // jeden podskok ≈ 26 px drogi
        if (Math.abs(dx) > 4) st.face = dx > 0 ? 1 : -1;
        moving = true;
      } else if (!stop) {
        st.wait -= dt;
        if (st.wait <= 0 && st.mode === "wander") { newTarget(); st.wait = 2 + Math.random() * 4; }
      }
      const hopH = moving ? Math.abs(Math.sin(st.phase * Math.PI)) * (st.speed > 200 ? 16 : 10) : 0;
      st.hop += (hopH - st.hop) * Math.min(1, dt * 18);
      const landing = moving ? Math.max(0, 1 - Math.abs(Math.sin(st.phase * Math.PI)) * 4) : 0;
      st.squash += (landing - st.squash) * Math.min(1, dt * 20);
      const idle = moving ? 0 : Math.sin(t * 2.2) * 2.5;            // „oddychanie” w miejscu
      const sz = size();
      root.style.transform = `translate3d(${st.x - sz / 2}px, ${st.y - sz / 2}px, 0)`;
      body.style.transform = `translateY(${-st.hop + idle}px) scale(${1 + st.squash * 0.08}, ${1 - st.squash * 0.1}) rotate(${moving ? st.face * 6 : 0}deg)`;
      shadow.style.transform = `scale(${1 - st.hop / 40})`;
      shadow.style.opacity = String(0.55 - st.hop / 50);
      root.classList.toggle("flip", st.x > innerWidth - 200);
      root.classList.toggle("low", st.y < 230);
      drawOrb(t);
    }
    requestAnimationFrame(frame);
  }
  addEventListener("resize", () => {
    fitCanvas();
    const b = bounds();
    st.x = clamp(st.x, b.x0, b.x1); st.y = clamp(st.y, b.y0, b.y1);
    st.tx = clamp(st.tx, b.x0, b.x1); st.ty = clamp(st.ty, b.y0, b.y1);
  });
  if (REDUCED_MOTION) { const b = bounds(); st.x = st.tx = b.x1 - 10; st.y = st.ty = b.y1 - 10; }

  orbBtn.addEventListener("pointerenter", () => { st.hover = true; });
  orbBtn.addEventListener("pointerleave", () => { st.hover = false; });
  orbBtn.addEventListener("click", () => (panel.hidden ? openPanel() : closePanel()));

  // ---------------------------------------------------------------- panel pytań
  function addMsg(html, who = "orb") {
    const m = document.createElement("div");
    m.className = `a49-msg ${who}`;
    m.innerHTML = html;
    log.append(m);
    while (log.children.length > 30) log.firstChild.remove();
    log.scrollTop = log.scrollHeight;
    return m;
  }
  function reply(res, scroll = true) {
    const m = addMsg(res.html);
    if (res.go && !res.off) {
      const a = document.createElement("a");
      a.href = res.go; a.className = "a49-go"; a.textContent = "Pokaż na stronie ↓";
      a.addEventListener("click", () => { if (res.go === "#expert") { const d = q("#expert"); if (d) d.open = true; } });
      m.append(a);
    }
    energy = Math.max(energy, 0.7);
    if (scroll) say(res.off ? "Pytaj mnie o stronę 🙂" : "Już tłumaczę! 👇", 2200);
  }
  let greeted = false;
  function openPanel() {
    panel.hidden = false;
    orbBtn.setAttribute("aria-expanded", "true");
    bubble.classList.remove("on");
    if (!greeted) {
      greeted = true;
      addMsg(`Cześć! Jestem <b>Orb</b> 👋 Opowiem Ci o Arcade 49. Wybierz temat albo wpisz pytanie,
        np. „co to jest high score?” albo „opowiedz o liczbie 17”.`);
    }
    if (CFG.elevenAgentId) q(".a49-voice", panel).hidden = false;
    setTimeout(() => q("input", form).focus({ preventScroll: true }), 30);
  }
  function closePanel() {
    panel.hidden = true;
    orbBtn.setAttribute("aria-expanded", "false");
    orbBtn.focus({ preventScroll: true });
  }
  chips.addEventListener("click", e => {
    const b = e.target.closest("[data-topic]");
    if (!b) return;
    const tp = TOPICS.find(x => x.id === b.dataset.topic);
    addMsg(esc(tp.label), "me");
    reply({ html: tp.answer(), go: tp.go });
  });
  form.addEventListener("submit", e => {
    e.preventDefault();
    const inp = q("input", form), text = inp.value.trim();
    if (!text) return;
    inp.value = "";
    addMsg(esc(text), "me");
    if (voice.conv && voice.conv.sendUserMessage) {    // w trybie głosowym pytanie idzie do agenta
      try { voice.conv.sendUserMessage(text); return; } catch { /* lokalna odpowiedź niżej */ }
    }
    reply(answer(text));
  });
  panel.addEventListener("click", e => {
    const act = e.target.closest("[data-act]");
    if (!act) return;
    if (act.dataset.act === "close") closePanel();
    if (act.dataset.act === "hide") setShown(false);
    if (act.dataset.act === "voice") voice.toggle(act);
  });
  addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden) closePanel(); });

  function setShown(on) {
    root.hidden = !on;
    restore.hidden = on;
    if (!on) { panel.hidden = true; voice.stop(); }
    try { localStorage.setItem(KEY, on ? "on" : "off"); } catch { /* prywatne okno */ }
  }
  restore.addEventListener("click", () => { setShown(true); say("Wróciłem! 👋", 2000); });

  // ---------------------------------------------------------------- reakcje na losowanie
  const BALL_LINES = {
    legenda: n => `${n}! LEGENDA wchodzi do gry! 👑`,
    epicka: n => `${n} — epicka postać, stały bywalec!`,
    rzadka: n => `Kula ${n}. Solidna, jak w statystyce.`,
    "zwykła": n => `${n}! Zwykła, ale dziś błyszczy ✨`,
    underdog: n => `${n}?! Underdog wraca na scenę! 🐺`,
  };
  document.addEventListener("a49:mix", () => {
    energy = 1;
    st.mode = "drum";
    if (!goToDrum()) goTo(st.x, st.y);
    say(["Mieszamy! 🌀", "Kręć bębnem! 🎰", "Trzymam kciuki… których nie mam 😄"][Math.floor(Math.random() * 3)], 2200);
    voice.context("Użytkownik nacisnął LOSUJ 6, kule się mieszają.");
  });
  document.addEventListener("a49:ball", e => {
    const b = e.detail;
    flash = { rgb: b.rgb, t: 0, left: 1.4 };
    energy = 1;
    st.squash = 1;
    let line = (b.tier && BALL_LINES[b.tier]) ? BALL_LINES[b.tier](b.n) : `Kula ${b.n}!`;
    if (b.hot) line += " 🔥 W ogniu!";
    else if (b.ice) line += " ❄️ Odmrożona!";
    say(`<span class="a49-ballnum" style="--bc:${rgba(b.rgb)}">${b.n}</span> ${line}`, 1900);
    voice.context(`Wypadła kula ${b.n}${b.tier ? ` (klasa ${TIER[b.tier]})` : ""}${b.hot ? ", jest w ogniu" : ""}${b.ice ? ", była zamrożona" : ""}.`);
  });
  document.addEventListener("a49:done", e => {
    const d = e.detail;
    const legends = d.balls.filter(b => b.tier === "legenda").length;
    const unders = d.balls.filter(b => b.tier === "underdog").length;
    let line = d.fresh ? "Takiej szóstki jeszcze nie było! 🆕" : "Gotowe! 🎉";
    if (legends >= 2) line = `Drużyna legend: ${legends}! 👑`;
    else if (unders >= 2) line = `Ekipa underdogów: ${unders}! 🐺`;
    setTimeout(() => say(`${line}<br><small>suma ${d.sum} · ${d.numbers.join(" · ")}</small>`, 5200), 500);
    setTimeout(() => { st.mode = "wander"; st.wait = 3; }, 2500);
    voice.context(`Losowanie zakończone: ${d.numbers.join(", ")}, suma ${d.sum}.`);
  });
  document.addEventListener("a49:error", () => {
    energy = 0.6;
    st.mode = "wander";
    say("Ups, automat API śpi 😴 Spróbuj za chwilę.", 3800);
  });

  // ---------------------------------------------------------------- komentarze przy przewijaniu (raz na sekcję)
  const SECTION_HINTS = {
    postacie: "To Postacie! Każda liczba ma swoją kartę 🃏",
    ranking: "High score: kto prowadzi w historii? 🏆",
    "ogien-lod": "Ogień i lód: kto gorący, kto zamrożony 🔥❄️",
    api: "Tu pobierzesz całą bazę za darmo 💾",
  };
  const seen = new Set();
  const io = new IntersectionObserver(es => es.forEach(en => {
    const id = en.target.id;
    if (en.isIntersecting && SECTION_HINTS[id] && !seen.has(id) && panel.hidden && st.mode === "wander") {
      seen.add(id);
      say(SECTION_HINTS[id] + "<br><small>Kliknij mnie, wyjaśnię więcej.</small>", 4200);
    }
  }), { threshold: 0.35 });
  Object.keys(SECTION_HINTS).forEach(id => { const el = document.getElementById(id); if (el) io.observe(el); });

  // ---------------------------------------------------------------- głos: agent ElevenLabs (opcjonalnie)
  const voice = {
    conv: null, busy: false,
    async toggle(btn) {
      if (this.conv) return this.stop();
      if (this.busy || !CFG.elevenAgentId) return;
      this.busy = true;
      btn.textContent = "⏳ Łączę…";
      try {
        const { Conversation } = await import("https://esm.sh/@elevenlabs/client");
        this.conv = await Conversation.startSession({
          agentId: CFG.elevenAgentId,
          connectionType: "webrtc",
          onMessage: ({ message, source }) => {
            if (!message) return;
            addMsg(esc(message), source === "user" ? "me" : "orb");
            if (source !== "user") say(esc(message.length > 120 ? message.slice(0, 117) + "…" : message), 4500);
          },
          onDisconnect: () => this.ended(btn),
          onError: err => { addMsg(`Błąd połączenia głosowego: ${esc(err && err.message || err)}`); },
        });
        btn.textContent = "⏹ Zakończ rozmowę";
        btn.classList.add("live");
        addMsg("🎙 Słucham! Mów śmiało, pytaj o stronę.");
      } catch (err) {
        addMsg(`Nie udało się włączyć głosu (${esc(err && err.message || err)}). Sprawdź dostęp do mikrofonu.`);
        this.ended(btn);
      } finally { this.busy = false; }
    },
    stop() { if (this.conv) { try { this.conv.endSession(); } catch { /* już zamknięta */ } } },
    ended(btn) {
      this.conv = null;
      btn = btn || q(".a49-voice", panel);
      btn.textContent = "🎙 Porozmawiaj głosem";
      btn.classList.remove("live");
    },
    context(text) {
      if (this.conv && this.conv.sendContextualUpdate) { try { this.conv.sendContextualUpdate(text); } catch { /* ignoruj */ } }
    },
  };

  // ---------------------------------------------------------------- start
  let pref = "on";
  try { pref = localStorage.getItem(KEY) || "on"; } catch { /* prywatne okno */ }
  setShown(pref !== "off");
  requestAnimationFrame(frame);
  setTimeout(() => say("Cześć! Jestem Orb 👋<br><small>Kliknij mnie, opowiem o automacie.</small>", 5000), 1400);
})();
