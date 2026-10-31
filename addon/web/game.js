/* Powerhouse game window. Python pushes state with PH.init / PH.update;
   actions go back through pycmd("powerhouse:...") and return a fresh snapshot. */
(function () {
  "use strict";

  const A = window.PowerhouseArt;
  const fmt = A.fmt;
  const $ = (sel, el) => (el || document).querySelector(sel);

  let STATIC = null;
  let S = null;
  let SET = {};
  const ui = { tab: "pathways", buyQty: 1, sigs: {}, shownAtp: 0, raf: 0, busy: false };

  // ------------------------------------------------------------------ utils

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ""; }
  function an(word) { return (/^[aeiou]/i.test(word) ? "an " : "a ") + word; }
  function plural(n, one, many) { return `${fmt(n)} ${n === 1 ? one : (many || one + "s")}`; }
  const RCOL = { common: "var(--common)", rare: "var(--rare)", epic: "var(--epic)", legendary: "var(--legendary)" };

  function send(cmd, arg) {
    return new Promise((resolve) => {
      const full = "powerhouse:" + cmd + (arg !== undefined ? ":" + arg : "");
      const go = () => pycmd(full, (r) => resolve(r || {}));
      if (typeof pycmd === "function") go();
      else setTimeout(() => (typeof pycmd === "function" ? go() : resolve({})), 300);
    });
  }

  // tiny synth for feedback sounds (no audio files)
  let actx = null;
  function tone(freqs, opts) {
    if (!SET.sounds) return;
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      const t0 = actx.currentTime;
      (freqs || [660]).forEach((f, i) => {
        const o = actx.createOscillator(), g = actx.createGain();
        o.type = (opts && opts.type) || "sine";
        o.frequency.setValueAtTime(f, t0 + i * 0.07);
        g.gain.setValueAtTime(0.0001, t0 + i * 0.07);
        g.gain.exponentialRampToValueAtTime((opts && opts.vol) || 0.08, t0 + i * 0.07 + 0.015);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.07 + 0.22);
        o.connect(g).connect(actx.destination);
        o.start(t0 + i * 0.07);
        o.stop(t0 + i * 0.07 + 0.25);
      });
    } catch (e) { /* audio is optional */ }
  }
  const SOUND = {
    buy: () => tone([520, 780], { type: "triangle", vol: 0.06 }),
    pop: (r) => tone({ common: [600, 900], rare: [600, 900, 1200], epic: [500, 750, 1000, 1500], legendary: [523, 659, 784, 1047, 1319] }[r] || [700], { type: "sine", vol: 0.07 }),
    level: () => tone([523, 659, 784, 1047], { type: "triangle", vol: 0.07 }),
    no: () => tone([220, 180], { type: "square", vol: 0.03 }),
  };

  // ------------------------------------------------------------- lifecycle

  function init(staticData, snapshot, settings) {
    STATIC = staticData;
    SET = settings || {};
    document.body.classList.toggle("still", !!SET.reduce_motion);
    S = snapshot;
    ui.shownAtp = S.atp;
    ui.tab = SET.last_tab || "pathways";
    build();
    renderAll(true);
    if (!S.seenIntro) showGuide(true);
  }

  function update(snapshot, events, settings) {
    if (!STATIC) return;
    if (settings) {
      SET = settings;
      document.body.classList.toggle("still", !!SET.reduce_motion);
    }
    if (snapshot) S = snapshot;
    renderAll(false);
    if (events && events.length) handleEvents(events);
  }

  function build() {
    document.getElementById("app").innerHTML = `
      <header class="top">
        <div class="brand">${A.glyph(34)}<div>Powerhouse<small>The ATP clicker that runs on flashcards</small></div></div>
        <div class="counter" aria-live="polite">
          <div class="atp-big"><span id="atpNum">0</span><span class="unit"> ATP</span></div>
          <div class="atp-sub"><span><b id="perCard">0</b> per card</span><span class="fl">flow <b id="flowMult">×1.00</b></span></div>
        </div>
        <div class="top-right"><button class="help" data-act="guide" title="How to play" aria-label="How to play">?</button>
        <button class="level" data-act="tab" data-tab="stats" title="Level and XP">
          <span class="ring"><svg viewBox="0 0 50 50" width="50" height="50">
            <circle cx="25" cy="25" r="21" fill="none" stroke="rgba(110,168,255,.18)" stroke-width="5"/>
            <circle id="ringArc" cx="25" cy="25" r="21" fill="none" stroke="#6EA8FF" stroke-width="5" stroke-linecap="round" stroke-dasharray="0 132"/>
          </svg><b id="lvlNum">1</b></span>
          <span><div class="title" id="lvlTitle"></div><div class="xp" id="lvlXp"></div></span>
        </button></div>
      </header>
      <div class="grid">
        <aside class="left" id="left"></aside>
        <section class="right">
          <nav class="tabs" role="tablist" id="tabs"></nav>
          <div class="panel" id="panel" role="tabpanel"></div>
        </section>
      </div>
      <div class="toasts" id="toasts" aria-live="polite"></div>
      <div class="overlay" id="overlay" role="dialog" aria-modal="true"></div>`;
    document.addEventListener("click", onClick);
    // Anki closes the window on Esc. While a pop-up is open, Esc should only close
    // the pop-up, so catch it first (capture phase) and stop it there.
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("#overlay").classList.contains("show")) {
        e.preventDefault();
        e.stopPropagation();
        if (ui.guide) finishGuide();
        else if (!ui.busy) closeOverlay();
      }
    }, true);
  }

  function renderAll(first) {
    renderHeader(first);
    renderLeft();
    renderTabs();
    renderPanel();
  }

  // ----------------------------------------------------------------- header

  const LONG_UNITS = ["", "thousand", "million", "billion", "trillion", "quadrillion", "quintillion", "sextillion",
    "septillion", "octillion", "nonillion", "decillion"];
  function fmtLong(n) { // 1.2Qa -> "1.20 quadrillion", for hover text
    if (!isFinite(n) || n < 1e6) return Math.floor(n || 0).toLocaleString("en-US");
    const i = Math.min(Math.floor(Math.log10(n) / 3), LONG_UNITS.length - 1);
    return `${(n / Math.pow(1000, i)).toFixed(2)} ${LONG_UNITS[i]}`;
  }

  function renderHeader(first) {
    tweenAtp(S.atp, first);
    $(".atp-big").title = `${fmtLong(S.atp)} ATP`;
    $("#perCard").textContent = "+" + fmt(S.perCard);
    $("#perCard").title = `${fmtLong(S.perCard)} ATP per card`;
    $("#flowMult").textContent = "×" + (S.flow.mult || 1).toFixed(2);
    const L = S.level;
    $("#lvlNum").textContent = L.n;
    $("#lvlTitle").textContent = L.title;
    $("#lvlXp").textContent = `${fmt(L.into)} / ${fmt(L.need)} XP`;
    const circ = 2 * Math.PI * 21;
    $("#ringArc").setAttribute("stroke-dasharray", `${Math.max(0.5, L.pct * circ).toFixed(1)} ${circ.toFixed(1)}`);
  }

  function tweenAtp(to, instant) {
    cancelAnimationFrame(ui.raf);
    const el = $("#atpNum");
    const from = ui.shownAtp;
    if (instant || SET.reduce_motion || Math.abs(to - from) < 1e-6) {
      ui.shownAtp = to;
      el.textContent = fmt(to);
      return;
    }
    const t0 = performance.now(), dur = 600;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      ui.shownAtp = from + (to - from) * e;
      el.textContent = fmt(ui.shownAtp);
      if (k < 1) ui.raf = requestAnimationFrame(step);
    };
    ui.raf = requestAnimationFrame(step);
  }

  // ------------------------------------------------------------------- left

  function todayCount() {
    const t = S.today;
    return t.count === undefined ? t.n : t.count;
  }

  function mood() {
    const t = S.today;
    const n = todayCount();
    if (n === 0) return { face: "sleepy", line: "Waiting for today's first card." };
    if (t.goalHit || n >= t.goal) return { face: "happy", line: "Fully charged for today." };
    return { face: "happy", line: `${plural(t.goal - n, "card")} to today's goal.` };
  }

  function stageHtml(eq, ctx) {
    const st = A.stage(eq.stage);
    const specks = [];
    let seed = 7;
    const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
    for (let i = 0; i < 26; i++) {
      const x = rnd() * 100, y = rnd() * 100, r = 1.5 + rnd() * 5, c = st.specks[i % st.specks.length];
      specks.push(`<circle cx="${x}" cy="${y}" r="${r / 3}" fill="${c}" opacity="${0.25 + rnd() * 0.5}"/>`);
    }
    const gid = "stg-" + (ctx || "left");
    const bg = `<svg class="bg" viewBox="0 0 100 100" preserveAspectRatio="none">
      <defs><radialGradient id="${gid}" cx=".5" cy=".42" r=".7"><stop offset="0" stop-color="${st.bg[0]}"/><stop offset="1" stop-color="${st.bg[1]}"/></radialGradient></defs>
      <rect width="100" height="100" fill="url(#${gid})"/>${specks.join("")}</svg>`;
    return { html: bg, light: st.light };
  }

  // daughters from past divisions, drawn small in the background (up to six)
  const LINEAGE_SPOTS = [[14, 18], [74, 14], [10, 66], [80, 62], [44, 6], [52, 80]];
  function lineageHtml(n) {
    if (!n) return "";
    const spots = LINEAGE_SPOTS.slice(0, Math.min(n, LINEAGE_SPOTS.length));
    return `<div class="lineage" title="${plural(n, "daughter")} from past divisions">${spots.map(([x, y]) =>
      `<span style="left:${x}%;top:${y}%">${A.glyph(26)}</span>`).join("")}</div>`;
  }

  function renderLeft() {
    const eq = S.cosmetics.equipped;
    const m = mood();
    const fissions = (S.fission && S.fission.fissions) || 0;
    const growth = typeof S.growth === "number" ? S.growth : 1;
    const sig = JSON.stringify([eq, m.face, SET.reduce_motion, fissions]);
    const left = $("#left");
    if (ui.sigs.stage !== sig || !$("#stage")) {
      ui.sigs.stage = sig;
      const st = stageHtml(eq, "left");
      left.innerHTML = `
        <div class="stage-wrap">
          <div class="speech" id="speech" aria-live="polite"></div>
          <button class="stage ${st.light ? "light" : ""}" id="stage" data-act="poke" aria-label="Poke Mito">
            ${st.html}${lineageHtml(fissions)}
            <div class="mito-holder">${A.mito({ equipped: eq, size: 210, mood: m.face, animate: !SET.reduce_motion })}</div>
            <div class="scale" title="Drawn to scale: Mito is about 1 µm across"><i></i>250 nm</div>
            <div class="vignette"></div>
          </button>
          <div class="mito-name"><b>Mito</b>${fissions ? `<small>generation ${fissions + 1}</small>` : ""}<span id="moodLine"></span></div>
        </div>
        <div id="leftCards" class="stack"></div>`;
    }
    const stageEl = $("#stage");
    stageEl.style.setProperty("--g", growth.toFixed(3));
    stageEl.title = `Mito has grown ${Math.round(100 * growth)}% of the way to full size. He grows as his pathways make more ATP.`;
    $("#moodLine").textContent = m.line;
    $("#leftCards").innerHTML = todayCard() + questsCard() + fissionCard();
  }

  function noCountNote(t) {
    if (!t.x) return "";
    const why = [];
    if (t.xq) why.push(`${fmt(t.xq)} too quick`);
    if (t.xr) why.push(`${fmt(t.xr)} over a card's 4-a-day limit`);
    if (t.xs) why.push(`${fmt(t.xs)} on auto-advance`);
    return `<p class="note" title="Answers under a second that bunch together, a card's fifth answer in a day, and auto-advance's machine-steady rhythm don't earn anything.">${plural(t.x, "answer")} today didn't count (${why.join(", ")}).</p>`;
  }

  function todayCard() {
    const t = S.today, s = S.streak, r = S.rounds, d = S.dividend;
    const n = todayCount();
    const goalPct = Math.min(100, Math.round(100 * n / Math.max(1, t.goal)));
    const streakText = s.current ? `${s.current}-day streak` : "No streak yet";
    const left = Math.max(0, t.goal - (s.today_count === undefined ? n : s.today_count));
    let streakNote;
    if (s.today_done) streakNote = "Streak safe for today.";
    else if (s.current) streakNote = `Answer <b>${fmt(left)}</b> more, or finish your due reviews, to extend it.`;
    else streakNote = `Answer <b>${fmt(t.goal)}</b> cards, or finish your due reviews, to start one.`;
    const rounds = r.known ? `
      <div class="meter" style="margin-top:12px"><label><span>Due reviews done</span><b>${Math.round(100 * r.pct)}%</b></label>
        <div class="track rounds"><i style="width:${Math.round(100 * r.pct)}%"></i></div></div>` : "";
    const div = d.paid
      ? `<p class="note">Knowledge dividend collected for today.</p>`
      : d.banked > 0
        ? `<p class="note">Hit the goal to collect a dividend from your <b>${fmt(d.banked)}</b> mature cards (+${fmt(d.cards * S.perCard)} ATP).</p>`
        : "";
    return `<div class="card">
      <div class="meter"><label><span>Today's goal</span><b>${fmt(n)} / ${fmt(t.goal)}</b></label>
        <div class="track energy"><i style="width:${goalPct}%"></i></div></div>
      ${rounds}
      <div class="streak-row">
        <span class="flame">${A.icon("flame", 17)}${esc(streakText)}</span>
        ${s.freezes ? `<span class="ice" title="A freeze covers one missed day">${A.icon("freeze", 15)}${plural(s.freezes, "freeze")}</span>` : ""}
      </div>
      <p class="note">${streakNote}</p>${div}${noCountNote(t)}
    </div>`;
  }

  function questsCard() {
    if (!S.quests.length) return "";
    const rows = S.quests.map((q) => {
      const pct = Math.round(100 * q.progress / Math.max(1, q.target));
      return `<div class="quest ${q.done ? "done" : ""}">
        <span class="box">${q.done ? A.icon("check", 14) : ""}</span>
        <span><span class="label">${esc(q.label)}</span>${q.done ? "" : `<div class="mini"><i style="width:${pct}%"></i></div>`}</span>
        <span class="rw" title="Reward: ${an(q.reward)} vesicle">${q.done ? "" : `${fmt(q.progress)}/${fmt(q.target)}`} ${A.vesicle(q.reward, 18)}</span>
      </div>`;
    }).join("");
    const all = S.questsBonus ? "Bonus epic vesicle collected." : "Finish all three for a bonus epic vesicle.";
    return `<div class="card"><h3>Daily quests <small>New ones at rollover</small></h3>${rows}<p class="note">${all}</p></div>`;
  }

  function fissionCard() {
    const f = S.fission;
    if (!f.gain || f.suggest === false) return "";
    return `<div class="card fission-card"><h3>Fission is ready ${A.icon("split", 18)}</h3>
      <p class="note" style="margin-top:0">Mito has made enough ATP to divide. He copies his mtDNA and splits in two,
      and you carry on as the small daughter. You gain <b>+${f.gain} mtDNA</b> (+${Math.round(f.gain * f.bonusEach * 100)}% ATP forever).
      Your ATP, his pathways and their ×2 boosts restart; your study habits, other upgrades, enzymes, trophies and looks stay.</p>
      <button class="btn" style="margin-top:12px;width:100%" data-act="fission">Divide</button></div>`;
  }

  // ------------------------------------------------------------------- tabs

  function renderTabs() {
    const newLooks = S.cosmetics.new.length;
    const affordable = S.upgrades.some((u) => u.status === "available" && STATIC.upgrades[u.id].cost <= S.atp);
    const tabs = [
      ["pathways", "Pathways", ""],
      ["upgrades", "Upgrades", affordable ? `<span class="dot" title="Something is affordable"></span>` : ""],
      ["vesicles", "Vesicles", S.vesicles.length ? `<span class="count">${S.vesicles.length}</span>` : ""],
      ["codex", "Enzymes", ""],
      ["wardrobe", "Wardrobe", newLooks ? `<span class="count">${newLooks}</span>` : ""],
      ["trophies", "Trophies", ""],
      ["stats", "Stats", ""],
    ];
    const html = tabs.map(([id, label, extra]) => `<button class="tab" role="tab" data-act="tab" data-tab="${id}"
      aria-selected="${ui.tab === id}">${label}${extra}</button>`).join("");
    if (ui.sigs.tabs !== html) { ui.sigs.tabs = html; $("#tabs").innerHTML = html; }
  }

  function renderPanel(force) {
    const panel = $("#panel");
    const fn = { pathways: tabPathways, upgrades: tabUpgrades, vesicles: tabVesicles, codex: tabCodex,
      wardrobe: tabWardrobe, trophies: tabTrophies, stats: tabStats }[ui.tab] || tabPathways;
    const html = fn();
    // SVG art gets fresh internal ids on every render; ignore them when deciding whether anything changed
    const sig = ui.tab + html.replace(/(?<!data-)(id="|url\(#)[bmc]?(ph|v)\d+/g, "$1");
    if (!force && ui.sigs.panel === sig) return;
    const keep = ui.sigs.panelTab === ui.tab ? panel.scrollTop : 0;
    ui.sigs.panel = sig;
    ui.sigs.panelTab = ui.tab;
    panel.innerHTML = html;
    panel.scrollTop = keep;
  }

  function switchTab(tab) {
    ui.tab = tab;
    if (tab === "wardrobe" && S.cosmetics.new.length) send("clearnew");
    send("tab", tab);
    renderTabs();
    renderPanel(true);
  }

  // --------------------------------------------------------------- pathways

  function costFor(p, qty) {
    if (qty === 1) return p.cost;
    const g = STATIC.costGrowth;
    return p.cost * (Math.pow(g, qty) - 1) / (g - 1);
  }

  function tabPathways() {
    const qty = ui.buyQty;
    const rows = S.pathways.map((p) => {
      const info = STATIC.pathways[p.id];
      if (!p.unlocked) {
        const prev = STATIC.pathwayOrder[STATIC.pathwayOrder.indexOf(p.id) - 1];
        return `<div class="pw locked"><span class="ic">${A.icon("lock", 22)}</span>
          <div><h4>???</h4><div class="blurb">Buy your first ${esc(STATIC.pathways[prev].name)} to discover the next pathway.</div></div>
          <button class="buy" disabled>Locked<small>${fmt(p.cost)} ATP</small></button></div>`;
      }
      let n = qty === "max" ? p.maxQty : qty;
      let label, cost, disabled = false;
      if (qty === "max" && n === 0) { n = 1; }
      cost = costFor(p, n);
      label = qty === "max" ? `Buy ${fmt(n)}` : n === 1 ? "Buy" : `Buy ${n}`;
      if (cost > S.atp) disabled = true;
      const pct = S.perCard > 0 ? 100 * p.total / S.perCard : 0;
      const share = pct > 0 && pct < 1 ? "<1" : Math.round(pct);
      return `<div class="pw"><span class="ic">${A.icon(p.id, 26)}</span>
        <div>
          <h4>${esc(info.name)} <span class="owned">${p.owned ? "× " + fmt(p.owned) : ""}</span>${p.mult > 1 ? `<span class="mult">×${fmt(p.mult)} boosted</span>` : ""}</h4>
          <div class="yield">+${fmt(p.each)} per card each${p.owned ? ` <span>making +${fmt(p.total)} per card (${share}%)</span>` : ""}</div>
          <div class="blurb">${esc(info.blurb)}</div>
        </div>
        <button class="buy" data-act="buy-pathway" data-id="${p.id}" ${disabled ? "disabled" : ""}>${label}<small>${fmt(cost)} ATP</small></button>
      </div>`;
    }).join("");
    return `<div class="toolbar"><p>Pathways add ATP to every card you answer.</p>
      <div class="seg" role="group" aria-label="How many to buy">
        ${[1, 10, "max"].map((q) => `<button data-act="qty" data-qty="${q}" aria-pressed="${ui.buyQty === q}">${q === "max" ? "Max" : "×" + q}</button>`).join("")}
      </div></div>${rows}`;
  }

  // --------------------------------------------------------------- upgrades

  function upgradeIcon(u) {
    if (u.kind === "pathway") return `${A.icon(u.pathway, 22)}<span class="x2">×2</span>`;
    if (u.kind === "flow") return A.icon("flow", 22);
    return A.icon(u.id, 22);
  }

  function requirement(u) {
    if (u.kind === "pathway") {
      const owned = (S.pathways.find((p) => p.id === u.pathway) || {}).owned || 0;
      return `Own ${u.ownedNeeded} ${esc(STATIC.pathways[u.pathway].name)} (${owned}/${u.ownedNeeded})`;
    }
    return `Unlocks at ${fmt(u.answersNeeded)} cards answered (${fmt(S.answers)} so far)`;
  }

  function tabUpgrades() {
    const avail = [], locked = [], owned = [];
    for (const row of S.upgrades) {
      const u = STATIC.upgrades[row.id];
      if (!u) continue;
      if (row.status === "owned") owned.push(u);
      else if (row.status === "available") avail.push(u);
      else locked.push(u);
    }
    avail.sort((a, b) => a.cost - b.cost);
    locked.sort((a, b) => a.cost - b.cost);
    const tile = (u, isLocked) => `<div class="up ${u.kind} ${isLocked ? "locked" : ""}">
      <span class="ic">${upgradeIcon(u)}</span>
      <div><h4>${esc(u.name)}</h4><p>${esc(u.blurb)}</p>
      ${isLocked ? `<div class="req">${A.icon("lock", 14)}${requirement(u)}</div>`
        : `<button class="buy" data-act="buy-upgrade" data-id="${u.id}" ${u.cost > S.atp ? "disabled" : ""}>Buy<small>${fmt(u.cost)} ATP</small></button>`}
      </div></div>`;
    let html = "";
    html += `<div class="section-title">Available</div>`;
    html += avail.length ? `<div class="ups">${avail.map((u) => tile(u, false)).join("")}</div>`
      : `<p class="empty"><b>Nothing to buy right now</b>Own 10 of a pathway or keep answering cards to unlock more.</p>`;
    if (locked.length) html += `<div class="section-title">Coming up</div><div class="ups">${locked.slice(0, 8).map((u) => tile(u, true)).join("")}</div>`;
    if (owned.length) html += `<div class="section-title">Owned (${owned.length})</div><div class="owned-strip">${owned.map((u) =>
      `<span title="${esc(u.name)}">${u.kind === "pathway" ? A.icon(u.pathway, 18) : u.kind === "flow" ? A.icon("flow", 18) : A.icon(u.id, 18)}</span>`).join("")}</div>`;
    return html;
  }

  // --------------------------------------------------------------- vesicles

  function tabVesicles() {
    const v = S.vesicles;
    if (!v.length) {
      return `<div class="pool"><div class="empty"><b>No vesicles waiting</b>
        They turn up while you review: about one every 40 cards early in the day, and less often after that
        (half as often after 150 cards that day, a quarter after 500, an eighth after 1,000). Quests, trophies, clean sweeps and every fifth level add more.</div>
        <div class="membrane"><span>Plasma membrane</span></div></div>`;
    }
    const counts = {};
    v.forEach((x) => (counts[x.r] = (counts[x.r] || 0) + 1));
    const summary = ["legendary", "epic", "rare", "common"].filter((r) => counts[r]).map((r) => `${counts[r]} ${r}`).join(", ");
    const size = v.length > 40 ? 48 : v.length > 16 ? 58 : 72;
    const bubbles = v.slice(0, 120).map((x) => `<button class="bubble ${x.r}" data-act="open" data-id="${x.id}"
      aria-label="Open ${x.r} vesicle">${A.vesicle(x.r, size)}</button>`).join("");
    return `<div class="toolbar"><p>${plural(v.length, "vesicle")} waiting: ${summary}. Click one to open it.</p>
      <button class="btn secondary" data-act="open-all">Open all</button></div>
      <div class="pool">${bubbles}<div class="membrane"><span>Plasma membrane</span></div></div>`;
  }

  async function openOne(id) {
    if (ui.busy) return;
    ui.busy = true;
    const v = S.vesicles.find((x) => x.id === id) || S.vesicles[0];
    if (!v) { ui.busy = false; return; }
    const ov = $("#overlay");
    ov.innerHTML = `<div class="reveal"><div class="orb" id="orb">${A.vesicle(v.r, 170)}</div><div class="burst" id="burst"></div></div>`;
    showOverlay();
    const res = send("open", v.id);
    await wait(SET.reduce_motion ? 0 : 650);
    const orb = $("#orb");
    if (orb) orb.classList.add("fuse");
    burst(v.r);
    SOUND.pop(v.r);
    const r = await res;
    await wait(SET.reduce_motion ? 0 : 380);
    if (r.state) S = r.state;
    if (!r.ok) {
      closeOverlay();
      renderAll(false);
      toast("close", "var(--muted)", r.error || "That vesicle couldn't be opened.", "");
      ui.busy = false;
      return;
    }
    const loot = r.loot || {};
    const items = (loot.items || []).map((it) => itemHtml(it)).join("");
    const more = S.vesicles.length;
    ov.innerHTML = `<div class="reveal"><div class="loot">
        <div class="rarity-line" style="color:${RCOL[loot.r] || "#fff"}">${cap(loot.r || "")} vesicle</div>
        <div class="loot-atp">+${fmt(loot.atp || 0)} ATP<small>Unloaded into your stores</small></div>
        ${items}
      </div>
      <div class="actions">
        ${more ? `<button class="btn" data-act="open-next">Open next (${more})</button>` : ""}
        <button class="btn ${more ? "secondary" : ""}" data-act="close-overlay">Done</button>
      </div></div>`;
    const first = $(".actions .btn", ov);
    if (first) first.focus();
    renderAll(false);
    if (r.events) handleEvents(r.events);
    ui.busy = false;
  }

  async function openAll() {
    if (ui.busy || !S.vesicles.length) return;
    ui.busy = true;
    const ov = $("#overlay");
    ov.innerHTML = `<div class="reveal"><div class="orb">${A.vesicle("epic", 150)}</div><div class="burst" id="burst"></div></div>`;
    showOverlay();
    const res = send("openall");
    await wait(SET.reduce_motion ? 0 : 500);
    burst("legendary");
    SOUND.pop("legendary");
    const r = await res;
    if (r.state) S = r.state;
    const loots = r.loots || [];
    let atp = 0;
    const notable = [];
    const tally = { common: 0, rare: 0, epic: 0, legendary: 0 };
    let dupes = 0;
    for (const l of loots) {
      atp += l.atp || 0;
      tally[l.r] = (tally[l.r] || 0) + 1;
      for (const it of l.items || []) {
        if (it.k === "enzyme" && it.dup) { dupes += 1; atp += it.atp || 0; if (it.up) notable.push(it); } else notable.push(it);
      }
    }
    const tallyText = Object.entries(tally).filter(([, n]) => n).map(([k, n]) => `${n} ${k}`).join(", ");
    ov.innerHTML = `<div class="reveal"><div class="loot">
        <div class="rarity-line" style="color:var(--muted)">Opened ${plural(loots.length, "vesicle")}: ${tallyText}</div>
        <div class="loot-atp">+${fmt(atp)} ATP<small>${dupes ? `Including ATP from ${plural(dupes, "duplicate enzyme")}` : "Straight into your stores"}</small></div>
        ${notable.length ? `<div class="summary">${notable.map((it) => itemHtml(it, true)).join("")}</div>` : `<p class="note">No new enzymes or looks this time.</p>`}
      </div><div class="actions"><button class="btn" data-act="close-overlay">Done</button></div></div>`;
    const b = $(".actions .btn", ov);
    if (b) b.focus();
    renderAll(false);
    if (r.events) handleEvents(r.events);
    ui.busy = false;
  }

  function itemHtml(it, compact) {
    if (compact) return itemCompact(it);
    if (it.k === "enzyme") {
      const e = STATIC.enzymes[it.id];
      const set = STATIC.sets[e.set];
      if (it.dup) {
        const copies = S.codex[it.id] || 0;
        const need = STATIC.expressionCopies[e.rarity];
        const top = need.length;
        const nextAt = need[it.lvl];
        let line;
        if (it.up) line = `Expression level ${it.lvl} of ${top}: more enzyme, higher Vmax (Km stays put). +${(100 * STATIC.expressionBonus).toFixed(2)}% ATP, plus +${fmt(it.atp)} ATP.`;
        else if (it.lvl >= top) line = `Fully expressed already, so the proteasome broke this copy down for +${fmt(it.atp)} ATP.`;
        else line = `${plural(copies, "copy", "copies")} now; level ${it.lvl + 1} at ${nextAt}. Plus +${fmt(it.atp)} ATP.`;
        return `<div class="item ${e.rarity}"><span class="ic" style="color:${RCOL[e.rarity]}">${A.icon("enzyme", 28)}</span>
          <div><h4>${esc(e.name)} <span class="tag" style="background:rgba(255,255,255,.08);color:var(--muted)">${it.up ? "Level up" : "Duplicate"}</span></h4>
          <p>${line}</p></div></div>`;
      }
      return `<div class="item ${e.rarity}"><span class="ic" style="color:${RCOL[e.rarity]}">${A.icon("enzyme", 28)}</span>
        <div><h4>${esc(e.name)} <span class="tag" style="background:${RCOL[e.rarity]};color:#16112c">New ${e.rarity}</span></h4>
        <p>${esc(e.fact)}</p>${it.set_complete ? `<p style="color:var(--atp)">Set complete: ${esc(set.name)}. +5% ATP forever.</p>` : ""}</div></div>`;
    }
    if (it.k === "cosmetic") {
      const c = STATIC.cosmetics[it.id];
      const eq = Object.assign({}, S.cosmetics.equipped, { [c.slot]: it.id });
      return `<div class="item ${c.rarity}"><span class="ic">${A.mito({ equipped: eq, size: 54, animate: false })}</span>
        <div><h4>${esc(c.name)} <span class="tag" style="background:${RCOL[c.rarity]};color:#16112c">New look</span></h4>
        <p>Find it in the wardrobe.</p></div></div>`;
    }
    if (it.k === "freeze") {
      return `<div class="item rare"><span class="ic" style="color:var(--ice)">${A.icon("freeze", 28)}</span>
        <div><h4>Streak freeze</h4><p>Covers one missed day so your streak survives.</p></div></div>`;
    }
    return "";
  }

  function itemCompact(it) {
    let name = "", sub = "", rarity = "rare", ic = "";
    if (it.k === "enzyme") {
      const e = STATIC.enzymes[it.id];
      name = e.name; sub = it.dup ? `Expression level ${it.lvl}` : `New ${e.rarity} enzyme`; rarity = e.rarity;
      ic = `<span style="color:${RCOL[e.rarity]}">${A.icon("enzyme", 20)}</span>`;
      if (it.set_complete) sub = "Set complete! +5% ATP";
    } else if (it.k === "cosmetic") {
      const c = STATIC.cosmetics[it.id];
      name = c.name; sub = "New look"; rarity = c.rarity;
      ic = A.mito({ equipped: Object.assign({}, S.cosmetics.equipped, { [c.slot]: it.id }), size: 36, animate: false });
    } else if (it.k === "freeze") {
      name = "Streak freeze"; sub = "Covers a missed day";
      ic = `<span style="color:var(--ice)">${A.icon("freeze", 20)}</span>`;
    }
    return `<div class="item ${rarity}" title="${esc(it.k === "enzyme" ? STATIC.enzymes[it.id].fact : name)}">
      <span class="ic">${ic}</span><div><h4>${esc(name)}</h4><p style="color:${RCOL[rarity]}">${esc(sub)}</p></div></div>`;
  }

  function burst(r) {
    const b = $("#burst");
    if (!b || SET.reduce_motion) return;
    const colors = A.RARITY_COLORS[r] || A.RARITY_COLORS.common;
    let html = "";
    for (let i = 0; i < 26; i++) {
      const a = Math.random() * Math.PI * 2, d = 80 + Math.random() * 120;
      html += `<i style="--x:${Math.cos(a) * d}px;--y:${Math.sin(a) * d}px;background:${colors[i % 2]};left:${-4}px;top:${-4}px;animation-delay:${Math.random() * 0.08}s"></i>`;
    }
    b.innerHTML = html;
  }

  function showOverlay() {
    $("#overlay").classList.add("show");
  }

  function closeOverlay() {
    const ov = $("#overlay");
    ov.classList.remove("show");
    ov.innerHTML = "";
  }

  function wait(ms) { return new Promise((r) => setTimeout(r, ms)); }

  // ------------------------------------------------------------------ codex

  function exprLevel(copies, rarity) {
    return STATIC.expressionCopies[rarity].filter((need) => copies >= need).length;
  }

  function exprPips(copies, rarity) {
    const need = STATIC.expressionCopies[rarity];
    const lv = exprLevel(copies, rarity), top = need.length;
    const next = need[lv];
    const tip = lv >= top ? `Fully expressed (${copies} copies)` : `Expression level ${lv} of ${top}: ${copies} of ${next} copies for the next level`;
    let dots = "";
    for (let i = 1; i <= top; i++) dots += `<i class="${i <= lv ? "on" : ""}"></i>`;
    return `<span class="expr" title="${tip}">${dots}</span>`;
  }

  function tabCodex() {
    const have = S.codex;
    const total = STATIC.enzymeOrder.length;
    const got = STATIC.enzymeOrder.filter((id) => have[id]).length;
    const open = new Set(S.unlockedSets || STATIC.setOrder);
    const bonus = (100 * STATIC.expressionBonus * (S.expressionExtra || 0));
    const legMissing = STATIC.enzymeOrder.some((id) => STATIC.enzymes[id].rarity === "legendary" && !have[id]);
    let html = `<div class="toolbar"><p>${got} of ${total} enzymes collected. Each complete set adds +5% ATP; all six add +10% more.
      Duplicates raise an enzyme's expression level (rarer ones need fewer copies), and each level adds +${(100 * STATIC.expressionBonus).toFixed(2)}% ATP${bonus ? ` (now +${bonus.toFixed(2)}%)` : ""}.
      ${S.legendaryNext ? `<b class="pity">Your next legendary enzyme will be one you're missing.</b>`
        : legMissing ? `Legendaries have bad-luck protection: never more than ${STATIC.legendaryPity || 2} duplicates in a row while you're missing one.` : ""}</p></div>`;
    for (const setId of STATIC.setOrder) {
      const set = STATIC.sets[setId];
      const ids = STATIC.enzymeOrder.filter((id) => STATIC.enzymes[id].set === setId);
      const n = ids.filter((id) => have[id]).length;
      if (!open.has(setId)) {
        const daysLeft = (S.setUnlockDays || {})[setId] || 0;
        const levelOk = S.level.n >= set.unlockLevel;
        const when = levelOk && daysLeft > 0 ? `Arrives in ${plural(daysLeft, "day")}`
          : `Unlocks at level ${set.unlockLevel} (${esc(set.unlockTitle)})${daysLeft > 0 ? `, ${plural(daysLeft, "day")} from now at the earliest` : ""}`;
        html += `<div class="set locked"><header><h4>${A.icon("lock", 15)} ${esc(set.name)}</h4>
          <span>${when}</span></header>
          <div class="cards">${ids.map((id) => enzCard(id, have)).join("")}</div></div>`;
        continue;
      }
      html += `<div class="set"><header><h4>${esc(set.name)}</h4>
        <span class="${n === ids.length ? "done" : ""}">${n === ids.length ? "Complete: +5% ATP" : `${n}/${ids.length}`}</span></header>
        <div class="cards">${ids.map((id) => enzCard(id, have)).join("")}</div></div>`;
    }
    return html;
  }

  function enzCard(id, have) {
    const e = STATIC.enzymes[id];
    if (!have[id]) return `<div class="enz missing ${e.rarity}" style="border-color:${RCOL[e.rarity]}"><b>?</b><span>${cap(e.rarity)} enzyme</span></div>`;
    return `<div class="enz ${e.rarity}">${exprPips(have[id], e.rarity)}
      <h5><span class="gem" style="background:${RCOL[e.rarity]}"></span>${esc(e.name)}</h5><p>${esc(e.fact)}</p></div>`;
  }

  // --------------------------------------------------------------- wardrobe

  function sourceHint(c) {
    const src = c.source;
    if (src === "default") return "Starter";
    if (src === "drop") return "Found in vesicles";
    if (src.startsWith("level:")) return `Reach level ${src.split(":")[1]}`;
    if (src.startsWith("achievement:")) {
      const a = STATIC.achievements[src.split(":")[1]];
      return a ? `Trophy: ${a.name}` : "A trophy";
    }
    if (src.startsWith("pathway:")) return `Own ${STATIC.pathways[src.split(":")[1]].name}`;
    if (src.startsWith("fission:")) {
      const n = +src.split(":")[1];
      return n === 1 ? "Divide once" : `Divide ${n} times`;
    }
    return "";
  }

  function swatch(c) {
    if (c.slot === "skin") {
      const s = A.SKINS[c.id];
      return `<span class="sw" style="background:linear-gradient(135deg,${s.body[0]},${s.body[1]})"></span>`;
    }
    if (c.slot === "stage") {
      const st = A.stage(c.id);
      return `<span class="sw" style="background:radial-gradient(circle,${st.bg[0]},${st.bg[1]})"></span>`;
    }
    return `<span class="sw" style="background:${RCOL[c.rarity]};opacity:.85"></span>`;
  }

  function tabWardrobe() {
    const eq = S.cosmetics.equipped;
    const owned = new Set(S.cosmetics.owned);
    const isNew = new Set(S.cosmetics.new);
    const st = stageHtml(eq, "ward");
    const slots = [["skin", "Skin"], ["hat", "Hat"], ["face", "Face"], ["neck", "Neck"], ["stage", "Microscope view"]];
    const rows = slots.map(([slot, label]) => {
      const items = STATIC.cosmeticOrder.map((id) => STATIC.cosmetics[id]).filter((c) => c.slot === slot);
      const chips = items.map((c) => {
        const have = owned.has(c.id);
        return `<button class="chip" data-act="equip" data-id="${c.id}" aria-pressed="${eq[slot] === c.id}" ${have ? "" : "disabled"}
          title="${have ? (eq[slot] === c.id && slot !== "skin" && slot !== "stage" ? "Click to take it off" : "Wear it") : esc(sourceHint(c))}">
          ${have ? swatch(c) : `<span class="sw" style="display:flex;align-items:center;justify-content:center;color:var(--faint)">${A.icon("lock", 14)}</span>`}
          <span>${esc(c.name)}${have ? "" : `<span class="why"> ${esc(sourceHint(c))}</span>`}</span>
          ${isNew.has(c.id) ? `<span class="new">New</span>` : ""}</button>`;
      }).join("");
      return `<div class="slot"><h4>${label}</h4><div class="chips">${chips}</div></div>`;
    }).join("");
    return `<div class="wardrobe"><div class="preview">
        <div class="stage ${st.light ? "light" : ""}">${st.html}<div class="mito-holder">${A.mito({ equipped: eq, size: 180, animate: !SET.reduce_motion })}</div><div class="vignette"></div></div>
        <p class="note" style="text-align:center">${owned.size} of ${STATIC.cosmeticOrder.length} looks unlocked</p></div>
      <div>${rows}</div></div>`;
  }

  // --------------------------------------------------------------- trophies

  function tabTrophies() {
    const got = S.achievements;
    const n = Object.keys(got).length;
    const items = STATIC.achievementOrder.map((id) => {
      const a = STATIC.achievements[id];
      const have = !!got[id];
      if (!have && a.hidden) {
        return `<div class="tro locked"><span class="ic">${A.icon("lock", 18)}</span><div><h5>???</h5><p>A secret trophy.</p></div></div>`;
      }
      return `<div class="tro ${have ? "" : "locked"}"><span class="ic" style="${have ? `background:${RCOL[a.tier]}26;color:${RCOL[a.tier]}` : ""}">${A.icon("trophy", 19)}</span>
        <div><h5>${esc(a.name)}</h5><p>${esc(a.desc)}</p></div></div>`;
    }).join("");
    return `<div class="toolbar"><p>${n} of ${STATIC.achievementOrder.length} trophies. Each one adds +1% ATP and comes with a vesicle.</p></div>
      <div class="trophies">${items}</div>`;
  }

  // ------------------------------------------------------------------ stats

  function tabStats() {
    const st = S.stats, f = S.fission;
    const stat = (v, label) => `<div class="stat"><b>${v}</b><span>${label}</span></div>`;
    const parts = (S.multiplierParts || []).map(([name, m]) => `<tr><td>${esc(name)}</td><td>×${m.toFixed(2)}</td></tr>`).join("");
    const toggle = (key, label, sub) => `<div class="setting"><span>${label}${sub ? `<small>${sub}</small>` : ""}</span>
      <button class="toggle" role="switch" aria-checked="${!!SET[key]}" data-act="setting" data-key="${key}" aria-label="${esc(label)}"></button></div>`;
    const positions = [["bar", "Bottom bar (never covers cards)"], ["top-right", "Card corner, top right"], ["top-left", "Card corner, top left"], ["bottom-left", "Card corner, bottom left"]];
    return `
      <div class="statgrid">
        ${stat(fmt(S.answers), "cards answered with Powerhouse")}
        ${stat(fmt(S.atpAll), "ATP made, all time")}
        ${stat(fmt(st.best_day), "best day (cards)")}
        ${stat(fmt(S.streak.best), "best streak (days)")}
        ${stat(fmt(S.flow.best), "best flow")}
        ${stat(fmt(st.opened), "vesicles opened")}
        ${stat(fmt(st.sweeps), "clean sweeps")}
        ${stat(fmt(f.mtdna), "mtDNA from fission")}
      </div>
      <div class="two" style="margin-top:16px">
        <div class="card"><h3>Where your ATP comes from</h3>
          <table class="mults"><tr><td>Base: 1 + pathways</td><td>${fmt(S.baseYield)}</td></tr>${parts}
          <tr class="total"><td>Per card</td><td>${fmt(S.perCard)}</td></tr></table>
          <p class="note">Flow adds up to ×${(1 + 0.005 * S.flow.cap).toFixed(2)} on top when you keep reviewing without long breaks.</p>
          ${f.gain ? `<button class="btn" style="margin-top:10px" data-act="fission">Divide for +${f.gain} mtDNA</button>`
            : `<p class="note">Fission unlocks at ${fmt(f.nextAt)} lifetime ATP (you have ${fmt(S.atpAll)}).</p>`}
        </div>
        <div class="card"><h3>Settings</h3><div class="settings">
          <div class="setting"><span>Daily goal<small>Cards per day that count toward your streak</small></span>
            <input type="number" min="1" max="5000" step="10" id="goalInput" value="${SET.daily_goal}" aria-label="Daily goal"></div>
          ${toggle("hud", "Show the review HUD", "The small ATP pill while you study")}
          <div class="setting"><span>HUD position</span><select id="hudPos" aria-label="HUD position">
            ${positions.map(([v, l]) => `<option value="${v}" ${SET.hud_position === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
          ${toggle("hud_toasts", "Pop-ups in the HUD", "Trophies, levels, quests, vesicles and fair-play notes")}
          ${toggle("deck_panel", "Show the card on the deck list")}
          ${toggle("toolbar_button", "Powerhouse button in the top bar", "Takes effect after restarting Anki")}
          ${toggle("sounds", "Sounds in this window")}
          ${toggle("reduce_motion", "Reduce motion")}
        </div></div>
      </div>
      <div class="card prose" style="margin-top:14px"><h3>How Powerhouse works <button class="btn secondary small" data-act="guide" style="float:right">Open the guide</button></h3>
        <p><b>Every button earns the same ATP.</b> Again, Hard, Good or Easy: grade honestly, because the button you press never changes your reward.</p>
        <p><b>Speed never pays more.</b> Flow only asks that no more than three minutes pass between answers (with the Pomodoro timer it waits out a five-minute break).</p>
        <p><b>Fair play.</b> Answers count when you actually do them. An answer under a second counts now and then, but not when another under-a-second answer came within the 4 answers before it. A card counts up to 4 times a day, and auto-advance's machine-steady rhythm doesn't count. Answers that don't count earn nothing and don't count toward your goal. At a normal pace, a couple of seconds a card or more, it almost never triggers.</p>
        <p><b>A clean sweep counts.</b> Finish every due review and the day counts for your streak, even below your goal, as long as at least half of today's answers counted.</p>
        <p><b>Mito grows, then divides.</b> Mito grows as his pathways make more ATP. Once you've made enough ATP in total, he can
        divide, like real mitochondria. You carry on as the small daughter: your ATP, his pathways and their ×2 boosts restart, but each
        division adds mtDNA copies (+${Math.round(100 * (S.fission.bonusEach || 0.25))}% ATP each, forever), and you keep your study habits and other upgrades,
        enzymes, trophies and looks. So every climb goes faster and further. It's optional, like Cookie Clicker's Ascension.</p>
        <p><b>Phone reviews count.</b> Powerhouse reads Anki's review history, so reviews from your phone are credited after you sync. Undoing an answer takes back what it earned.</p>
        <p><b>Your cards are never touched.</b> Powerhouse only reads your collection. Progress is saved inside the add-on's folder.</p>
      </div>`;
  }

  // ----------------------------------------------------------------- events

  function handleEvents(events) {
    for (const e of events) {
      if (e.t === "achievement") toast("trophy", RCOL[e.r], `Trophy: ${e.name}`, `+1% ATP and ${an(e.r)} vesicle`);
      else if (e.t === "level") { toast("spark", "var(--dapi)", `Level ${e.level}`, e.title); SOUND.level(); }
      else if (e.t === "quest") toast("quest", "var(--atp)", "Quest done", e.label);
      else if (e.t === "quests_all") toast("quest", "var(--epic)", "All three quests done", "Bonus epic vesicle");
      else if (e.t === "goal") toast("flame", "var(--flame)", "Daily goal reached", e.atp > 0 ? `Dividend +${fmt(e.atp)} ATP` : "Streak safe for today");
      else if (e.t === "sweep") toast("check", "var(--legendary)", "Clean sweep", "Every due review finished");
      else if (e.t === "cosmetics") (e.ids || []).forEach((id) => toast("shirt", "var(--mito)", "New look unlocked", STATIC.cosmetics[id].name));
      if (e.cosmetics) e.cosmetics.forEach((id) => toast("shirt", "var(--mito)", "New look unlocked", STATIC.cosmetics[id].name));
    }
  }

  function toast(icon, color, title, sub) {
    const box = $("#toasts");
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = `<span class="ic" style="color:${color};background:rgba(255,255,255,.06)">${A.icon(icon, 18)}</span><span><span class="t"></span><small></small></span>`;
    $(".t", el).textContent = title;
    $("small", el).textContent = sub || "";
    box.appendChild(el);
    while (box.children.length > 4) box.firstChild.remove();
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, 3600);
  }

  // ------------------------------------------------------------------ intro

  // ------------------------------------------------------------------ guide
  // "How to play": a short illustrated tour, shown the first time and from the ? button.

  const MINI = {
    phone: `<svg viewBox="0 0 24 24" width="22" height="22"><rect x="6" y="2.5" width="12" height="19" rx="2.6" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10.5 18.5 H13.5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
    undo: `<svg viewBox="0 0 24 24" width="22" height="22"><path d="M9 7 L4 12 L9 17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M4.5 12 H14 A5.5 5.5 0 0 1 14 23" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" transform="translate(0 -4)"/></svg>`,
  };

  function gChips(list) {
    return list.map(([t, ok]) => `<i class="${ok ? "ok" : "no"}">${t}</i>`).join("");
  }

  const GUIDE = [
    {
      title: "Every card you answer powers Mito",
      art: () => `<div class="g-art g-hero">${A.mito({ equipped: S.cosmetics.equipped, size: 168, animate: !SET.reduce_motion })}
        ${[[12, 18], [78, 12], [84, 70], [8, 72]].map(([x, y], i) => `<span class="g-float" style="left:${x}%;top:${y}%;animation-delay:${i * 0.6}s">${A.icon("atp", 22)}</span>`).join("")}</div>`,
      body: `<p class="g-lead">Powerhouse turns your Anki reviews into ATP for Mito, your mitochondrion. Review like normal; the game keeps score.</p>
        <ul><li><b>ATP</b> buys pathways that make every future card worth more.</li>
        <li><b>Vesicles</b> drop while you review. Open them for loot.</li>
        <li><b>48 enzymes</b> to collect, each with a high-yield fact.</li>
        <li><b>Streaks, quests, trophies</b> and titles from Pre-med to Nobel laureate.</li></ul>`,
    },
    {
      title: "Any button, same ATP",
      art: () => `<div class="g-art g-buttons"><div class="g-btns">${["Again", "Hard", "Good", "Easy"].map((b) =>
        `<div class="g-btn"><b>${b}</b><span>+12 ATP</span></div>`).join("")}</div>
        <div class="g-pill">${A.glyph(20)}<b>4.1K</b><span class="u">ATP</span><span class="pc">+12/card</span><span class="fx">×1.24</span></div></div>`,
      body: `<ul><li>Again pays exactly what Easy pays, so <b>grade honestly</b>.</li>
        <li><b>Flow</b> builds while you keep reviewing with no more than 3 minutes between answers: up to ×1.5, more with upgrades. Speed never pays more.</li>
        <li>The pill in the review bar shows your ATP, what a card is worth, your flow and how many vesicles are waiting.</li></ul>`,
    },
    {
      title: "Only real reviews count",
      art: () => `<div class="g-art g-fair">
        <div class="g-row"><span class="g-lab">${A.icon("pomodoro", 18)}Mashing</span><span class="g-chips">${gChips([["0.6s", 1], ["0.4s", 0], ["0.5s", 0], ["4.2s", 1]])}</span></div>
        <div class="g-row"><span class="g-lab">${A.icon("enzyme", 18)}One card, all day</span><span class="g-chips">${gChips([["1", 1], ["2", 1], ["3", 1], ["4", 1], ["5", 0]])}</span></div>
        <div class="g-row"><span class="g-lab">${A.icon("flow", 18)}Auto-advance</span><span class="g-chips">${gChips([["3.00s", 1], ["×3", 1], ["3.01s", 1], ["3.00s", 0]])}</span></div></div>`,
      body: `<ul><li>One answer under a second is fine. If another under-a-second answer came within the 4 answers before it, it doesn't count.</li>
        <li>A card counts up to <b>4 times a day</b>, so looping one card doesn't pay.</li>
        <li>Auto-advance's machine-steady rhythm doesn't count.</li>
        <li>Answers that don't count earn nothing and don't count toward your goal or streak. At a normal pace, a couple of seconds a card or more, this almost never triggers.</li></ul>`,
    },
    {
      title: "Build Mito's metabolism",
      art: () => `<div class="g-art g-ladder"><div class="g-steps">${STATIC.pathwayOrder.map((id, i) =>
        `<span class="g-step" style="--i:${i}" title="${esc(STATIC.pathways[id].name)}">${A.icon(id, 20)}</span>`).join("")}</div>
        <div class="g-grow"><span style="--s:.55">${A.glyph(30)}</span><span class="arr">→</span><span style="--s:1">${A.glyph(54)}</span></div></div>`,
      body: `<ul><li><b>Pathways</b> add ATP to every future card. Each one opens after you buy the one before, from glycolysis all the way to mitochondrial biogenesis.</li>
        <li>Own 10, 25, 50 and 100 of a pathway to unlock upgrades that <b>double</b> it.</li>
        <li><b>Study habits</b> (coffee, sleep, a qbank streak…) unlock as you answer more cards and multiply everything.</li>
        <li>Mito <b>grows</b> as his pathways make more ATP.</li></ul>`,
    },
    {
      title: "Vesicles: loot while you review",
      art: () => `<div class="g-art g-ves">${["common", "rare", "epic", "legendary"].map((r, i) =>
        `<span class="g-orb" style="--d:${i * 0.25}s">${A.vesicle(r, 46 + i * 10)}<small style="color:${RCOL[r]}">${cap(r)}</small></span>`).join("")}</div>`,
      body: `<ul><li>About <b>one every 40 cards</b> early in the day, then less often on a big day: half as often after 150 cards, a quarter after 500, an eighth after 1,000.</li>
        <li>Quests, trophies, clean sweeps and every fifth level give more.</li>
        <li>Open them after your session for ATP, enzymes, new looks for Mito and, rarely, a streak freeze.</li></ul>`,
    },
    {
      title: "Collect the enzymes",
      art: () => {
        const leg = STATIC.enzymes.pfk1, com = STATIC.enzymes.hexokinase;
        const pips = (n) => `<span class="expr">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= n ? "on" : ""}"></i>`).join("")}</span>`;
        return `<div class="g-art g-codex">
          <div class="enz legendary">${pips(3)}<h5><span class="gem" style="background:${RCOL.legendary}"></span>${esc(leg.name)}</h5><p>${esc(leg.fact)}</p></div>
          <div class="enz common">${pips(5)}<h5><span class="gem" style="background:${RCOL.common}"></span>${esc(com.name)}</h5><p>${esc(com.fact)}</p></div></div>`;
      },
      body: `<ul><li><b>48 enzymes in 6 sets.</b> A new set opens with each title: Pre-med, MS1, MS2, Step 1 survivor, MS3, MS4. Each later set also has a minimum wait after you install: 1, 3, 5, 8 and 12 weeks.</li>
        <li>Every <b>legendary</b> is its pathway's rate-limiting enzyme. Bad luck has a limit: never more than 2 duplicate legendaries in a row while you're missing one.</li>
        <li>Duplicates raise an enzyme's <b>expression</b>: more enzyme, higher Vmax, same Km. Each level adds +0.25% ATP; rarer enzymes need fewer copies.</li>
        <li>Each complete set adds +5% ATP, and all six add +10% more.</li></ul>`,
    },
    {
      title: "Your day: goal, streak, quests",
      art: () => `<div class="g-art g-day"><div class="card">
        <div class="meter"><label><span>Today's goal</span><b>72 / 100</b></label><div class="track energy"><i style="width:72%"></i></div></div>
        <div class="streak-row"><span class="flame">${A.icon("flame", 17)}14-day streak</span><span class="ice">${A.icon("freeze", 15)}2 freezes</span></div>
        <div class="quest done"><span class="box">${A.icon("check", 14)}</span><span class="label">Answer 60 cards</span></div>
        <div class="quest"><span class="box"></span><span class="label">Answer 125 cards</span></div>
        <div class="quest"><span class="box"></span><span class="label">Reach a flow of 50</span></div></div></div>`,
      body: `<ul><li>Hit your <b>daily goal</b> (100 cards to start, change it in Stats) to keep your streak. Finishing every due review counts too, as long as at least half of the day's answers counted.</li>
        <li>Every 7 streak days earns a <b>freeze</b> that covers a missed day. You can bank 2.</li>
        <li>Reaching the goal pays a <b>knowledge dividend</b> from your mature cards.</li>
        <li><b>Three daily quests</b> adapt to how much you usually study. Finish all three for a bonus epic vesicle.</li>
        <li>Every answer that counts is 1 XP. Levels and trophies each add +1% ATP.</li></ul>`,
    },
    {
      title: "Mito grows, then divides",
      art: () => `<div class="g-art g-fission">
        <span class="g-big">${A.mito({ equipped: S.cosmetics.equipped, size: 132, animate: false })}</span>
        <span class="g-split">${A.icon("split", 26)}<small>mtDNA ×2</small></span>
        <span class="g-small">${A.mito({ equipped: S.cosmetics.equipped, size: 74, animate: false })}</span>
        <span class="g-line">${A.glyph(18)}${A.glyph(18)}${A.glyph(18)}</span></div>`,
      body: () => `<ul><li>Once you've made 10 billion ATP in total, Mito can <b>divide</b>, like real mitochondria. You carry on as the small daughter.</li>
        <li><b>Restarts:</b> your ATP, Mito's pathways and their ×2 boosts. <b>Keeps:</b> study habits, vesicle and flow upgrades, level, streak, trophies, enzymes, looks and vesicles.</li>
        <li>Each division adds <b>mtDNA copies</b>, +${Math.round(100 * (S.fission.bonusEach || 0.25))}% ATP each, forever, so the next climb goes faster and further. (mtDNA encodes 13 proteins of the electron transport chain and ATP synthase.)</li>
        <li>The game suggests dividing once it would gain at least 3 copies and at least double what you have. It's optional, like Cookie Clicker's Ascension.</li></ul>`,
    },
    {
      title: "Good to know",
      art: () => `<div class="g-art g-know">${[
        [MINI.phone, "Phone reviews count"], [MINI.undo, "Undo takes it back"], [A.icon("lock", 22), "Read-only"], [A.icon("gear", 22), "Settings in Stats"],
      ].map(([ic, t]) => `<span class="g-tile">${ic}<small>${t}</small></span>`).join("")}</div>`,
      body: `<ul><li>Reviews on your <b>phone</b> count once they sync to this computer, even up to 30 days later.</li>
        <li><b>Undo</b> takes back an answer's ATP and XP, and its vesicle if you haven't opened it.</li>
        <li>Powerhouse <b>only reads</b> your review history. It never changes cards, scheduling, decks or sync.</li>
        <li>Open the game from the <b>Powerhouse</b> button, the card under your deck list, or Tools → Powerhouse. Settings, like your daily goal and where the pill sits, are in <b>Stats</b>.</li></ul>`,
    },
  ];

  function showGuide(first) {
    ui.guide = { page: 0, first: !!first };
    renderGuide();
    showOverlay();
  }

  function renderGuide() {
    const g = ui.guide;
    if (!g) return;
    const n = GUIDE.length, pg = GUIDE[g.page], last = g.page === n - 1;
    const finish = g.first ? `<button class="btn" data-act="guide-done">Start with 3 free vesicles</button>`
      : `<button class="btn" data-act="guide-done">Done</button>`;
    $("#overlay").innerHTML = `<div class="guide" role="document" aria-label="How to play">
      <div class="g-top"><span>How to play · ${g.page + 1} of ${n}</span>
        <button class="g-x" data-act="guide-done" aria-label="${g.first ? "Skip the guide" : "Close"}">${g.first ? "Skip" : A.icon("close", 16)}</button></div>
      <div class="g-page ${SET.reduce_motion ? "" : "g-in"}">${pg.art()}<div class="g-text"><h2>${esc(pg.title)}</h2>${typeof pg.body === "function" ? pg.body() : pg.body}</div></div>
      <div class="g-foot">
        <button class="btn secondary" data-act="guide-prev" ${g.page === 0 ? "disabled" : ""}>Back</button>
        <span class="g-dots">${GUIDE.map((_, i) => `<button data-act="guide-go" data-page="${i}" aria-label="Page ${i + 1}" aria-current="${i === g.page}"></button>`).join("")}</span>
        ${last ? finish : `<button class="btn" data-act="guide-next">Next</button>`}
      </div></div>`;
    const b = $(".g-foot .btn:last-child");
    if (b) b.focus();
  }

  async function finishGuide() {
    const g = ui.guide;
    ui.guide = null;
    closeOverlay();
    if (g && g.first) {
      const r = await send("intro");
      applyResult(r);
      switchTab("vesicles");
    }
  }

  window.addEventListener("keydown", (e) => {
    if (!ui.guide || !$("#overlay").classList.contains("show")) return;
    if (e.key === "ArrowRight" && ui.guide.page < GUIDE.length - 1) { ui.guide.page += 1; renderGuide(); }
    else if (e.key === "ArrowLeft" && ui.guide.page > 0) { ui.guide.page -= 1; renderGuide(); }
  });

  // ----------------------------------------------------------------- clicks

  async function onClick(e) {
    const el = e.target.closest("[data-act]");
    if (!el) return;
    const act = el.getAttribute("data-act");
    if (act === "tab") return switchTab(el.getAttribute("data-tab"));
    if (act === "qty") {
      const q = el.getAttribute("data-qty");
      ui.buyQty = q === "max" ? "max" : +q;
      return renderPanel(true);
    }
    if (act === "buy-pathway") {
      const id = el.getAttribute("data-id");
      const r = await send("buy", `pathway:${id}:${ui.buyQty}`);
      if (r.ok) { SOUND.buy(); pulse(el); } else SOUND.no();
      return applyResult(r);
    }
    if (act === "buy-upgrade") {
      const r = await send("buy", `upgrade:${el.getAttribute("data-id")}`);
      if (r.ok) SOUND.buy(); else SOUND.no();
      return applyResult(r);
    }
    if (act === "open") return openOne(el.getAttribute("data-id"));
    if (act === "open-next") return openOne(null);
    if (act === "open-all") return openAll();
    if (act === "close-overlay") return closeOverlay();
    if (act === "equip") return applyResult(await send("equip", el.getAttribute("data-id")));
    if (act === "poke") {
      const r = await send("poke");
      const sp = $("#speech");
      if (sp && r.line) {
        sp.textContent = r.line;
        sp.classList.add("show");
        clearTimeout(ui.speechT);
        ui.speechT = setTimeout(() => sp.classList.remove("show"), 3200);
      }
      const stage = $("#stage");
      if (stage && !SET.reduce_motion) { stage.classList.remove("poked"); void stage.offsetWidth; stage.classList.add("poked"); }
      if (r.events && r.events.length) applyResult(r);
      return;
    }
    if (act === "fission") return confirmFission();
    if (act === "fission-yes") {
      closeOverlay();
      await divideAnimation();
      const r = await send("fission");
      if (r.ok) toast("split", "var(--epic)", `Divided! +${r.gain} mtDNA`, `+${Math.round(r.gain * S.fission.bonusEach * 100)}% ATP forever`);
      return applyResult(r);
    }
    if (act === "intro-done" || act === "guide-done") return finishGuide();
    if (act === "guide") return showGuide(false);
    if (act === "guide-next" && ui.guide) { ui.guide.page = Math.min(GUIDE.length - 1, ui.guide.page + 1); return renderGuide(); }
    if (act === "guide-prev" && ui.guide) { ui.guide.page = Math.max(0, ui.guide.page - 1); return renderGuide(); }
    if (act === "guide-go" && ui.guide) { ui.guide.page = +el.getAttribute("data-page") || 0; return renderGuide(); }
    if (act === "setting") {
      const key = el.getAttribute("data-key");
      const patch = {};
      patch[key] = !SET[key];
      return saveSettings(patch);
    }
  }

  function confirmFission() {
    const f = S.fission;
    const ov = $("#overlay");
    ov.innerHTML = `<div class="intro" style="width:min(520px,92vw)">
      <div class="hero">${A.icon("split", 44)}<div><h2>Divide Mito?</h2>
      <p>You gain <b>${f.gain} mtDNA</b>: +${Math.round(f.gain * f.bonusEach * 100)}% ATP forever. mtDNA encodes 13 proteins of the
      electron transport chain and ATP synthase, so more copies, more ATP.</p>
      ${f.suggest === false ? `<p class="note">That's a small gain for a restart. Each division needs more lifetime ATP than the last, so most players wait for a bigger one.</p>` : ""}</div></div>
      <div class="rules">
        <div class="rule"><span class="ic" style="background:rgba(255,107,94,.14);color:var(--mito)">${A.icon("close", 18)}</span>
          <div><b>Restarts</b><span>Your ATP, Mito's pathways and their ×2 boosts. He starts small again.</span></div></div>
        <div class="rule"><span class="ic" style="background:rgba(124,242,156,.14);color:var(--atp)">${A.icon("check", 18)}</span>
          <div><b>Keeps</b><span>Study habits, vesicle and flow upgrades, level, streak, trophies, enzymes, looks, vesicles and every mtDNA.</span></div></div>
      </div>
      <div class="actions" style="display:flex;gap:10px"><button class="btn" data-act="fission-yes">Divide</button>
      <button class="btn secondary" data-act="close-overlay">Not yet</button></div></div>`;
    showOverlay();
  }

  // Scroll el into view inside its own scrolling column. (scrollIntoView would also scroll
  // whatever page embeds this one.) Resolves once it's showing.
  async function reveal(el) {
    let box = el.parentElement;
    while (box && box !== document.body) {
      const oy = getComputedStyle(box).overflowY;
      if ((oy === "auto" || oy === "scroll") && box.scrollHeight > box.clientHeight + 1) break;
      box = box.parentElement;
    }
    const r = el.getBoundingClientRect();
    const view = box && box !== document.body ? box.getBoundingClientRect() : { top: 0, bottom: window.innerHeight };
    if (r.top >= view.top - 1 && r.bottom <= view.bottom + 1) return;
    const delta = r.top - view.top - 12;
    if (box && box !== document.body) box.scrollTo({ top: Math.max(0, box.scrollTop + delta), behavior: "smooth" });
    else window.scrollTo({ top: Math.max(0, window.scrollY + delta), behavior: "smooth" });
    await wait(480);
  }

  async function divideAnimation() {
    const stage = $("#stage");
    if (!stage || SET.reduce_motion) return;
    const holder = stage.querySelector(".mito-holder");
    if (!holder) return;
    await reveal(stage); // the Divide button sits below Mito, so bring him back into view first
    const twin = holder.cloneNode(true);
    twin.classList.add("twin");
    holder.parentNode.insertBefore(twin, holder.nextSibling);
    stage.classList.add("dividing");
    await wait(1400);
    stage.classList.remove("dividing");
    twin.remove();
  }

  function pulse(el) {
    if (SET.reduce_motion) return;
    el.animate([{ transform: "scale(1)" }, { transform: "scale(1.06)" }, { transform: "scale(1)" }], { duration: 220 });
  }

  function applyResult(r) {
    if (!r) return;
    if (r.settings) SET = r.settings;
    if (r.state) { S = r.state; renderAll(false); }
    if (r.events && r.events.length) handleEvents(r.events);
    if (r.error) toast("close", "var(--muted)", r.error, "");
  }

  async function saveSettings(patch) {
    const r = await send("settings", JSON.stringify(patch));
    applyResult(r);
    document.body.classList.toggle("still", !!SET.reduce_motion);
    renderPanel(true);
  }

  document.addEventListener("change", (e) => {
    if (e.target.id === "goalInput") {
      const v = Math.max(1, Math.min(5000, parseInt(e.target.value, 10) || 100));
      saveSettings({ daily_goal: v });
    } else if (e.target.id === "hudPos") {
      saveSettings({ hud_position: e.target.value });
    }
  });

  window.PH = { init, update, tab: (t) => { if (S) switchTab(t); } };
})();
