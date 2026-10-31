/* Powerhouse: Mito the mitochondrion, plus shared icons and number formatting.
   Pure functions that return SVG strings. No DOM access at load time. */
(function () {
  "use strict";
  if (window.PowerhouseArt) return;

  const SKINS = {
    skin_coral: { body: ["#FF8C7E", "#FF5A5F"], edge: "#C93A4C", matrix: "#FFC2B5", fold: "#E8565C", cheek: "#FF9DB0" },
    skin_gfp: { body: ["#8DF7B5", "#2FD47E"], edge: "#178A57", matrix: "#D6FFE4", fold: "#2DB872", cheek: "#FFB3C7" },
    skin_brownfat: { body: ["#C99372", "#93603F"], edge: "#6B3F27", matrix: "#EBCDB5", fold: "#A8704C", cheek: "#F2A0A0" },
    skin_golden: { body: ["#FFE68A", "#F7B500"], edge: "#B07A00", matrix: "#FFF4C2", fold: "#E0A300", cheek: "#FFB38A" },
    skin_galaxy: { body: ["#7B5CFF", "#2B1E7A"], edge: "#1A1250", matrix: "#4A3AAE", fold: "#9C86FF", cheek: "#FF8AD8" },
    skin_holo: { body: ["#9FF6FF", "#F7A6FF"], edge: "#7C6BD6", matrix: "#F4F1FF", fold: "#B69CFF", cheek: "#FF9AC2" },
  };

  let uid = 0;

  function body(skin, id) {
    const s = SKINS[skin] || SKINS.skin_coral;
    // Outer membrane: a plump bean. Inner membrane (matrix) inset inside it.
    const outer = "M38 92 C30 56 60 30 102 30 C146 30 176 52 170 90 C166 124 136 142 100 140 C62 138 42 124 38 92 Z";
    const inner = "M50 92 C45 63 70 43 102 43 C136 43 159 60 157 90 C155 117 131 129 100 128 C69 127 54 117 50 92 Z";
    // Cristae: the classic folded inner membrane, drawn as a belly band of folds
    const cristae = "M56 114 C60 100 66 100 68 112 C70 124 76 124 78 108 C80 96 88 96 90 110 C92 124 98 124 100 108 " +
      "C102 96 110 96 112 110 C114 124 120 124 122 108 C124 96 132 96 134 110 C136 122 142 122 146 106";
    let extra = "";
    if (skin === "skin_galaxy") {
      const stars = [[70, 60], [128, 56], [146, 96], [84, 66], [116, 60], [62, 96], [152, 76]];
      extra = stars.map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="${i % 3 ? 1.4 : 2.2}" fill="#fff" opacity="${i % 2 ? .9 : .6}"/>`).join("");
    }
    if (skin === "skin_golden") {
      extra = `<path d="M150 46 L152.5 52 L159 54 L152.5 56 L150 62 L147.5 56 L141 54 L147.5 52 Z" fill="#fff" opacity=".9"/>
        <path d="M58 118 L59.6 122 L64 123.5 L59.6 125 L58 129 L56.4 125 L52 123.5 L56.4 122 Z" fill="#fff" opacity=".8"/>`;
    }
    const holo = skin === "skin_holo"
      ? `<animate attributeName="x1" values="0;1;0" dur="6s" repeatCount="indefinite"/>`
      : "";
    return `
      <defs>
        <linearGradient id="b${id}" x1="0" y1="0" x2="1" y2="1">${holo}
          <stop offset="0" stop-color="${s.body[0]}"/><stop offset="1" stop-color="${s.body[1]}"/>
        </linearGradient>
        <radialGradient id="m${id}" cx=".45" cy=".3" r=".8">
          <stop offset="0" stop-color="#fff" stop-opacity=".6"/><stop offset=".55" stop-color="${s.matrix}"/>
          <stop offset="1" stop-color="${s.matrix}"/>
        </radialGradient>
        <clipPath id="c${id}"><path d="${inner}"/></clipPath>
      </defs>
      <ellipse class="mito-shadow" cx="104" cy="150" rx="52" ry="6" fill="#000" opacity=".22"/>
      <g class="mito-feet" fill="${s.edge}">
        <ellipse cx="80" cy="140" rx="11" ry="6"/><ellipse cx="124" cy="140" rx="11" ry="6"/>
      </g>
      <path d="${outer}" fill="url(#b${id})" stroke="${s.edge}" stroke-width="3"/>
      <path d="${inner}" fill="url(#m${id})" stroke="${s.fold}" stroke-width="2.6"/>
      <g clip-path="url(#c${id})"><g transform="translate(0 4)">
        <path d="${cristae}" fill="none" stroke="${s.body[1]}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" opacity=".35"/>
        <path d="${cristae}" fill="none" stroke="${s.fold}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>
      </g></g>
      ${extra}
      <path d="M60 68 C64 55 78 46 96 44" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="5" stroke-linecap="round"/>
      <g class="mito-face">
        <g class="mito-eyes">
          <ellipse cx="86" cy="78" rx="7.5" ry="9.5" fill="#24163A"/>
          <ellipse cx="120" cy="78" rx="7.5" ry="9.5" fill="#24163A"/>
          <circle cx="88.5" cy="74" r="3" fill="#fff"/><circle cx="122.5" cy="74" r="3" fill="#fff"/>
          <circle cx="84" cy="82" r="1.4" fill="#fff" opacity=".8"/><circle cx="118" cy="82" r="1.4" fill="#fff" opacity=".8"/>
        </g>
        <ellipse cx="72" cy="92" rx="8" ry="4.5" fill="${s.cheek}" opacity=".8"/>
        <ellipse cx="134" cy="92" rx="8" ry="4.5" fill="${s.cheek}" opacity=".8"/>
        <path class="mito-mouth" d="M96 92 Q103 99 110 92" fill="none" stroke="#24163A" stroke-width="3" stroke-linecap="round"/>
      </g>`;
  }

  const HATS = {
    hat_scrubcap: `
      <path d="M58 52 C58 26 80 14 102 14 C126 14 148 26 148 52 C132 46 118 44 102 44 C86 44 72 46 58 52 Z" fill="#3FB8A9" stroke="#1F7F74" stroke-width="2.5"/>
      <path d="M58 52 C72 46 86 44 102 44 C118 44 132 46 148 52" fill="none" stroke="#1F7F74" stroke-width="5" stroke-linecap="round"/>
      <g fill="#E8FFFB" opacity=".9"><circle cx="82" cy="28" r="2.2"/><circle cx="100" cy="22" r="2.2"/><circle cx="118" cy="27" r="2.2"/>
      <circle cx="92" cy="36" r="2.2"/><circle cx="112" cy="35" r="2.2"/><circle cx="130" cy="38" r="2"/><circle cx="72" cy="40" r="2"/></g>
      <path d="M146 50 C154 52 158 58 156 64" fill="none" stroke="#1F7F74" stroke-width="3" stroke-linecap="round"/>`,
    hat_beanie: `
      <circle cx="102" cy="8" r="9" fill="#F4F1FF" stroke="#C9C2E8" stroke-width="2"/>
      <path d="M60 50 C60 24 80 12 102 12 C126 12 146 24 146 50 Z" fill="#6E8BFF" stroke="#4458C9" stroke-width="2.5"/>
      <g stroke="#5A73F0" stroke-width="3" opacity=".7"><path d="M80 18 L78 48"/><path d="M102 13 L102 48"/><path d="M124 18 L126 48"/></g>
      <rect x="56" y="42" width="94" height="14" rx="7" fill="#4F66E0" stroke="#3446B8" stroke-width="2.5"/>`,
    hat_party: `
      <path d="M102 -14 L80 40 L124 40 Z" fill="#FF7AB6" stroke="#C5427F" stroke-width="2.5" stroke-linejoin="round"/>
      <path d="M93 8 L111 8 M87 22 L117 22" stroke="#FFE36E" stroke-width="5" stroke-linecap="round"/>
      <circle cx="102" cy="-14" r="6" fill="#FFE36E" stroke="#D6A92B" stroke-width="2"/>`,
    hat_grad: `
      <path d="M72 32 C72 42 86 48 102 48 C118 48 132 42 132 32 L132 26 L72 26 Z" fill="#2E2450" stroke="#17112E" stroke-width="2.5"/>
      <path d="M50 22 L102 4 L154 22 L102 40 Z" fill="#3A2E66" stroke="#17112E" stroke-width="2.5" stroke-linejoin="round"/>
      <circle cx="102" cy="22" r="3.5" fill="#FFC94D"/>
      <path d="M102 22 L138 30 L140 52" fill="none" stroke="#FFC94D" stroke-width="2.5" stroke-linecap="round"/>
      <path d="M136 50 L144 50 L142 62 L138 62 Z" fill="#FFC94D"/>`,
    hat_mirror: `
      <path d="M50 58 C54 38 76 26 102 26 C128 26 150 38 154 58" fill="none" stroke="#3B3355" stroke-width="7" stroke-linecap="round"/>
      <circle cx="102" cy="40" r="18" fill="url(#mirrorG)" stroke="#8D88A8" stroke-width="3"/>
      <circle cx="102" cy="40" r="4" fill="#2A2440"/>
      <path d="M92 32 C95 28 99 27 103 27" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round" opacity=".8"/>
      <defs><radialGradient id="mirrorG" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#B9B4D0"/></radialGradient></defs>`,
    hat_propeller: `
      <path d="M62 50 C62 24 82 14 102 14 C124 14 144 24 144 50 Z" fill="#FF6B5E" stroke="#B83A3A" stroke-width="2.5"/>
      <path d="M102 14 C92 24 88 38 88 50 L102 50 Z" fill="#FFD25E"/><path d="M102 14 C112 24 118 38 120 50 L144 50 C142 30 126 16 102 14 Z" fill="#6EA8FF"/>
      <rect x="99" y="2" width="6" height="14" rx="2" fill="#3B3355"/>
      <g class="ph-spin" style="transform-origin:102px 2px"><ellipse cx="86" cy="2" rx="16" ry="4" fill="#7CF29C" stroke="#2F9E5B" stroke-width="2"/>
      <ellipse cx="118" cy="2" rx="16" ry="4" fill="#B884FF" stroke="#7448C2" stroke-width="2"/></g>
      <circle cx="102" cy="2" r="3.5" fill="#3B3355"/>`,
    hat_halo: `
      <ellipse cx="102" cy="12" rx="34" ry="9" fill="none" stroke="#FFE07A" stroke-width="6" opacity=".95"/>
      <ellipse cx="102" cy="12" rx="34" ry="9" fill="none" stroke="#FFF6CF" stroke-width="2"/>`,
    hat_crown: `
      <path d="M66 46 L62 12 L82 28 L102 6 L122 28 L142 12 L138 46 Z" fill="#FFC94D" stroke="#B07A00" stroke-width="2.5" stroke-linejoin="round"/>
      <rect x="64" y="40" width="76" height="10" rx="4" fill="#F5B000" stroke="#B07A00" stroke-width="2.5"/>
      <circle cx="102" cy="26" r="5" fill="#FF5A7A"/><circle cx="80" cy="35" r="3.5" fill="#6EA8FF"/><circle cx="124" cy="35" r="3.5" fill="#7CF29C"/>
      <circle cx="62" cy="12" r="3" fill="#FFE68A"/><circle cx="102" cy="6" r="3" fill="#FFE68A"/><circle cx="142" cy="12" r="3" fill="#FFE68A"/>`,
  };

  const FACES = {
    face_glasses: `
      <circle cx="86" cy="79" r="14" fill="#BFE6FF" fill-opacity=".25" stroke="#2A2140" stroke-width="3.5"/>
      <circle cx="120" cy="79" r="14" fill="#BFE6FF" fill-opacity=".25" stroke="#2A2140" stroke-width="3.5"/>
      <path d="M100 78 Q103 74 106 78" fill="none" stroke="#2A2140" stroke-width="3.5"/>
      <path d="M72 76 L58 70 M134 76 L148 70" stroke="#2A2140" stroke-width="3" stroke-linecap="round"/>`,
    face_mask: `
      <path d="M76 88 C76 84 130 84 130 88 L128 108 C118 114 88 114 78 108 Z" fill="#A9DBF5" stroke="#5FA7CF" stroke-width="2.5"/>
      <path d="M80 95 L126 95 M82 102 L124 102" stroke="#7FBFE2" stroke-width="2.2"/>
      <path d="M77 90 C66 88 60 82 58 76 M129 90 C140 88 146 82 148 76" fill="none" stroke="#E6F5FD" stroke-width="2.2"/>`,
    face_monocle: `
      <circle cx="120" cy="78" r="14" fill="#E9F6FF" fill-opacity=".2" stroke="#C9A227" stroke-width="3.5"/>
      <path d="M131 88 C138 100 136 114 128 128" fill="none" stroke="#C9A227" stroke-width="2" stroke-dasharray="3 3"/>`,
    face_shades: `
      <path d="M86 65 L90 74 L100 75 L93 82 L95 92 L86 87 L77 92 L79 82 L72 75 L82 74 Z" fill="#FF5FB0" stroke="#2A2140" stroke-width="2.5" stroke-linejoin="round"/>
      <path d="M120 65 L124 74 L134 75 L127 82 L129 92 L120 87 L111 92 L113 82 L106 75 L116 74 Z" fill="#B884FF" stroke="#2A2140" stroke-width="2.5" stroke-linejoin="round"/>
      <path d="M99 78 L107 78" stroke="#2A2140" stroke-width="3"/>`,
  };

  const NECKS = {
    neck_bowtie: `
      <path d="M102 128 L84 118 L84 138 Z" fill="#FF5A7A" stroke="#B02E4C" stroke-width="2.5" stroke-linejoin="round"/>
      <path d="M102 128 L120 118 L120 138 Z" fill="#FF5A7A" stroke="#B02E4C" stroke-width="2.5" stroke-linejoin="round"/>
      <rect x="97" y="122" width="10" height="12" rx="3" fill="#E04466" stroke="#B02E4C" stroke-width="2"/>`,
    neck_badge: `
      <path d="M72 116 L96 132 M132 116 L108 132" stroke="#6EA8FF" stroke-width="3.5" stroke-linecap="round"/>
      <rect x="90" y="128" width="24" height="30" rx="3" fill="#FFFFFF" stroke="#5A6A9A" stroke-width="2"/>
      <rect x="94" y="133" width="9" height="10" rx="1.5" fill="#FF8C7E"/>
      <path d="M94 148 L110 148 M94 153 L106 153" stroke="#9AA6C8" stroke-width="2"/>`,
    neck_stetho: `
      <path d="M64 112 C70 136 134 136 140 112" fill="none" stroke="#3B3355" stroke-width="5" stroke-linecap="round"/>
      <path d="M116 132 C120 140 122 146 122 150" fill="none" stroke="#3B3355" stroke-width="4" stroke-linecap="round"/>
      <circle cx="122" cy="154" r="7" fill="#C9C4DE" stroke="#6E6890" stroke-width="2.5"/>`,
    neck_scarf: `
      <path d="M64 116 C80 132 124 132 140 116 L144 126 C126 142 78 142 60 126 Z" fill="#FFB347" stroke="#C47A12" stroke-width="2.5"/>
      <path d="M118 132 L124 160 L136 156 L128 130 Z" fill="#FF9F2E" stroke="#C47A12" stroke-width="2.5"/>
      <path d="M72 126 L80 132 M90 130 L96 134 M108 132 L114 132" stroke="#E9851A" stroke-width="2"/>`,
    neck_medal: `
      <path d="M86 112 L96 136 M118 112 L108 136" stroke="#6EA8FF" stroke-width="6"/>
      <circle cx="102" cy="144" r="12" fill="#FFC94D" stroke="#B07A00" stroke-width="2.5"/>
      <path d="M102 136 L104.5 141.5 L110 142 L106 146 L107 152 L102 149 L97 152 L98 146 L94 142 L99.5 141.5 Z" fill="#FFF0B8"/>`,
  };

  const STAGES = {
    stage_confocal: { bg: ["#2A2268", "#120F26"], specks: ["#6EA8FF", "#7CF29C", "#FF6B5E"], light: false },
    stage_he: { bg: ["#FBE6EE", "#E9B9CF"], specks: ["#6B3FA0", "#8E5CC0", "#C76A9A"], light: true },
    stage_gram: { bg: ["#F5EEF8", "#DCCBE6"], specks: ["#5B2A86", "#E05A8A", "#7C3FB0"], light: true },
    stage_em: { bg: ["#7C7C84", "#2A2A30"], specks: ["#DADAE0", "#9A9AA4", "#BFBFC8"], light: false },
  };

  function mito(opts) {
    opts = opts || {};
    const id = "ph" + (++uid);
    const eq = opts.equipped || {};
    const skin = eq.skin || "skin_coral";
    const size = opts.size || 200;
    const mood = opts.mood || "happy";
    let faceTweak = "";
    if (mood === "sleepy") {
      faceTweak = `<style>#${id} .mito-eyes ellipse{transform:scaleY(.18);transform-box:fill-box;transform-origin:center}
        #${id} .mito-eyes circle{display:none}</style>`;
    }
    const hat = eq.hat && HATS[eq.hat] ? `<g class="mito-hat">${HATS[eq.hat]}</g>` : "";
    const face = eq.face && FACES[eq.face] ? `<g class="mito-acc">${FACES[eq.face]}</g>` : "";
    const neck = eq.neck && NECKS[eq.neck] ? `<g class="mito-acc">${NECKS[eq.neck]}</g>` : "";
    const cls = ["mito"].concat(opts.animate === false ? [] : ["mito-anim"]).join(" ");
    return `<svg id="${id}" class="${cls}" viewBox="0 -20 204 186" width="${size}" height="${Math.round(size * 186 / 204)}"
      role="img" aria-label="Mito the mitochondrion">${faceTweak}
      <g class="mito-bob">${body(skin, id)}${neck}${face}${hat}</g></svg>`;
  }

  // Small glyph for tight spaces (HUD, toolbar)
  function glyph(size) {
    size = size || 22;
    return `<svg viewBox="0 0 32 24" width="${size}" height="${Math.round(size * 24 / 32)}" aria-hidden="true">
      <path d="M3 12 C2 5 8 2 16 2 C25 2 30 6 29 12 C28 19 23 22 16 22 C8 22 4 19 3 12 Z" fill="#FF6B5E" stroke="#C93A4C" stroke-width="1.6"/>
      <path d="M7 12 C6 7 10 5 16 5 C22 5 26 8 25 12 C24 17 21 19 16 19 C10 19 8 17 7 12 Z" fill="#FFC2B5"/>
      <path d="M11 6 C10 10 10 13 12 15 M16 5 C15 9 15 12 17 14 M21 6 C20 9 20 12 22 14" fill="none" stroke="#E8565C" stroke-width="1.4" stroke-linecap="round"/>
    </svg>`;
  }

  function stage(stageId) {
    return STAGES[stageId] || STAGES.stage_confocal;
  }

  // Line icons (24×24, currentColor) for pathways, upgrades and UI
  const ICONS = {
    glycolysis: `<path d="M12 3 L19.5 7.5 L19.5 16.5 L12 21 L4.5 16.5 L4.5 7.5 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="12" cy="3" r="1.6" fill="currentColor"/>`,
    pdh: `<circle cx="7" cy="9" r="3.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="17" cy="9" r="3.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="17" r="3.5" fill="none" stroke="currentColor" stroke-width="2"/>`,
    krebs: `<path d="M19 12 A7 7 0 1 1 12 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M12 1.5 L15.5 5 L12 8.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
    etc: `<rect x="2" y="8" width="4" height="8" rx="1" fill="currentColor"/><rect x="8" y="6" width="4" height="12" rx="1" fill="currentColor" opacity=".8"/><rect x="14" y="8" width="4" height="8" rx="1" fill="currentColor" opacity=".65"/><path d="M19 12 L23 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    synthase: `<circle cx="12" cy="8" r="5.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2.5 L12 13.5 M6.5 8 L17.5 8" stroke="currentColor" stroke-width="1.6"/><path d="M12 13.5 L12 21 M8 21 L16 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    betaox: `<path d="M2 15 L6 9 L10 15 L14 9 L18 15 L22 9" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`,
    ketones: `<path d="M5 17 L12 7 L19 17 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 7 L12 2" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="2.5" r="1.8" fill="currentColor"/>`,
    creatine: `<rect x="3" y="6" width="16" height="12" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><rect x="19.5" y="10" width="2.5" height="4" rx="1" fill="currentColor"/><path d="M12 7.5 L8.5 12.5 L11.5 12.5 L10 16.5 L14 11 L11 11 Z" fill="currentColor"/>`,
    // slow-twitch fibers (id kept from the old brown fat pathway): a striated muscle fiber
    brownfat: `<path d="M2 12 C6 6 18 6 22 12 C18 18 6 18 2 12 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M8 8.6 V15.4 M12 7.6 V16.4 M16 8.6 V15.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
    biogenesis: `<ellipse cx="9" cy="12" rx="6.5" ry="4.5" fill="none" stroke="currentColor" stroke-width="2"/><ellipse cx="15" cy="12" rx="6.5" ry="4.5" fill="none" stroke="currentColor" stroke-width="2" opacity=".7"/>`,
    coffee: `<path d="M4 9 H16 V14 A5 5 0 0 1 11 19 H9 A5 5 0 0 1 4 14 Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 10 H18 A2.5 2.5 0 0 1 18 15 H16" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 3 C7 5 9 5 8 7 M12 3 C11 5 13 5 12 7" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>`,
    water: `<path d="M9 2 H15 V5 C17 6 18 8 18 10 V20 A2 2 0 0 1 16 22 H8 A2 2 0 0 1 6 20 V10 C6 8 7 6 9 5 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M6 14 H18" stroke="currentColor" stroke-width="1.6"/>`,
    headphones: `<path d="M4 15 V12 A8 8 0 0 1 20 12 V15" fill="none" stroke="currentColor" stroke-width="2"/><rect x="3" y="14" width="5" height="7" rx="2" fill="currentColor"/><rect x="16" y="14" width="5" height="7" rx="2" fill="currentColor"/>`,
    pomodoro: `<circle cx="12" cy="13.5" r="7.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 13.5 L12 9.5 M12 13.5 L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M9 4 C10 5.5 14 5.5 15 4 M12 4.5 V2" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>`,
    desk: `<path d="M3 9 H21 M6 9 V21 M18 9 V21 M6 15 H18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><rect x="9" y="3" width="6" height="4" rx="1" fill="currentColor"/>`,
    sleep: `<path d="M20 14.5 A8 8 0 1 1 9.5 4 A6.5 6.5 0 0 0 20 14.5 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M15 3 H19 L15 7 H19" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>`,
    group: `<circle cx="8" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="16" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M2.5 19 A5.5 5.5 0 0 1 13.5 19 M10.5 19 A5.5 5.5 0 0 1 21.5 19" fill="none" stroke="currentColor" stroke-width="2"/>`,
    annotated: `<path d="M4 4 H11 A2 2 0 0 1 12 6 V20 A2 2 0 0 0 11 19 H4 Z M20 4 H13 A2 2 0 0 0 12 6 V20 A2 2 0 0 1 13 19 H20 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M15 9 H18 M15 12 H18" stroke="currentColor" stroke-width="1.6"/>`,
    qbank: `<path d="M4 5 H20 V15 H11 L6 19.5 V15 H4 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M10 8.5 A2 2 0 1 1 12.5 10.5 L12 12" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/>`,
    mastery: `<path d="M12 3 A8 8 0 1 0 20 11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M20 3 L20 8 L15 8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="11" r="2.5" fill="currentColor"/>`,
    boards: `<rect x="3" y="4" width="18" height="13" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="16" cy="17.5" r="3.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M14.5 20.5 L13.5 23 M17.5 20.5 L18.5 23 M6 8 H14 M6 11 H11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>`,
    attending: `<path d="M12 2.5 L14.6 8.6 L21 9.1 L16 13.3 L17.6 19.6 L12 16.2 L6.4 19.6 L8 13.3 L3 9.1 L9.4 8.6 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>`,
    clathrin: `<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 4 L12 20 M5 8 L19 16 M5 16 L19 8" stroke="currentColor" stroke-width="1.4" opacity=".7"/>`,
    snare: `<path d="M4 6 C10 10 14 14 20 18 M4 18 C10 14 14 10 20 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="12" r="2.4" fill="currentColor"/>`,
    rab: `<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2.5"/><path d="M9 12 L11.5 14.5 L15.5 9.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
    dynamin: `<path d="M3 12 C7 7 10 7 12 12 C14 17 17 17 21 12" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 6 V18" stroke="currentColor" stroke-width="2" stroke-dasharray="2 2"/>`,
    flow: `<path d="M3 9 C6 6 9 6 12 9 C15 12 18 12 21 9 M3 15 C6 12 9 12 12 15 C15 18 18 18 21 15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    vesicle: `<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="5.5" fill="none" stroke="currentColor" stroke-width="1.4" opacity=".6"/><circle cx="9.5" cy="9.5" r="1.5" fill="currentColor"/>`,
    flame: `<path d="M12 2.5 C15 7 18 9.5 18 14 A6 6 0 0 1 6 14 C6 11 8 9 9 7 C10 9.5 11 10 12 10 C12 7.5 11 5 12 2.5 Z" fill="currentColor"/>`,
    freeze: `<path d="M12 2 V22 M3.5 7 L20.5 17 M3.5 17 L20.5 7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M9.5 4 L12 6.5 L14.5 4 M9.5 20 L12 17.5 L14.5 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
    trophy: `<path d="M7 3 H17 V9 A5 5 0 0 1 7 9 Z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7 5 H3.5 A3.5 3.5 0 0 0 7 10.5 M17 5 H20.5 A3.5 3.5 0 0 1 17 10.5 M12 14 V18 M8 21 H16 L15 18 H9 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>`,
    quest: `<rect x="4" y="3" width="16" height="18" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 9 L10 11 L13.5 7.5 M8 15.5 H16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`,
    enzyme: `<path d="M5 6 C5 4 7 3 9 4 L15 7 C17 8 17 10 15 11 L11 13 L15 15 C17 16 17 18 15 19 L9 21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7" cy="12" r="2" fill="currentColor"/>`,
    lock: `<rect x="5" y="11" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 11 V8 A4 4 0 0 1 16 8 V11" fill="none" stroke="currentColor" stroke-width="2"/>`,
    check: `<path d="M5 12.5 L10 17.5 L19 7.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>`,
    close: `<path d="M6 6 L18 18 M18 6 L6 18" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>`,
    gear: `<circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2.5 V5.5 M12 18.5 V21.5 M2.5 12 H5.5 M18.5 12 H21.5 M5.3 5.3 L7.4 7.4 M16.6 16.6 L18.7 18.7 M5.3 18.7 L7.4 16.6 M16.6 7.4 L18.7 5.3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`,
    split: `<ellipse cx="7.5" cy="12" rx="5" ry="6.5" fill="none" stroke="currentColor" stroke-width="2"/><ellipse cx="16.5" cy="12" rx="5" ry="6.5" fill="none" stroke="currentColor" stroke-width="2"/>`,
    atp: `<path d="M13 2 L5 13 H11 L10 22 L19 10 H13 Z" fill="currentColor"/>`,
    stats: `<path d="M4 20 V12 M10 20 V5 M16 20 V9 M22 20 H2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>`,
    shirt: `<path d="M8 3 L4 5.5 L2 10 L6 11.5 L6 21 H18 V11.5 L22 10 L20 5.5 L16 3 C15 5 9 5 8 3 Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>`,
    book: `<path d="M4 4.5 A1.5 1.5 0 0 1 5.5 3 H19 V18 H5.5 A1.5 1.5 0 0 0 4 19.5 Z M4 19.5 A1.5 1.5 0 0 0 5.5 21 H19 V18" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>`,
    spark: `<path d="M12 2 L13.8 9.2 L21 11 L13.8 12.8 L12 20 L10.2 12.8 L3 11 L10.2 9.2 Z" fill="currentColor"/>`,
  };

  function icon(name, size) {
    const body = ICONS[name] || ICONS.spark;
    size = size || 20;
    return `<svg class="ph-icon" viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">${body}</svg>`;
  }

  // Vesicle bubble: a lipid bilayer ring with cargo dots
  const RARITY_COLORS = {
    common: ["#E4E8FF", "#8E9BD0"],
    rare: ["#7FD6FF", "#2F9BE0"],
    epic: ["#D2A8FF", "#9056E8"],
    legendary: ["#FFE08A", "#F0A800"],
  };

  function vesicle(rarity, size) {
    const c = RARITY_COLORS[rarity] || RARITY_COLORS.common;
    const id = "v" + (++uid);
    size = size || 64;
    const dots = [];
    for (let i = 0; i < 18; i++) {
      const a = (i / 18) * Math.PI * 2;
      dots.push(`<circle cx="${32 + Math.cos(a) * 25.5}" cy="${32 + Math.sin(a) * 25.5}" r="1.9" fill="${c[1]}"/>`);
      dots.push(`<circle cx="${32 + Math.cos(a + 0.17) * 21.5}" cy="${32 + Math.sin(a + 0.17) * 21.5}" r="1.6" fill="${c[1]}" opacity=".8"/>`);
    }
    return `<svg class="ph-vesicle" viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true">
      <defs><radialGradient id="${id}" cx=".38" cy=".32" r=".75">
        <stop offset="0" stop-color="#fff" stop-opacity=".9"/><stop offset=".45" stop-color="${c[0]}" stop-opacity=".55"/>
        <stop offset="1" stop-color="${c[1]}" stop-opacity=".35"/></radialGradient></defs>
      <circle cx="32" cy="32" r="27" fill="url(#${id})"/>
      ${dots.join("")}
      <circle cx="32" cy="32" r="27.5" fill="none" stroke="${c[1]}" stroke-width="1.5" opacity=".6"/>
      <circle cx="32" cy="32" r="19.5" fill="none" stroke="${c[1]}" stroke-width="1.2" opacity=".45"/>
      <circle cx="28" cy="36" r="4" fill="${c[1]}" opacity=".55"/><circle cx="37" cy="30" r="3" fill="${c[1]}" opacity=".45"/>
      <ellipse cx="24" cy="21" rx="6" ry="3.5" fill="#fff" opacity=".7" transform="rotate(-30 24 21)"/>
    </svg>`;
  }

  // Number formatting shared by every view
  const UNITS = ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"];

  function fmt(n, opts) {
    opts = opts || {};
    if (n === null || n === undefined || !isFinite(n)) return "0";
    const neg = n < 0;
    n = Math.abs(n);
    let out;
    if (n < 10 && opts.decimals !== 0) {
      out = n >= 1 || n === 0 ? (Math.round(n * 10) / 10).toString() : n.toFixed(2);
      if (out.endsWith(".0")) out = out.slice(0, -2);
    } else if (n < 1e4) {
      out = Math.floor(n).toLocaleString("en-US");
    } else {
      let i = Math.floor(Math.log10(n) / 3);
      i = Math.min(i, UNITS.length - 1);
      let v = n / Math.pow(1000, i);
      if (v >= 999.5 && i < UNITS.length - 1) { i += 1; v = n / Math.pow(1000, i); }
      out = (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2)).replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1") + UNITS[i];
    }
    return (neg ? "−" : "") + out;
  }

  function fmtLong(n) {
    if (!isFinite(n)) return "0";
    if (n < 1e6) return Math.floor(n).toLocaleString("en-US");
    const words = ["", "thousand", "million", "billion", "trillion", "quadrillion", "quintillion", "sextillion", "septillion", "octillion", "nonillion", "decillion"];
    let i = Math.floor(Math.log10(n) / 3);
    i = Math.min(i, words.length - 1);
    const v = n / Math.pow(1000, i);
    return `${v.toFixed(v >= 100 ? 0 : 2).replace(/\.?0+$/, "")} ${words[i]}`;
  }

  window.PowerhouseArt = { mito, glyph, icon, vesicle, stage, fmt, fmtLong, RARITY_COLORS, SKINS, HATS, FACES, NECKS };
})();
