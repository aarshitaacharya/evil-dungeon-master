"use strict";
/* Evil Dungeon Master: replay viewer.
 *
 * It plays back the event stream written by main.py (events.jsonl). It never
 * re-implements game rules: every turn event carries a state snapshot, and the
 * rigged world arrives in round_setup. No AI calls happen here.
 */

const T = 16;                      // tile size in source pixels
const RW = 8, RH = 6, GAP = 1;     // room size and corridor gap, in tiles
const PACK = "/assets/pack/", ENEMY = "/assets/enemies/";
const $ = (s) => document.querySelector(s);
const ctx = $("#map").getContext("2d"), dmCtx = $("#dmc").getContext("2d"), invCtx = $("#inv").getContext("2d");
[ctx, dmCtx, invCtx].forEach((c) => (c.imageSmoothingEnabled = false));

// ---------------------------------------------------------------- assets ---
const IMG = {};
function load(name, url) {
  return new Promise((done) => {
    const img = new Image();
    img.onload = () => { IMG[name] = img; done(); };
    img.onerror = () => { console.warn("missing asset", url); done(); };
    img.src = encodeURI(url);
  });
}
async function loadAssets() {
  const items = PACK + "items and trap_animation/";
  const jobs = [
    load("tiles", PACK + "character and tileset/Dungeon_Tileset.png"),
    load("chars", PACK + "character and tileset/Dungeon_Character.png"),
    load("vamp_idle", ENEMY + "enemies-vampire_idle.png"),
    load("vamp_attack", ENEMY + "enemies-vampire_attack.png"),
    load("vamp_hurt", ENEMY + "enemies-vampire_take_damage.png"),
  ];
  const anim = (key, folder, file) => { for (let i = 1; i <= 4; i++) jobs.push(load(`${key}${i}`, `${items}${folder}/${file}_${i}.png`)); };
  anim("chest", "chest", "chest"); anim("chestopen", "chest", "chest_open"); anim("crate", "box_1", "box_1");
  anim("flasks", "flasks", "flasks_1"); anim("candle", "torch", "candlestick_1"); anim("torch", "torch", "torch");
  anim("coin", "coin", "coin");
  await Promise.all(jobs);
  IMG.goose = makeGoose();
}

// A pixel goose, since the pack has no animals. Outline is added automatically.
function makeGoose() {
  const rows = [
    "................", "......ww........", ".....wwww.......", ".....wkwwoo.....", ".....wwwwoo.....", "......www.......",
    "......www.......", "....wwwwwww.....", "...wwwwwwwwww...", "..wwwwssswwwww..", "..wwwwsssswwww..", "...wwwwwwwwww...",
    "....wwwwwwww....", ".....o..o.......", ".....o..o.......", "....oo.oo.......",
  ];
  const col = { w: "#f4f0e8", s: "#c9c2d6", o: "#ef9a3c", k: "#1b1021" };
  const c = document.createElement("canvas"); c.width = c.height = 16;
  const g = c.getContext("2d");
  const filled = (x, y) => rows[y] && rows[y][x] && rows[y][x] !== ".";
  for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
    if (filled(x, y)) { g.fillStyle = col[rows[y][x]]; g.fillRect(x, y, 1, 1); }
    else if ([[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => filled(x + dx, y + dy))) { g.fillStyle = "#1b1021"; g.fillRect(x, y, 1, 1); }
  }
  return c;
}

// ---------------------------------------------------------------- layout ---
const DIRS = { north: [0, -1], south: [0, 1], east: [1, 0], west: [-1, 0] };
const OPP = { north: "south", south: "north", east: "west", west: "east" };

/** Place rooms on a grid by following exits; return pixel origins and map size. */
function computeLayout(world) {
  const grid = { [world.start]: [0, 0] }, queue = [world.start];
  while (queue.length) {
    const r = queue.shift();
    for (const [d, ex] of Object.entries(world.rooms[r].exits)) {
      if (grid[ex.to]) continue;
      grid[ex.to] = [grid[r][0] + DIRS[d][0], grid[r][1] + DIRS[d][1]];
      if (world.rooms[ex.to]) queue.push(ex.to);
    }
  }
  const height = (r) => (r === "outside" ? 3 : RH);
  const gys = [...new Set(Object.values(grid).map((p) => p[1]))].sort((a, b) => a - b);
  const rowH = Object.fromEntries(gys.map((gy) => [gy, Math.max(...Object.entries(grid).filter(([, p]) => p[1] === gy).map(([r]) => height(r)))]));
  const rowY = {}; let y = 0;
  for (const gy of gys) { rowY[gy] = y; y += rowH[gy] + GAP; }
  const minX = Math.min(...Object.values(grid).map((p) => p[0])), maxX = Math.max(...Object.values(grid).map((p) => p[0]));
  const origin = {};
  for (const [r, [gx, gy]] of Object.entries(grid)) origin[r] = [(gx - minX) * (RW + GAP) * T, rowY[gy] * T];
  return { origin, width: (maxX - minX + 1) * (RW + GAP) * T - GAP * T, height: (y - GAP) * T };
}

const FEATURE_SLOTS = [[1.5, 1.5], [6.5, 1.5], [1.5, 4.5], [6.5, 4.5]];
const ITEM_SLOTS = [[3, 3.2], [5, 3.2], [4, 4.3], [3, 2], [5, 2]];
const EXIT_SPOT = { north: [4, 1.5], south: [4, 4.5], east: [6.5, 3], west: [1.5, 3] };
const px = (room, [cx, cy]) => [view.layout.origin[room][0] + cx * T, view.layout.origin[room][1] + cy * T];

/** Where each loose or hidden item is drawn: name -> {x, y, hidden}. */
function itemPositions(items, world) {
  const out = {}, byRoom = {};
  for (const [name, at] of Object.entries(items)) {
    if (at === "inventory") continue;
    const [room, feat] = at.split("/");
    if (!view.layout.origin[room]) continue;
    if (feat) {
      const fi = Object.keys(world.rooms[room].features).indexOf(feat);
      const [x, y] = px(room, FEATURE_SLOTS[Math.max(fi, 0) % 4]);
      out[name] = { x: x + 5, y: y - 5, hidden: true, scale: 0.6 };
    } else (byRoom[room] ||= []).push(name);
  }
  for (const [room, names] of Object.entries(byRoom)) names.sort().forEach((n, i) => {
    const [x, y] = px(room, ITEM_SLOTS[i % ITEM_SLOTS.length]);
    out[n] = { x, y, hidden: false, scale: 1 };
  });
  return out;
}

// ----------------------------------------------------------------- state ---
const view = {
  events: [], idx: -1, speed: 1, playing: true, token: 0, gate: null,
  baseWorld: null, world: null, layout: null, snap: null, searched: new Set(),
  round: 0, rounds: 0, player: { x: 0, y: 0, flip: false, bubble: "", bubbleUntil: 0 },
  dm: { mood: "idle", full: "", shown: "" }, fx: [], log: [], board: [], summary: null, judge: null, cards: [],
};
const now = () => performance.now();
async function wait(ms) {
  const end = now() + ms / view.speed;
  while (now() < end) { await new Promise((r) => setTimeout(r, 16)); }
  while (!view.playing) await new Promise((r) => (view.gate = r));
}

// --------------------------------------------------------------- drawing ---
function tile(c, r, x, y, alpha = 1) {
  ctx.globalAlpha = alpha; ctx.drawImage(IMG.tiles, c * T, r * T, T, T, x, y, T, T); ctx.globalAlpha = 1;
}
const FLOORS = [[6, 0], [7, 0], [8, 0], [9, 0], [6, 1], [7, 1], [8, 1], [9, 1], [6, 2], [7, 2], [8, 2], [9, 2]];
const floor = (x, y) => FLOORS[(x * 7 + y * 13) % FLOORS.length];
const frame = (n) => Math.floor(now() / 170) % n + 1;

function drawFloorTile(room, tx, ty) {
  const [ox, oy] = view.layout.origin[room]; const [c, r] = floor(tx, ty); tile(c, r, ox + tx * T, oy + ty * T);
}
function drawRoom(room, def) {
  const [ox, oy] = view.layout.origin[room];
  if (room === "outside") return drawOutside(ox, oy);
  for (let ty = 0; ty < RH; ty++) for (let tx = 0; tx < RW; tx++) {
    const edgeX = tx === 0 ? 0 : tx === RW - 1 ? 5 : 1 + ((tx - 1) % 4);
    if (ty === 0) tile(edgeX, 0, ox + tx * T, oy);
    else if (ty === RH - 1) tile(edgeX, 4, ox + tx * T, oy + ty * T);
    else if (tx === 0 || tx === RW - 1) tile(tx === 0 ? 0 : 5, 1 + ((ty - 1) % 3), ox + tx * T, oy + ty * T);
    else drawFloorTile(room, tx, ty);
  }
  // doorways and the short corridors that join rooms
  for (const [d, ex] of Object.entries(def.exits)) {
    const spans = d === "north" || d === "south" ? [[3, 4]] : [[2, 3]];
    for (const [a, b] of spans) for (let k = a; k <= b; k++) {
      const cells = { north: [[k, 0], [k, -1]], south: [[k, RH - 1], [k, RH]], west: [[0, k], [-1, k]], east: [[RW - 1, k], [RW, k]] }[d];
      cells.forEach(([tx, ty]) => { const [c, r] = floor(tx, ty); tile(c, r, ox + tx * T, oy + ty * T); });
    }
  }
  if (room === "hallway") [2, 5].forEach((tx) => ctx.drawImage(IMG[`torch${frame(4)}`], ox + tx * T, oy + 4));
}
function drawOutside(ox, oy) {
  const g = ctx.createLinearGradient(0, oy, 0, oy + 3 * T);
  g.addColorStop(0, "#fff3c4"); g.addColorStop(1, "#9fd4ff");
  ctx.fillStyle = g; ctx.fillRect(ox + T, oy, (RW - 2) * T, 3 * T);
  ctx.fillStyle = "#2a1a33"; ctx.fillRect(ox + T, oy, (RW - 2) * T, 2);
  ctx.fillStyle = "#3a6b3a"; ctx.fillRect(ox + T, oy + 2.4 * T, (RW - 2) * T, 0.6 * T);
  ctx.fillStyle = "#1b1021"; ctx.font = "bold 9px monospace"; ctx.textAlign = "center";
  ctx.fillText("OUTSIDE", ox + (RW * T) / 2, oy + 0.9 * T); ctx.textAlign = "left";
}
function drawFeature(room, name, i) {
  const [x, y] = px(room, FEATURE_SLOTS[i % 4]);
  const open = view.searched.has(`${room}/${name}`);
  const sprite = name === "chest" ? (open ? `chestopen${frame(4)}` : "chest1") : name === "shelf" ? `flasks${frame(4)}` : "crate1";
  ctx.fillStyle = "rgba(0,0,0,.35)"; ctx.beginPath(); ctx.ellipse(x, y + 7, 7, 2.5, 0, 0, 7); ctx.fill();
  ctx.drawImage(IMG[sprite], x - 8, y - 8);
}
function drawDoor(room, dir, ex) {
  const st = view.snap.doors[`${room}:${dir}`] || ex.door;
  const [ox, oy] = view.layout.origin[room];
  const [x, y] = { north: [3, 0], south: [3, RH - 1], east: [RW - 1, 2], west: [0, 2] }[dir];
  const [c1, c2, r] = st.open ? [6, 7, 6] : [6, 7, 3];
  tile(c1, r, ox + x * T, oy + y * T); tile(c2, r, ox + (x + 1) * T, oy + y * T);
  if (st.locked) {            // padlock
    const lx = ox + (x + 1) * T - 3, ly = oy + y * T + 5;
    ctx.fillStyle = "#f2c14e"; ctx.fillRect(lx, ly + 3, 7, 5); ctx.strokeStyle = "#f2c14e"; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.arc(lx + 3.5, ly + 3, 2.4, Math.PI, 0); ctx.stroke();
  } else if (!st.open) { ctx.fillStyle = "#5fd38d"; ctx.fillRect(ox + (x + 1) * T - 1, oy + y * T + 6, 3, 3); }
}
const ITEM_TILE = { iron: [8, 8], gold: [9, 9], flask: [7, 9], red: [9, 8], coin: [6, 8], skull: [7, 7], pouch: [5, 8] };
function drawItem(c, name, x, y, scale = 1, alpha = 1) {
  const t = now(), bob = Math.sin(t / 300 + name.length) * 1.2;
  c.save(); c.globalAlpha = alpha; c.translate(x, y + bob); c.scale(scale, scale);
  if (/goose/.test(name)) c.drawImage(IMG.goose, -8, -9);
  else if (/candle/.test(name)) c.drawImage(IMG[`candle${frame(4)}`], -8, -8);
  else {
    const k = /key/.test(name) ? (/(shiny|fake|gold|brass|decoy|rusty|silver)/.test(name) ? "gold" : "iron")
      : /(flask|potion|vial)/.test(name) ? "flask" : /(coin|gold|amulet|ring|gem|stone|jewel|crystal)/.test(name) ? "coin"
      : /(skull|bone|skeleton)/.test(name) ? "skull" : "pouch";
    const [tc, tr] = ITEM_TILE[k];
    c.drawImage(IMG.tiles, tc * T, tr * T, T, T, -8, -8, T, T);
  }
  c.restore();
}
function drawPlayer() {
  const p = view.player, f = Math.floor(now() / 380) % 2 ? 2 : 0;
  ctx.fillStyle = "rgba(0,0,0,.4)"; ctx.beginPath(); ctx.ellipse(p.x, p.y + 7, 6, 2.2, 0, 0, 7); ctx.fill();
  ctx.save(); ctx.translate(p.x, p.y - 1); if (p.flip) ctx.scale(-1, 1);
  ctx.drawImage(IMG.chars, 1 * T, f * T, T, T, -8, -8, T, T); ctx.restore();
}

let scale = 2, offX = 0, offY = 0, dpr = 1;
function fitCanvas() {
  const cv = $("#map"); dpr = window.devicePixelRatio || 1;
  const w = Math.round(cv.clientWidth * dpr), h = Math.round(cv.clientHeight * dpr);
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; ctx.imageSmoothingEnabled = false; }
}
function render() {
  fitCanvas();
  const cv = $("#map"); ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#0c0610"; ctx.fillRect(0, 0, cv.width, cv.height);
  if (view.layout && view.world) {
    const raw = Math.min((cv.width - 4 * dpr) / view.layout.width, (cv.height - 4 * dpr) / view.layout.height);
    scale = raw >= 1 ? Math.floor(raw) : Math.max(0.5, Math.floor(raw * 4) / 4);
    offX = (cv.width - view.layout.width * scale) / 2; offY = (cv.height - view.layout.height * scale) / 2;
    ctx.setTransform(scale, 0, 0, scale, offX, offY); ctx.imageSmoothingEnabled = false;
    const w = view.world;
    for (const room of Object.keys(w.rooms).concat(["outside"])) drawRoom(room, w.rooms[room] || { exits: {} });
    for (const [room, def] of Object.entries(w.rooms)) {
      Object.keys(def.features).forEach((f, i) => drawFeature(room, f, i));
      for (const [d, ex] of Object.entries(def.exits)) if (ex.door) drawDoor(room, d, ex);
    }
    const pos = itemPositions(view.snap.items, w);
    for (const [name, p] of Object.entries(pos)) {
      if (p.hidden) { ctx.fillStyle = "#b57cff"; ctx.fillRect(p.x + 4, p.y - 4, 2, 2); }   // hint pip: something is hidden here
      drawItem(ctx, name, p.x, p.y, p.scale, p.hidden ? 0.6 : 1);
    }
    drawPlayer(); drawFx();
    ctx.setTransform(1, 0, 0, 1, 0, 0); drawBubble();
  }
  drawDM(); drawInventory(); typeDM();
  requestAnimationFrame(render);
}

// --------------------------------------------------------------- effects ---
function addFx(fx) { view.fx.push({ t0: now(), ...fx }); }
function drawFx() {
  view.fx = view.fx.filter((f) => (now() - f.t0) * view.speed < f.dur);
  for (const f of view.fx) {
    const k = ((now() - f.t0) * view.speed) / f.dur;
    if (f.kind === "poof") {
      for (let i = 0; i < 8; i++) {
        const a = (i / 8) * 6.28, r = 3 + k * 12; ctx.globalAlpha = 1 - k;
        ctx.fillStyle = i % 2 ? "#b57cff" : "#f2c14e"; ctx.fillRect(f.x + Math.cos(a) * r - 1, f.y + Math.sin(a) * r - 1, 3, 3);
      } ctx.globalAlpha = 1;
    } else if (f.kind === "fly") {
      const e = k * k * (3 - 2 * k), x = f.from[0] + (f.to[0] - f.from[0]) * e, y = f.from[1] + (f.to[1] - f.from[1]) * e - Math.sin(k * 3.14) * 18;
      drawItem(ctx, f.name, x, y, 1.15);
    } else if (f.kind === "text") {
      ctx.globalAlpha = 1 - k * k; ctx.font = "bold 7px monospace"; ctx.textAlign = "center"; ctx.fillStyle = "#1b1021";
      ctx.fillText(f.text, f.x + 0.7, f.y - k * 12 + 0.7); ctx.fillStyle = f.color || "#f2c14e"; ctx.fillText(f.text, f.x, f.y - k * 12);
      ctx.textAlign = "left"; ctx.globalAlpha = 1;
    } else if (f.kind === "confetti") {
      for (let i = 0; i < 26; i++) {
        const a = i * 2.4, sp = 20 + (i % 5) * 9, x = f.x + Math.cos(a) * sp * k, y = f.y - 10 + Math.sin(a) * sp * k * 0.6 + k * k * 40;
        ctx.globalAlpha = 1 - k; ctx.fillStyle = ["#f2c14e", "#5fd38d", "#b57cff", "#e5484d", "#6cb6ff"][i % 5]; ctx.fillRect(x, y, 2, 2);
      } ctx.globalAlpha = 1;
    }
  }
}
function drawBubble() {
  const p = view.player; if (!p.bubble || now() > p.bubbleUntil) return;
  const sx = offX + p.x * scale, sy = offY + (p.y - 12) * scale;
  const u = dpr; ctx.font = `bold ${13 * u}px ui-monospace, Menlo, monospace`;
  const w = ctx.measureText(p.bubble).width + 16 * u;
  const x = Math.max(4, Math.min($("#map").width - w - 4, sx - w / 2)), y = Math.max(4, sy - 26 * u), h = 22 * u;
  ctx.fillStyle = "#f4efe6"; ctx.strokeStyle = "#1b1021"; ctx.lineWidth = 2 * u;
  ctx.beginPath(); ctx.roundRect(x, y, w, h, 5 * u); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(sx - 5 * u, y + h); ctx.lineTo(sx, y + h + 7 * u); ctx.lineTo(sx + 5 * u, y + h); ctx.fill();
  ctx.fillStyle = "#1b1021"; ctx.fillText(p.bubble, x + 8 * u, y + 15 * u);
}
function drawDM() {
  const sheet = { idle: "vamp_idle", scheme: "vamp_attack", laugh: "vamp_attack", hurt: "vamp_hurt" }[view.dm.mood];
  const img = IMG[sheet]; dmCtx.clearRect(0, 0, 112, 112); if (!img) return;
  const n = Math.max(1, Math.floor(img.width / 32)), i = Math.floor(now() / (view.dm.mood === "idle" ? 160 : 110)) % n;
  const g = dmCtx.createRadialGradient(56, 70, 5, 56, 70, 60); g.addColorStop(0, "#5a1530"); g.addColorStop(1, "#0c0610");
  dmCtx.fillStyle = g; dmCtx.fillRect(0, 0, 112, 112);
  dmCtx.drawImage(img, i * 32 + 6, 5, 20, 26, 6, 4 + Math.sin(now() / 400) * 3, 100, 130);
}
function drawInventory() {
  invCtx.clearRect(0, 0, 420, 40); if (!view.snap) return;
  const held = Object.entries(view.snap.items).filter(([, at]) => at === "inventory").map(([n]) => n);
  invCtx.font = "11px ui-monospace, Menlo, monospace"; invCtx.fillStyle = "#9a86ad";
  if (!held.length) invCtx.fillText("(empty)", 4, 24);
  held.forEach((n, i) => {
    const x = 14 + i * 130; invCtx.fillStyle = "#271834"; invCtx.fillRect(x - 14, 4, 126, 32);
    drawItem(invCtx, n, x, 20, 1.5); invCtx.fillStyle = "#eadff5"; invCtx.fillText(n, x + 14, 24);
  });
}

// ------------------------------------------------------- DM panel (DOM) ---
function typeDM() {
  const d = view.dm;
  if (d.shown.length < d.full.length) { d.shown = d.full.slice(0, d.shown.length + Math.max(1, Math.round(view.speed * 1.5))); $("#bubble").textContent = d.shown; }
}
function say(text, instant) { view.dm.full = text; view.dm.shown = instant ? text : ""; if (instant) $("#bubble").textContent = text; }
function cardHTML(a) {
  const args = Object.entries(a).filter(([k]) => !["tool", "op", "reason"].includes(k)).map(([k, v]) => `${k}: ${v}`).join(" · ");
  return `<div class="card ${a.tool}"><b>${a.tool.toUpperCase()}</b>${a.op}<div class="args">${args}</div><div class="why">${a.reason || ""}</div></div>`;
}
function showJudge(par) {
  const j = $("#judge"); j.classList.remove("hidden", "bad"); j.textContent = `JUDGE ✓ par ${par}`;
}
const QUIPS = {
  win: ["Hmph. Beginner's luck.", "It escaped?! I'll be harder next time.", "Curses! Where did I go wrong?"],
  lose: ["Mwahaha! Still trapped!", "Delicious. Keep searching, little one.", "Ran out of moves. Pathetic."],
};

// ---------------------------------------------------------------- events ---
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
function setPlayerAt(room, spot = [4, 3]) { const [x, y] = px(room, spot); Object.assign(view.player, { x, y }); }
async function walk(points) {
  for (const [x, y] of points) {
    const p = view.player;
    while (dist([p.x, p.y], [x, y]) > 1) {
      const d = dist([p.x, p.y], [x, y]), step = Math.min(d, 1.1 * view.speed * 1.6);
      p.flip = x < p.x - 0.5 ? true : x > p.x + 0.5 ? false : p.flip;
      p.x += ((x - p.x) / d) * step; p.y += ((y - p.y) / d) * step;
      await new Promise((r) => setTimeout(r, 16));
      while (!view.playing) await new Promise((r) => (view.gate = r));
    }
  }
}
function route(from, to, world) {
  if (from === to) return [px(to, [4, 3])];
  const dir = Object.entries(world.rooms[from].exits).find(([, ex]) => ex.to === to)?.[0];
  if (!dir) return [px(to, [4, 3])];
  const pts = [px(from, EXIT_SPOT[dir])];
  if (world.rooms[to]) pts.push(px(to, EXIT_SPOT[OPP[dir]]), px(to, [4, 3]));
  return pts;
}
const FAIL = /^(You can't|There is no|You don't|You see no|The .* doesn't|Use what|The door is (locked|closed)|The lock has|Your head|.* honks|Say something|The game is over)/;

async function handle(e, instant) {
  const v = view;
  switch (e.type) {
    case "run_start": v.baseWorld = e.world; v.rounds = e.rounds; v.board = []; v.summary = null; break;
    case "round_start":
      v.round = e.round; v.log = []; v.cards = []; v.searched = new Set(); v.judge = null;
      $("#roundpill").textContent = `Round ${e.round}/${v.rounds}`; $("#log").innerHTML = ""; $("#cards").innerHTML = "";
      $("#judge").classList.add("hidden"); v.dm.mood = "idle"; renderBoard(); break;
    case "dm_thinking":
      v.dm.mood = "scheme"; say("Let me study how it fumbled last time…", instant); if (!instant) await wait(1100); break;
    case "round_setup": {
      v.world = e.world; v.layout = computeLayout(e.world);
      const start = { room: e.world.start, items: Object.fromEntries(Object.entries(e.world.items).map(([n, i]) => [n, i.at])),
        doors: Object.fromEntries(Object.entries(e.world.rooms).flatMap(([r, d]) => Object.entries(d.exits).filter(([, x]) => x.door).map(([dir, x]) => [`${r}:${dir}`, x.door]))) };
      v.snap = start; setPlayerAt(e.world.start);
      say(e.analysis, instant);
      for (const a of e.actions) { v.cards.push(a); $("#cards").insertAdjacentHTML("beforeend", cardHTML(a)); }
      showJudge(e.par); v.dm.mood = e.actions.length ? "laugh" : "idle";
      if (!instant) {
        const text = Math.min(4200, 700 + e.analysis.length * 22);
        await wait(text);
        riggingFx(e);
        await wait(1600); v.dm.mood = "idle";
      }
      break;
    }
    case "turn": {
      const prev = v.snap, s = e.state, p = v.player;
      v.log.push(e); logLine(e);
      if (!instant) { p.bubble = e.command; p.bubbleUntil = now() + 1400 / v.speed; await wait(420); }
      if (s.room !== prev.room) { if (instant) setPlayerAt(s.room); else await walk(route(prev.room, s.room, v.world)); }
      else if (!instant && /^(go|north|south|east|west)/.test(e.command) && FAIL.test(e.result)) addFx({ kind: "text", x: p.x, y: p.y - 14, text: "bump!", dur: 700, color: "#e5484d" });
      for (const [name, at] of Object.entries(s.items)) {
        if (prev.items[name] !== at && !instant) {
          const posNow = itemPositions(s.items, v.world)[name] || itemPositions(prev.items, v.world)[name];
          if (at === "inventory") { const [x, y] = itemPositions(prev.items, v.world)[name] ? [itemPositions(prev.items, v.world)[name].x, itemPositions(prev.items, v.world)[name].y] : [p.x, p.y]; addFx({ kind: "fly", name, from: [x, y], to: [p.x, p.y - 14], dur: 450 }); }
          else if (posNow) addFx({ kind: "poof", x: posNow.x, y: posNow.y, dur: 600 });
        }
      }
      const m = e.command.match(/^(?:search|examine|inspect|look under|look at)\s+(\w+)/);
      if (m && v.world.rooms[prev.room].features[m[1]] !== undefined) v.searched.add(`${prev.room}/${m[1]}`);
      for (const k of Object.keys(s.doors)) if (!instant && prev.doors[k] && (prev.doors[k].locked !== s.doors[k].locked)) addFx({ kind: "poof", x: p.x, y: p.y - 20, dur: 700 });
      if (!instant && /honks/.test(e.result)) addFx({ kind: "text", x: p.x, y: p.y - 14, text: "HONK!", dur: 900, color: "#ffd166" });
      if (!instant && /head swims/.test(e.result)) addFx({ kind: "text", x: p.x, y: p.y - 14, text: "dizzy…", dur: 900, color: "#b57cff" });
      v.snap = s;
      if (!instant) await wait(260);
      break;
    }
    case "round_end": {
      const wasted = e.moves - e.par;
      v.board.push({ round: e.round, won: e.won, moves: e.moves, par: e.par, wasted }); renderBoard();
      if (e.won) {
        v.dm.mood = "hurt"; say(QUIPS.win[e.round % 3], instant);
        if (!instant) { await walk([px("hallway", EXIT_SPOT.north), px("outside", [4, 1.5])]); addFx({ kind: "confetti", x: v.player.x, y: v.player.y, dur: 1800 }); await wait(2000); }
      } else { v.dm.mood = "laugh"; say(QUIPS.lose[e.round % 3], instant); if (!instant) await wait(2200); }
      break;
    }
    case "run_end": v.summary = e.summary; renderBoard(); v.dm.mood = "laugh"; break;
    case "error": v.dm.mood = "idle"; say("⚠ The run stopped: " + e.message, instant); break;
  }
}
function riggingFx(e) {
  const base = view.baseWorld.items, now_ = e.world.items, pos = itemPositions(Object.fromEntries(Object.entries(now_).map(([n, i]) => [n, i.at])), e.world);
  const oldPos = itemPositions(Object.fromEntries(Object.entries(base).map(([n, i]) => [n, i.at])), e.world);
  for (const [name, i] of Object.entries(now_)) {
    if (!pos[name]) continue;
    if (!base[name]) addFx({ kind: "poof", x: pos[name].x, y: pos[name].y, dur: 1100 });
    else if (base[name].at !== i.at && oldPos[name]) addFx({ kind: "fly", name, from: [oldPos[name].x, oldPos[name].y], to: [pos[name].x, pos[name].y], dur: 1300 });
  }
  for (const a of e.actions) {
    if (a.op === "extend_path") Object.keys(e.world.rooms).filter((r) => r.includes("passage")).forEach((r) => { const [x, y] = px(r, [4, 3]); addFx({ kind: "poof", x, y, dur: 1100 }); });
    if (a.op === "lie") { const [x, y] = px(a.room, [4, 3]); addFx({ kind: "text", x, y, text: "(lies)", dur: 1500, color: "#b57cff" }); }
    if (a.op === "pest" && pos[a.item]) addFx({ kind: "text", x: pos[a.item].x, y: pos[a.item].y - 8, text: "pest!", dur: 1500, color: "#ffd166" });
    if (a.op === "second_key" && pos[a.item]) addFx({ kind: "text", x: pos[a.item].x, y: pos[a.item].y - 8, text: "2nd key", dur: 1500, color: "#b57cff" });
  }
}
function logLine(e) {
  const first = e.result.split("\n")[0], bad = FAIL.test(first), good = /click|swings open|escaped|You take|find:/.test(first);
  const row = document.createElement("div");
  row.innerHTML = `<span class="n">${e.move}.</span><span class="cmd">${esc(e.command)}</span> <span class="res ${bad ? "bad" : good ? "good" : ""}">→ ${esc(first)}</span>`;
  $("#log").appendChild(row); $("#log").scrollTop = 1e9;
}
const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
function renderBoard() {
  const max = Math.max(10, ...view.board.map((b) => b.wasted));
  $("#bars").innerHTML = view.board.map((b) => `<div class="bar ${b.won ? "" : "loss"} ${b.round === 1 ? "base" : ""}" title="Round ${b.round}: ${b.won ? "WIN" : "LOSS"}, ${b.moves} moves (par ${b.par})"><i style="height:${Math.max(3, (b.wasted / max) * 82)}px"></i><em>${b.wasted}</em><em>R${b.round}</em></div>`).join("");
  const s = view.summary;
  $("#summary").innerHTML = s ? `Rigged rounds won <b>${s.rigged_wins}/${s.rigged_rounds}</b>. Avg wasted <b>${s.avg_wasted_rigged?.toFixed(1)}</b> vs <b>${s.baseline_wasted}</b> baseline.` : "Bars show wasted moves. Round 1 (faded) is the unrigged baseline.";
}

// -------------------------------------------------------------- playback ---
function resetState() {
  Object.assign(view, { baseWorld: null, world: null, layout: null, snap: null, searched: new Set(), round: 0, fx: [], log: [], board: [], summary: null, cards: [] });
  Object.assign(view.dm, { mood: "idle", full: "", shown: "" }); $("#bubble").textContent = ""; $("#log").innerHTML = ""; $("#cards").innerHTML = "";
  $("#judge").classList.add("hidden"); renderBoard();
}
async function playFrom(i) {
  const tok = ++view.token;
  for (let k = i; tok === view.token; k++) {
    while (k >= view.events.length && view.live && tok === view.token) await new Promise((r) => setTimeout(r, 80));
    if (k >= view.events.length) break;
    await handle(view.events[k], false);
    if (tok !== view.token) return;
    view.idx = k; $("#scrub").value = k;
  }
}
async function jumpTo(i) {
  view.token++; resetState();
  for (let k = 0; k <= i; k++) await handle(view.events[k], true);
  view.idx = i; $("#scrub").value = i; view.player.bubble = ""; view.fx = [];
  if (view.world) setPlayerAt(view.snap.room);
  playFrom(i + 1);
}
const roundStarts = () => view.events.map((e, i) => (e.type === "round_start" ? i : -1)).filter((i) => i >= 0);
function skipRound(dir) {
  const starts = roundStarts(), cur = starts.filter((i) => i <= view.idx).pop() ?? 0;
  const target = dir > 0 ? starts.find((i) => i > view.idx) : (view.idx - cur > 3 ? cur : starts.filter((i) => i < cur).pop());
  if (target !== undefined) jumpTo(target);
}

function startLive() {
  const rounds = +$("#liverounds").value, btn = $("#golive");
  btn.disabled = true; btn.textContent = "● starting…";
  fetch("/api/start", { method: "POST", headers: { "X-EDM": "1", "Content-Type": "application/json" }, body: JSON.stringify({ rounds }) })
    .then((r) => r.json()).then((r) => {
      if (r.error) { say("Could not start: " + r.error, true); btn.disabled = false; btn.textContent = "● Live run"; return; }
      view.token++; resetState(); view.events = []; view.idx = -1; view.live = true; view.playing = true; $("#play").textContent = "⏸";
      $("#roundpill").innerHTML = `<span class="livetag">● LIVE</span>`; $("#scrub").max = 0;
      const es = new EventSource("/api/stream");
      es.onmessage = (m) => { view.events.push(JSON.parse(m.data)); $("#scrub").max = view.events.length - 1; };
      es.addEventListener("done", () => { es.close(); view.live = false; btn.disabled = false; btn.textContent = "● Live run"; refreshReplays(); });
      playFrom(0);
    });
}
async function refreshReplays() {
  const list = await (await fetch("/api/replays")).json(), sel = $("#replays");
  sel.innerHTML = list.map((r) => `<option value="${r.path}">${r.name}</option>`).join("");
}
async function loadReplay(path, at) {
  view.live = false;
  const text = await (await fetch("/replay/" + path)).text();
  view.events = text.trim().split("\n").map((l) => JSON.parse(l));
  $("#scrub").max = view.events.length - 1; resetState(); view.idx = -1; view.token++;
  if (at !== undefined) { view.playing = false; $("#play").textContent = "▶"; await jumpTo(at); } else playFrom(0);
}
async function init() {
  await loadAssets();
  const list = await (await fetch("/api/replays")).json();
  const sel = $("#replays");
  sel.innerHTML = list.length ? list.map((r) => `<option value="${r.path}">${r.name}</option>`).join("") : "<option>No replays yet</option>";
  sel.onchange = () => loadReplay(sel.value);
  const wanted = new URLSearchParams(location.search).get("replay");
  if (wanted) sel.value = [...sel.options].find((o) => o.text.includes(wanted))?.value ?? sel.value;
  requestAnimationFrame(render);
  $("#splash").classList.add("gone");
  const q = new URLSearchParams(location.search);
  if (q.has("speed")) { view.speed = +q.get("speed"); [...$("#speeds").children].forEach((b) => b.classList.toggle("on", +b.dataset.s === view.speed)); }
  if (list.length) loadReplay(sel.value, q.has("at") ? +q.get("at") : undefined);  // ?at=N opens paused at event N (for screenshots)
  $("#golive").onclick = startLive;
  $("#play").onclick = () => { view.playing = !view.playing; $("#play").textContent = view.playing ? "⏸" : "▶"; if (view.playing && view.gate) view.gate(); };
  $("#prev").onclick = () => skipRound(-1); $("#next").onclick = () => skipRound(1);
  $("#scrub").oninput = (ev) => jumpTo(+ev.target.value);
  $("#speeds").onclick = (ev) => { const s = ev.target.dataset.s; if (!s) return; view.speed = +s; [...$("#speeds").children].forEach((b) => b.classList.toggle("on", b === ev.target)); };
  document.addEventListener("keydown", (ev) => { if (ev.key === " ") { ev.preventDefault(); $("#play").click(); } });
}
init();
