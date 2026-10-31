/* Powerhouse review HUD.
   Default home: the review screen's bottom bar, next to "More", so it never
   covers a card. Optional: a click-through pill in a corner of the card area.
   Lives in a shadow root so card styles and other add-ons can't restyle it. */
(function () {
  "use strict";
  if (window.PowerhouseHUD) return;

  const CSS = `
  :host { all: initial; }
  * { box-sizing: border-box; }
  .wrap { display: flex; flex-direction: column; gap: 6px; font-family: "PowerhouseFredoka", ui-rounded, "SF Pro Rounded", system-ui, sans-serif; }
  .wrap.right { align-items: flex-end; } .wrap.left { align-items: flex-start; }
  .pill {
    position: relative; display: flex; align-items: center; gap: 9px; height: 34px; padding: 0 12px 0 7px;
    background: rgba(18, 15, 38, .86); color: #F3EFFF; border: 1px solid rgba(255,255,255,.12);
    border-radius: 999px; box-shadow: 0 4px 14px rgba(0,0,0,.22);
    backdrop-filter: blur(10px) saturate(1.2); -webkit-backdrop-filter: blur(10px) saturate(1.2);
    font-size: 13px; line-height: 1; white-space: nowrap; font-variant-numeric: tabular-nums; overflow: hidden;
  }
  .main, .msg { display: flex; align-items: center; gap: 9px; transition: opacity .25s ease, transform .25s ease; }
  .msg { position: absolute; inset: 0 12px 0 9px; opacity: 0; transform: translateY(8px); pointer-events: none; gap: 7px; }
  .pill.talking .main { opacity: 0; transform: translateY(-8px); }
  .pill.talking .msg { opacity: 1; transform: none; }
  .msg .ic { display: flex; }
  .msg b { font-weight: 600; font-size: 13px; overflow: hidden; text-overflow: ellipsis; }
  .msg span { color: #B9B1DD; font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
  .glyph { display: flex; transform-origin: 50% 80%; }
  .glyph.bump { animation: bump .45s ease-out; }
  @keyframes bump { 0% { transform: scale(1) } 35% { transform: scale(1.25, .85) } 70% { transform: scale(.92, 1.1) } 100% { transform: scale(1) } }
  .atp { display: flex; align-items: baseline; gap: 4px; position: relative; }
  .atp b { font-size: 15.5px; font-weight: 600; letter-spacing: .01em; color: #FFFFFF; transition: color .3s; }
  .atp b.flash { color: #7CF29C; transition: none; }
  .atp span { font-size: 11px; color: #A49CC8; }
  .per { font-size: 12px; color: #7CF29C; }
  .sep { width: 1px; height: 16px; background: rgba(255,255,255,.14); }
  .flow { display: flex; align-items: center; gap: 6px; color: #9CC3FF; font-size: 12px; }
  .bar { width: 30px; height: 5px; border-radius: 3px; background: rgba(110,168,255,.2); overflow: hidden; }
  .bar i { display: block; height: 100%; width: 0; background: linear-gradient(90deg, #6EA8FF, #A9CBFF); border-radius: 3px; transition: width .35s ease; }
  .ves { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #D9D3F5; }
  .ves svg { display: block; }
  .ves.pop svg { animation: pop .6s cubic-bezier(.2,1.6,.4,1); }
  @keyframes pop { 0% { transform: scale(.4) } 60% { transform: scale(1.35) } 100% { transform: scale(1) } }
  .gain {
    position: absolute; left: 0; top: -2px; font-size: 12px; font-weight: 600; color: #7CF29C;
    pointer-events: none; animation: rise 1s ease-out forwards; text-shadow: 0 1px 4px rgba(0,0,0,.5);
  }
  @keyframes rise { 0% { opacity: 0; transform: translateY(4px) } 20% { opacity: 1 } 100% { opacity: 0; transform: translateY(-18px) } }
  .compact .per, .compact .flow, .compact .sep.s1 { display: none; }
  .still *, .still { animation: none !important; transition: none !important; }
  `;

  const KIND = {
    achievement: ["trophy", "#FFC94D"], level: ["spark", "#6EA8FF"], quest: ["quest", "#7CF29C"],
    quests_all: ["quest", "#B884FF"], goal: ["flame", "#FF9F43"], sweep: ["check", "#FFC94D"],
    vesicle: ["vesicle", "#7FD6FF"], comeback: ["spark", "#FF6B5E"], undo: ["close", "#A49CC8"],
    nocount: ["close", "#A49CC8"],
  };
  // fair play: why an answer earned nothing, said at most once every 90 seconds per reason
  const NOCOUNT = {
    quick: ["Too quick", "didn't count"],
    repeat: ["Card maxed", "4 times today"],
    steady: ["Auto-advance", "doesn't count"],
  };
  const nocountSaid = {};

  let host = null, root = null, els = {}, opts = {}, shown = 0, target = 0, raf = 0;
  let queue = [], talking = false;

  function art() { return window.PowerhouseArt; }
  function fmt(n) { return art() ? art().fmt(n) : String(Math.round(n)); }
  function inBar() { return opts.position === "bar"; }

  function ensureFont(url) {
    if (!url || document.getElementById("powerhouse-font")) return;
    const st = document.createElement("style");
    st.id = "powerhouse-font";
    st.textContent = `@font-face{font-family:"PowerhouseFredoka";src:url("${url}") format("woff2");font-weight:300 700;font-display:swap;}`;
    (document.head || document.documentElement).appendChild(st);
  }

  function place() {
    const s = host.style;
    const pos = opts.position || "bar";
    if (pos === "bar") {
      // Absolutely positioned so the answer buttons stay exactly where Anki puts them.
      s.position = "absolute"; s.top = "9px"; s.zIndex = "5";
      els.wrap.className = "wrap right" + (opts.reduceMotion ? " still" : "");
      fit();
      return;
    }
    s.position = "fixed"; s.zIndex = "9000"; s.pointerEvents = "none";
    s.top = s.bottom = s.left = s.right = "";
    if (pos.startsWith("bottom")) s.bottom = "10px"; else s.top = "10px";
    if (pos.endsWith("left")) s.left = "12px"; else s.right = "12px";
    els.wrap.className = "wrap " + (pos.endsWith("left") ? "left" : "right") + (opts.reduceMotion ? " still" : "");
  }

  // In the bottom bar: sit just left of "More", shrink when space is tight,
  // and step aside entirely rather than ever overlapping Anki's buttons.
  function rightEdgeOfMiddle() {
    const mid = document.getElementById("middle");
    if (!mid) return 0;
    let right = 0;
    mid.querySelectorAll("button, .stattxt, span").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width) right = Math.max(right, r.right);
    });
    return right;
  }

  function fit() {
    if (!host || !inBar()) return;
    const W = document.documentElement.clientWidth || window.innerWidth;
    const cells = document.querySelectorAll("#innertable td");
    const cell = cells.length ? cells[cells.length - 1] : null;
    const more = cell ? cell.querySelector("button") : null;
    if (!more || !more.getBoundingClientRect().width) { host.style.display = "none"; return; }
    host.style.display = "block";
    const mr = more.getBoundingClientRect();
    host.style.right = Math.round(W - mr.left + 6) + "px";
    host.style.top = Math.round(mr.top + window.scrollY + (mr.height - 34) / 2) + "px";
    const limit = rightEdgeOfMiddle() + 14;
    els.pill.classList.remove("compact");
    if (host.getBoundingClientRect().left < limit) els.pill.classList.add("compact");
    if (host.getBoundingClientRect().left < limit) host.style.display = "none";
  }

  let fitQueued = false;
  function queueFit() {
    if (fitQueued) return;
    fitQueued = true;
    requestAnimationFrame(() => { fitQueued = false; fit(); });
  }

  function mount(o, payload) {
    opts = o || {};
    if (host && document.contains(host)) { place(); if (payload) update(payload, true); return; }
    ensureFont(opts.fontUrl);
    host = document.createElement(inBar() ? "span" : "div");
    host.id = "powerhouse-hud";
    host.setAttribute("aria-hidden", "true");
    root = host.attachShadow({ mode: "open" });
    const A = art();
    root.innerHTML = `<style>${CSS}</style>
      <div class="wrap">
        <div class="pill" title="Powerhouse: every answer that counts makes ATP">
          <div class="main">
            <span class="glyph">${A ? A.glyph(24) : ""}</span>
            <span class="atp"><b>0</b><span>ATP</span></span>
            <span class="per"></span>
            <span class="sep s1"></span>
            <span class="flow"><span class="fx">×1.00</span><span class="bar"><i></i></span></span>
            <span class="sep"></span>
            <span class="ves">${A ? A.vesicle("rare", 16) : ""}<span class="vn">0</span></span>
          </div>
          <div class="msg"><span class="ic"></span><b></b><span></span></div>
        </div>
      </div>`;
    els = {
      wrap: root.querySelector(".wrap"), pill: root.querySelector(".pill"), glyph: root.querySelector(".glyph"),
      atpBox: root.querySelector(".atp"), atp: root.querySelector(".atp b"), per: root.querySelector(".per"),
      fx: root.querySelector(".fx"), bar: root.querySelector(".bar i"), ves: root.querySelector(".ves"),
      vn: root.querySelector(".vn"), msg: root.querySelector(".msg"),
    };
    if (inBar()) {
      (document.body || document.documentElement).appendChild(host);
      window.addEventListener("resize", queueFit);
      const mid = document.getElementById("middle");
      if (mid && window.MutationObserver) new MutationObserver(queueFit).observe(mid, { childList: true, subtree: true });
      setTimeout(fit, 50);
    } else {
      (document.body || document.documentElement).appendChild(host);
      document.addEventListener("mousemove", onMove, { passive: true });
    }
    place();
    if (opts.hidden) host.style.display = "none";
    if (payload) { shown = payload.atp || 0; update(payload, true); }
    if (window.__phHudPending) { const p = window.__phHudPending; window.__phHudPending = null; update(p); }
  }

  // Overlay mode only: fade away when the mouse comes near so the card stays readable.
  function onMove(e) {
    if (!host || inBar()) return;
    const r = host.getBoundingClientRect();
    const near = e.clientX > r.left - 28 && e.clientX < r.right + 28 && e.clientY > r.top - 28 && e.clientY < r.bottom + 28;
    host.style.transition = "opacity .2s";
    host.style.opacity = near ? "0.12" : "1";
  }

  function tween() {
    cancelAnimationFrame(raf);
    const from = shown, to = target, t0 = performance.now(), dur = 450;
    if (opts.reduceMotion || Math.abs(to - from) < 1e-9) { shown = to; els.atp.textContent = fmt(shown); return; }
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      const e = 1 - Math.pow(1 - k, 3);
      shown = from + (to - from) * e;
      els.atp.textContent = fmt(shown);
      if (k < 1) raf = requestAnimationFrame(step); else shown = to;
    };
    raf = requestAnimationFrame(step);
  }

  function update(p, silent) {
    if (!host || !p) return;
    target = Math.max(0, p.atp || 0);
    tween();
    els.per.textContent = `+${fmt(p.perCard || 0)}/card`;
    const flowMult = p.flowMult || 1;
    els.fx.textContent = "×" + flowMult.toFixed(2);
    const capMult = 1 + 0.005 * (p.flowCap || 100);
    els.bar.style.width = Math.round(Math.min(1, (flowMult - 1) / (capMult - 1 || 1)) * 100) + "%";
    els.vn.textContent = String(p.vesicles || 0);
    if (silent) return;
    const events = p.events || [];
    const answers = events.find((e) => e.t === "answers");
    if (answers && answers.atp > 0 && !opts.reduceMotion) {
      if (inBar()) {
        els.atp.classList.add("flash");
        setTimeout(() => els.atp.classList.remove("flash"), 220);
      } else {
        const g = document.createElement("span");
        g.className = "gain";
        g.textContent = "+" + fmt(answers.atp);
        els.atpBox.appendChild(g);
        setTimeout(() => g.remove(), 1000);
      }
      els.glyph.classList.remove("bump"); void els.glyph.offsetWidth; els.glyph.classList.add("bump");
    }
    for (const e of events) {
      if (e.t === "vesicle") {
        const A = art();
        if (A) els.ves.firstElementChild.outerHTML = A.vesicle(e.r, 16);
        els.ves.classList.remove("pop"); void els.ves.offsetWidth; els.ves.classList.add("pop");
        if (e.r === "epic" || e.r === "legendary") say("vesicle", `${cap(e.r)} vesicle!`, "open it later");
      } else if (e.t === "achievement") say("achievement", e.name, "trophy unlocked");
      else if (e.t === "level") say("level", `Level ${e.level}`, e.title);
      else if (e.t === "quest") say("quest", "Quest done", e.label);
      else if (e.t === "quests_all") say("quests_all", "All quests done", "epic vesicle");
      else if (e.t === "goal") say("goal", "Daily goal hit", e.atp > 0 ? `+${fmt(e.atp)} dividend` : "streak safe");
      else if (e.t === "sweep") say("sweep", "Clean sweep", "all reviews done");
      else if (e.t === "comeback") say("comeback", "Welcome back", "Mito missed you");
      else if (e.t === "undo") say("undo", "Undone", `−${fmt(e.atp)} ATP`);
      else if (e.t === "nocount") {
        for (const why of ["quick", "steady", "repeat"]) {
          if (!e[why]) continue;
          const now = Date.now();
          if (nocountSaid[why] && now - nocountSaid[why] < 90000) continue;
          nocountSaid[why] = now;
          say("nocount", NOCOUNT[why][0], NOCOUNT[why][1]);
          break;
        }
      }
    }
  }

  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  // Pop-ups replace the pill's content for a moment instead of covering anything.
  function say(kind, title, sub) {
    if (opts.toasts === false || !host) return;
    queue.push({ kind, title, sub });
    if (queue.length > 3) queue.splice(0, queue.length - 3);
    if (!talking) next();
  }

  function next() {
    const t = queue.shift();
    if (!t) { talking = false; els.pill.classList.remove("talking"); return; }
    talking = true;
    const A = art();
    const [icon, color] = KIND[t.kind] || ["spark", "#F3EFFF"];
    els.msg.querySelector(".ic").innerHTML = A ? A.icon(icon, 16) : "";
    els.msg.querySelector(".ic").style.color = color;
    els.msg.querySelector("b").textContent = t.title;
    els.msg.querySelector("span:last-child").textContent = t.sub || "";
    els.pill.classList.add("talking");
    setTimeout(() => {
      els.pill.classList.remove("talking");
      setTimeout(next, opts.reduceMotion ? 0 : 300);
    }, 2400);
  }

  function setVisible(v) { if (host) host.style.display = v ? "" : "none"; }

  window.PowerhouseHUD = { mount, update, setVisible };
})();
