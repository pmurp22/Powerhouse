/* Powerhouse deck-list card: today's progress at a glance and a door into the game.
   Rendered in a shadow root so deck-list themes and background add-ons can't restyle it. */
(function () {
  "use strict";
  if (window.PowerhousePanel) return;

  const CSS = `
  :host { all: initial; display: block; }
  * { box-sizing: border-box; }
  .card {
    position: relative; max-width: 720px; margin: 14px auto 6px; padding: 14px 16px 14px 14px; text-align: left;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 13px; line-height: 1.35; color: #F3EFFF;
    background: radial-gradient(120% 140% at 0% 0%, rgba(55, 42, 120, .92), rgba(18, 15, 38, .94) 60%);
    border: 1px solid rgba(255,255,255,.12); border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,.28);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  }
  .top { display: grid; grid-template-columns: auto 1fr auto; gap: 14px; align-items: center; }
  .mito { cursor: pointer; display: flex; border-radius: 16px; outline-offset: 3px; }
  .mito:focus-visible { outline: 2px solid #6EA8FF; }
  .mid { min-width: 0; display: flex; flex-direction: column; gap: 7px; }
  .lvl { display: flex; align-items: baseline; gap: 8px; font-family: "PowerhouseFredoka", ui-rounded, system-ui, sans-serif; }
  .lvl b { font-size: 18px; font-weight: 600; }
  .lvl span { color: #A9CBFF; font-size: 14px; }
  .xp { height: 6px; border-radius: 4px; background: rgba(110,168,255,.18); overflow: hidden; }
  .xp i { display: block; height: 100%; background: linear-gradient(90deg, #6EA8FF, #A9CBFF); border-radius: 4px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px 14px; color: #CFC8EE; }
  .chip { display: flex; align-items: center; gap: 5px; }
  .chip svg { flex: none; }
  .flame { color: #FF9F43; } .ice { color: #8FD8FF; } .muted { color: #A49CC8; }
  .atp { text-align: right; font-family: "PowerhouseFredoka", ui-rounded, system-ui, sans-serif; }
  .atp b { display: block; font-size: 22px; font-weight: 600; color: #fff; font-variant-numeric: tabular-nums; }
  .atp span { color: #7CF29C; font-size: 12px; }
  .atp small { font-size: 12px; color: #A49CC8; font-weight: 500; }
  .bars { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 18px; margin-top: 12px; }
  .meter label { display: flex; justify-content: space-between; color: #CFC8EE; font-size: 12px; margin-bottom: 4px; }
  .meter label b { color: #fff; font-weight: 600; font-variant-numeric: tabular-nums; }
  .track { height: 8px; border-radius: 5px; background: rgba(255,255,255,.08); overflow: hidden; }
  .track i { display: block; height: 100%; border-radius: 5px; }
  .energy i { background: linear-gradient(90deg, #FF6B5E, #FFB199); }
  .rounds i { background: linear-gradient(90deg, #4FD487, #A6F5C2); }
  .quests { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  .q { display: flex; align-items: center; gap: 6px; padding: 5px 9px 5px 6px; border-radius: 10px;
       background: rgba(255,255,255,.06); color: #DCD6F7; font-size: 12px; }
  .q .box { width: 16px; height: 16px; border-radius: 5px; border: 1.5px solid rgba(255,255,255,.35); display: flex; align-items: center; justify-content: center; }
  .q.done { color: #A49CC8; text-decoration: line-through; text-decoration-color: rgba(164,156,200,.6); }
  .q.done .box { background: #4FD487; border-color: #4FD487; color: #10241A; }
  .q em { font-style: normal; color: #A49CC8; font-variant-numeric: tabular-nums; }
  .foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
  .session { color: #A49CC8; font-size: 12px; }
  .session b { color: #E9E4FF; font-weight: 600; }
  .actions { display: flex; gap: 8px; align-items: center; margin-left: auto; }
  button {
    font: 600 13px/1 "PowerhouseFredoka", ui-rounded, system-ui, sans-serif; letter-spacing: .01em; cursor: pointer;
    border: 0; border-radius: 12px; padding: 9px 14px; color: #1A0F1F; background: #FF6B5E;
    box-shadow: 0 3px 0 #B8424B; transition: transform .08s, box-shadow .08s;
  }
  button:hover { background: #FF7F73; }
  button:active { transform: translateY(2px); box-shadow: 0 1px 0 #B8424B; }
  button:focus-visible { outline: 2px solid #6EA8FF; outline-offset: 2px; }
  .ghost { background: transparent; color: #CFC8EE; box-shadow: none; padding: 6px 8px; font-weight: 500; }
  .ghost:hover { background: rgba(255,255,255,.08); }
  .badge { display: inline-flex; align-items: center; gap: 6px; color: #E9E4FF; font-size: 12px; }
  .compact .bars, .compact .quests, .compact .foot .session { display: none; }
  .compact .card { padding: 9px 12px; }
  .compact .xp { display: none; }
  .row-compact { display: none; }
  @media (max-width: 560px) { .bars { grid-template-columns: 1fr; } .top { grid-template-columns: auto 1fr; } .atp { grid-column: 1 / -1; text-align: left; } }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
  .still * { transition: none !important; animation: none !important; }
  .mito-anim .mito-bob { animation: bob 3.2s ease-in-out infinite; transform-origin: 50% 90%; }
  @keyframes bob { 0%,100% { transform: translateY(0) } 50% { transform: translateY(-3px) } }
  `;

  let host = null, root = null, data = null, opts = {};

  function A() { return window.PowerhouseArt; }

  function ensureFont(url) {
    if (!url || document.getElementById("powerhouse-font")) return;
    const st = document.createElement("style");
    st.id = "powerhouse-font";
    st.textContent = `@font-face{font-family:"PowerhouseFredoka";src:url("${url}") format("woff2");font-weight:300 700;font-display:swap;}`;
    (document.head || document.documentElement).appendChild(st);
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function render() {
    if (!root || !data) return;
    const d = data, art = A(), fmt = art.fmt;
    const compact = !!opts.compact;
    const s = d.streak || {};
    const hour = new Date().getHours();
    const mood = d.today === 0 && hour >= 14 ? "sleepy" : "happy";
    const xpPct = d.xpNeed ? Math.round(100 * d.xpInto / d.xpNeed) : 0;
    const goalPct = Math.min(100, Math.round(100 * d.today / Math.max(1, d.goal)));
    const r = d.rounds || {};
    const roundsPct = r.known ? Math.round(100 * (r.pct || 0)) : null;
    const streakText = s.current
      ? `${s.current}-day streak${s.today_done ? "" : " (today pending)"}`
      : "Start a streak today";
    const quests = (d.quests || []).map((q) => `
      <span class="q ${q.done ? "done" : ""}"><span class="box">${q.done ? art.icon("check", 12) : ""}</span>
      ${esc(q.label)}${q.done ? "" : ` <em>${fmt(q.progress)}/${fmt(q.target)}</em>`}</span>`).join("");
    let sessionLine = "";
    const ls = d.lastSession;
    if (ls && ls.n) {
      sessionLine = `Last session: <b>${fmt(ls.n)}</b> cards, <b>+${fmt(ls.atp)}</b> ATP` +
        (ls.vf ? `, <b>${ls.vf}</b> vesicle${ls.vf === 1 ? "" : "s"} found` : "");
    }
    const ves = d.vesicles ? `<span class="badge">${art.vesicle("rare", 18)}${d.vesicles} to open</span>` : "";
    const fission = d.fissionGain > 0 ? `<span class="badge">${art.icon("split", 16)}Fission ready</span>` : "";
    root.innerHTML = `<style>${CSS}</style>
      <div class="${compact ? "compact" : ""} ${opts.reduceMotion ? "still" : ""}">
      <div class="card" role="region" aria-label="Powerhouse">
        <div class="top">
          <div class="mito" tabindex="0" role="button" aria-label="Open Powerhouse" data-act="open">
            ${art.mito({ equipped: d.equipped, size: compact ? 44 : 78, mood, animate: !opts.reduceMotion })}
          </div>
          <div class="mid">
            <div class="lvl"><b>Level ${d.level}</b><span>${esc(d.title)}</span></div>
            <div class="xp" title="${fmt(d.xpInto)} / ${fmt(d.xpNeed)} XP to the next level"><i style="width:${xpPct}%"></i></div>
            <div class="chips">
              <span class="chip flame">${art.icon("flame", 15)}<span>${esc(streakText)}</span></span>
              ${s.freezes ? `<span class="chip ice" title="Streak freezes cover a missed day">${art.icon("freeze", 14)}<span>${s.freezes} freeze${s.freezes === 1 ? "" : "s"}</span></span>` : ""}
              ${compact ? `<span class="chip muted">${fmt(d.today)} / ${fmt(d.goal)} today</span>` : ""}
            </div>
          </div>
          <div class="atp"><b>${fmt(d.atp)} <small>ATP</small></b><span>+${fmt(d.perCard)} per card</span></div>
        </div>
        <div class="bars">
          <div class="meter energy"><label><span>Today's goal</span><b>${fmt(d.today)} / ${fmt(d.goal)}</b></label>
            <div class="track"><i style="width:${goalPct}%"></i></div></div>
          <div class="meter rounds"><label><span>Due reviews done</span><b>${roundsPct === null ? "—" : roundsPct + "%"}</b></label>
            <div class="track"><i style="width:${roundsPct === null ? 0 : roundsPct}%"></i></div></div>
        </div>
        ${quests ? `<div class="quests">${quests}</div>` : ""}
        <div class="foot">
          <span class="session">${sessionLine}</span>
          <span class="actions">${fission}${ves}
            <button class="ghost" data-act="toggle" title="${compact ? "Show more" : "Show less"}">${compact ? "More" : "Less"}</button>
            <button data-act="open">Open Powerhouse</button></span>
        </div>
      </div></div>`;
  }

  function onClick(e) {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    const act = t.getAttribute("data-act");
    if (act === "open") pycmd("powerhouse:open");
    if (act === "toggle") {
      opts.compact = !opts.compact;
      render();
      pycmd("powerhouse:panel:" + (opts.compact ? "compact" : "full"));
    }
  }

  function onKey(e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.closest && e.target.closest(".mito")) {
      e.preventDefault();
      pycmd("powerhouse:open");
    }
  }

  function mount(el, o, payload) {
    opts = o || {};
    ensureFont(opts.fontUrl);
    host = el;
    root = host.shadowRoot || host.attachShadow({ mode: "open" });
    root.addEventListener("click", onClick);
    root.addEventListener("keydown", onKey);
    data = window.__phPanelPending || payload;
    window.__phPanelPending = null;
    render();
  }

  function update(payload) {
    data = payload;
    render();
  }

  window.PowerhousePanel = { mount, update };
})();
