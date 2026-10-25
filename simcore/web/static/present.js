// Presentation screen: a second window for the projector or a second monitor, while this
// window keeps the controls. Three views, picked in the presenter bar under the canvas:
//  - Ikuti editor: the canvas plus whatever is open here — the module panel on the right, the
//    Spreadsheet / Summary / Report pane at the bottom, and any open dialog — with the
//    values typed so far and the field being edited outlined;
//  - Animasi: the model and its animation over the whole screen;
//  - Hasil: the Summary, following the scrolling of the Summary pane here.
// The canvas follows the editor's zoom and panning (🔍 Ikuti zoom), or shows the whole model.
// The live plots float over the canvas while a run is animated, and the mouse over the canvas
// shows as a pointer dot. 🔦 Sorot dims all but the modules clicked here, ✏ Pena draws on
// the model (on both screens; strokes fade after a few seconds). The window is a same-origin popup filled and updated from here, so
// it needs no server and no messages.
(function () {
  let win = null, mode = "editor", zoom = 1.25, pointer = true, follow = true, spotOn = false, pen = false, ptr = null,
      spot = new Set(), stroke = null, last = {}, lastFrame = 0, lastPanels = 0, timer = 0;

  const bar = document.createElement("div");
  bar.id = "pvbar"; bar.hidden = true; bar.setAttribute("role", "toolbar"); bar.setAttribute("aria-label", "Layar presentasi");
  bar.innerHTML = `<b>🖥 Presentasi</b>
    <span class="pvseg" role="group" aria-label="Yang tampil di layar presentasi">
      <button data-mode="editor" aria-pressed="true" title="Ikuti editor: kanvas plus panel modul, Spreadsheet/Summary dan dialog yang sedang terbuka di sini">Editor</button>
      <button data-mode="anim" aria-pressed="false" title="Hanya model dan animasi, satu layar penuh">Animasi</button>
      <button data-mode="sum" aria-pressed="false" title="Tabel Summary hasil run; scroll di panel Summary, layar presentasi ikut">Hasil</button>
    </span>
    <button id="pvzout" title="Perkecil tulisan panel di layar presentasi" aria-label="Perkecil tulisan">A−</button><button id="pvzin" title="Perbesar tulisan panel di layar presentasi" aria-label="Perbesar tulisan">A+</button>
    <button id="pvfollow" aria-pressed="true" aria-label="Ikuti zoom" title="Ikuti zoom: layar presentasi mengikuti zoom dan geser kanvas di sini. Matikan untuk selalu menampilkan seluruh model.">🔍</button>
    <button id="pvptr" aria-pressed="true" aria-label="Pointer" title="Pointer: posisi mouse di kanvas tampil sebagai titik merah di layar presentasi">●</button>
    <button id="pvspot" aria-pressed="false" title="Sorot: klik module di kanvas untuk menyorotnya di layar presentasi (Shift+klik menambah, klik area kosong menghapus)">🔦 Sorot</button>
    <button id="pvpen" aria-pressed="false" title="Pena: gambar di atas model dengan mouse; coretan hilang sendiri setelah beberapa detik (Esc mematikan pena)">✏ Pena</button>
    <button id="pvink0" title="Hapus semua coretan" aria-label="Hapus coretan">🧽</button>
    <button id="pvclose" title="Tutup layar presentasi" aria-label="Tutup layar presentasi">✕</button>`;
  $("stage").appendChild(bar);
  const st = document.createElement("style");
  st.textContent = `#pvbar { position: absolute; left: 50%; bottom: 10px; transform: translateX(-50%); display: flex; gap: 6px; align-items: center; z-index: 4;
    background: var(--panel); border: 1px solid var(--accent); border-radius: 8px; padding: 4px 8px; box-shadow: 0 4px 14px rgba(0,0,0,.15); white-space: nowrap; }
  #pvbar[hidden] { display: none; }
  #pvbar button { padding: 2px 8px; }
  #pvbar .pvseg { display: inline-flex; }
  #pvbar .pvseg button { border-radius: 0; margin-left: -1px; }
  #pvbar .pvseg button:first-child { border-radius: 6px 0 0 6px; margin-left: 0; }
  #pvbar .pvseg button:last-child { border-radius: 0 6px 6px 0; }
  #stage.pvpen #canvas { cursor: crosshair; }
  #stage.pvon #zoombar { bottom: 56px; }
  #pvink path, #pvinkm path { fill: none; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
  #pvbar button[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }`;
  document.head.appendChild(st);

  for (const b of bar.querySelectorAll("[data-mode]")) b.onclick = () => setMode(b.dataset.mode);
  $("pvzin").onclick = () => { zoom = Math.min(3, zoom + 0.15); };
  $("pvzout").onclick = () => { zoom = Math.max(0.7, zoom - 0.15); };
  $("pvfollow").onclick = () => { follow = !follow; $("pvfollow").setAttribute("aria-pressed", String(follow)); last.vb = last.vbFor = null; };
  $("pvptr").onclick = () => { pointer = !pointer; $("pvptr").setAttribute("aria-pressed", String(pointer)); };
  const press = (id, v) => $(id).setAttribute("aria-pressed", String(v));
  $("pvspot").onclick = () => { spotOn = !spotOn; press("pvspot", spotOn); spot = new Set(spotOn ? sel : []); };
  $("pvpen").onclick = () => setPen(!pen);
  $("pvink0").onclick = () => { ink.innerHTML = ""; };
  function setPen(v) { pen = v; press("pvpen", pen); $("stage").classList.toggle("pvpen", pen); if (!pen) stroke = null; }
  $("pvclose").onclick = () => { if (win && !win.closed) win.close(); closed(); };

  function setMode(m) {
    mode = m;
    for (const b of bar.querySelectorAll("[data-mode]")) b.setAttribute("aria-pressed", String(b.dataset.mode === m));
    if (m === "sum" && $("p-summary")) openPane("summary");
    last = {opened: last.opened};
  }

  const PAGE = `<!doctype html><html lang="id"><head><meta charset="utf-8"><title>Atlverse Simulation — Presentasi</title>
<link rel="icon" href="icon.svg" type="image/svg+xml"><style id="pvcopied"></style><style>
:root { --pvz: 1.25; }
body { height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
#pvhead { display: flex; align-items: center; gap: 18px; padding: 10px 20px; background: var(--panel); border-bottom: 1px solid var(--line); }
#pvhead img { height: 34px; }
#pvname { font-size: 24px; font-weight: 600; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#pvclock { font: 600 26px/1 ui-monospace, monospace; }
#pvstate { color: var(--muted); font-size: 16px; }
#pvfs { font-size: 15px; padding: 6px 12px; }
#pvtrack { height: 5px; background: var(--line); }
#pvprog { height: 100%; width: 0; background: var(--accent); }
#pvmain { flex: 1; display: flex; min-height: 0; }
#pvleft { flex: 1; display: flex; flex-direction: column; min-width: 0; }
#pvstage { flex: 1; position: relative; min-height: 0; }
#pvstage svg { width: 100%; height: 100%; display: block; }
#pvhint { position: absolute; left: 50%; top: 18px; transform: translateX(-50%); background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 10px 16px; font-size: 16px; color: var(--muted); box-shadow: 0 4px 14px rgba(0,0,0,.12); text-align: center; }
#pvplots { position: absolute; top: 12px; right: 12px; width: min(30vw, 480px); max-height: calc(100% - 24px); overflow: auto; z-index: 2;
  background: color-mix(in srgb, var(--panel) 94%, transparent); border: 1px solid var(--line); border-radius: 8px; padding: 6px 12px; box-shadow: 0 4px 14px rgba(0,0,0,.12); }
#pvplots .plg svg { width: 100%; height: auto; display: block; }
#pvplots .plleg { display: flex; flex-wrap: wrap; gap: 2px 14px; font-size: 15px; }
#pvplots .plleg i { display: inline-block; width: 14px; height: 4px; vertical-align: middle; margin-right: 5px; border-radius: 2px; }
#pvplots .plg .hint { font-size: 15px; margin-top: 8px; }
#pvbottom { flex: none; }
#pvbottom #bottom.open { height: 42vh; }
#pvbottom #tabs button { pointer-events: none; }
#pvbottom #panes, #pvside #side, #pvdlg .dlgbox { zoom: var(--pvz); }
#pvside { flex: none; display: flex; }
#pvside #side { width: calc(min(34vw, 560px) / var(--pvz)); }
#pvdlg .dlgbox { max-height: calc((100vh - 40px) / var(--pvz)); }
#pvsum { overflow: auto; padding: 14px 28px; flex: 1; }
#pvsum > div { zoom: var(--pvz); }
[hidden] { display: none !important; }
.pvmirror input, .pvmirror select, .pvmirror textarea, .pvmirror button { pointer-events: none; }
.pvfocus { outline: 3px solid #ffc800 !important; outline-offset: 1px; }
.port { display: none; }
body.pvanim .node.selected rect.body { stroke: var(--node-line); stroke-width: 1.5; }
#pvdot { fill: #e02424; fill-opacity: .75; stroke: #fff; stroke-width: 2; pointer-events: none; }
</style></head><body>
<div id="pvhead"><img src="logo.svg" alt=""><span id="pvname"></span><span id="pvstate"></span><span id="pvclock"></span>
<button id="pvfs" title="Layar penuh (Esc untuk keluar)">⛶ Layar penuh</button></div>
<div id="pvtrack"><div id="pvprog"></div></div>
<div id="pvmain">
  <div id="pvleft">
    <div id="pvstage"><svg id="canvas" preserveAspectRatio="xMidYMid meet"><defs id="pvdefs"></defs>
      <g id="world"><g id="links"></g><g id="nodes"></g><g id="ents"></g><path id="pvspotmask" fill="#000" fill-opacity=".55" fill-rule="evenodd" d=""/><g id="pvink"></g><circle id="pvdot" r="9" visibility="hidden"/></g></svg>
      <div id="pvplots" hidden></div>
      <div id="pvhint">Seret jendela ini ke layar proyektor, lalu klik <b>⛶ Layar penuh</b>.<br>Jalankan dan kendalikan simulasi dari jendela editor.</div></div>
    <div id="pvbottom" class="pvmirror"></div>
  </div>
  <div id="pvside" class="pvmirror"></div>
  <div id="pvsum" hidden></div>
</div>
<div id="pvdlg" class="pvmirror"></div>
</body></html>`;

  async function open() {
    if (win && !win.closed) { win.focus(); return; }
    win = window.open("", "atl-present", "popup,width=1280,height=760");
    if (!win) { toast("Browser memblokir jendela baru — izinkan pop-up untuk situs ini, lalu coba lagi"); return; }
    if (!win.document.getElementById("pvstage")) { win.document.open(); win.document.write(PAGE); win.document.close(); }
    const d = win.document;
    d.getElementById("pvfs").onclick = () => { if (d.fullscreenElement) d.exitFullscreen(); else d.documentElement.requestFullscreen().catch(() => {}); };
    d.addEventListener("fullscreenchange", () => { d.getElementById("pvfs").textContent = d.fullscreenElement ? "Keluar layar penuh" : "⛶ Layar penuh"; });
    win.addEventListener("pagehide", () => setTimeout(() => { if (!win || win.closed) closed(); }, 50));
    last = {opened: performance.now()}; bar.hidden = false; $("stage").classList.add("pvon"); setMode(mode);
    toSecondScreen();
    clearInterval(timer); timer = setInterval(() => frame(true), 250);   // keeps going when this tab is in the background
    requestAnimationFrame(loop);
  }
  async function toSecondScreen() {   // Chrome's Window Management API: put the window on the other screen
    try {
      if (!window.getScreenDetails) return;
      const s = await window.getScreenDetails();
      const other = s.screens.find(x => x !== s.currentScreen);
      if (other && win && !win.closed) {
        win.moveTo(other.availLeft, other.availTop); win.resizeTo(other.availWidth, other.availHeight);
        win.document.getElementById("pvhint").innerHTML = "Klik <b>⛶ Layar penuh</b> di atas.<br>Jalankan dan kendalikan simulasi dari jendela editor.";
      }
    } catch (e) {}
  }
  function closed() { win = null; bar.hidden = true; $("stage").classList.remove("pvon"); clearInterval(timer); setPen(false); }

  function loop(now) {
    if (!win) return;
    if (win.closed) return closed();
    if (now - lastFrame > 30) frame(false);
    requestAnimationFrame(loop);
  }
  function put(d, id, html) { if (last[id] !== html) { last[id] = html; d.getElementById(id).innerHTML = html; } }
  // An element's markup with the current values of its fields (innerHTML alone has the
  // values the page was built with) and the field being edited marked.
  function snap(src) {
    const c = src.cloneNode(true);
    const a = src.querySelectorAll("input, select, textarea"), b = c.querySelectorAll("input, select, textarea");
    a.forEach((x, i) => {
      const y = b[i]; if (!y) return;
      if (x.type === "checkbox" || x.type === "radio") x.checked ? y.setAttribute("checked", "") : y.removeAttribute("checked");
      else if (x.tagName === "SELECT") [...y.options].forEach((o, j) => x.options[j] && x.options[j].selected ? o.setAttribute("selected", "") : o.removeAttribute("selected"));
      else if (x.tagName === "TEXTAREA") y.textContent = x.value;
      else if (x.type !== "file") y.setAttribute("value", x.value);
      if (x === document.activeElement) y.classList.add("pvfocus");
      y.removeAttribute("autofocus");
    });
    return c.outerHTML;
  }
  function scrollLike(src, dst) {   // same scroll position, as a fraction
    if (!src || !dst) return;
    const f = src.scrollTop / Math.max(1, src.scrollHeight - src.clientHeight);
    dst.scrollTop = f * (dst.scrollHeight - dst.clientHeight);
  }
  const visible = el => el && !el.hidden && el.offsetParent !== null;

  function frame(fromTimer) {
    if (!win || win.closed) return closed();
    const now = performance.now();
    if (fromTimer && now - lastFrame < 200) return;
    lastFrame = now;
    const d = win.document;
    // look: the editor's styles and theme
    const css = [...document.querySelectorAll("style")].map(s => s.textContent).join("\n");
    if (last.css !== css) { last.css = css; d.getElementById("pvcopied").textContent = css; }
    const theme = document.documentElement.getAttribute("data-theme");
    if (d.documentElement.getAttribute("data-theme") !== theme) theme ? d.documentElement.setAttribute("data-theme", theme) : d.documentElement.removeAttribute("data-theme");
    if (last.zoom !== zoom) { last.zoom = zoom; d.documentElement.style.setProperty("--pvz", zoom); }
    d.body.classList.toggle("pvanim", mode !== "editor");
    // header: model name, clock, progress
    const name = model.name || "Model";
    if (last.name !== name) { last.name = name; d.getElementById("pvname").textContent = name; d.title = name + " — Presentasi"; }
    const running = !!anim, done = running && anim.done;
    const clock = running ? `t = ${fmt(anim.t)} ${model.time_units}` : "";
    if (last.clock !== clock) { last.clock = clock; d.getElementById("pvclock").textContent = clock; }
    const state = typeof runJob !== "undefined" && runJob ? "menghitung…" : !running ? "" : done ? "selesai" : anim.playing ? "▶ berjalan" : "⏸ jeda";
    if (last.state !== state) { last.state = state; d.getElementById("pvstate").textContent = state; }
    d.getElementById("pvprog").style.width = (running && anim.end > 0 ? Math.min(100, 100 * anim.t / anim.end) : 0) + "%";
    if (running || mode === "sum" || now - (last.opened || 0) > 15000) d.getElementById("pvhint").hidden = true;

    const sum = mode === "sum", ed = mode === "editor";
    d.getElementById("pvleft").hidden = sum;
    d.getElementById("pvsum").hidden = !sum;
    const panels = now - lastPanels > 140;   // the panels are copied a few times a second, the canvas every frame
    if (panels) lastPanels = now;
    if (sum) {
      if (panels) { const p = $("p-summary"); put(d, "pvsum", `<div>${p ? p.innerHTML : ""}</div>`); }
      scrollLike($("panes"), d.getElementById("pvsum"));
      for (const id of ["pvside", "pvbottom", "pvdlg"]) put(d, id, "");
      return;
    }
    // canvas: same elements as the editor's
    put(d, "pvdefs", document.querySelector("#canvas defs").innerHTML);
    put(d, "links", $("links").innerHTML);
    put(d, "nodes", $("nodes").innerHTML);
    put(d, "ents", $("ents").innerHTML);
    const svg = d.getElementById("canvas");
    if (follow) {   // the part of the model the editor shows, at the editor's zoom
      const r = $("canvas").getBoundingClientRect();
      if (r.width && r.height) {
        const vb = `${-view.x / view.k} ${-view.y / view.k} ${r.width / view.k} ${r.height / view.k}`;
        if (last.vb !== vb) { last.vb = vb; last.vbFor = null; svg.setAttribute("viewBox", vb); }
      }
    } else if (last.nodes !== last.vbFor) {   // the whole model
      last.vbFor = last.nodes; last.vb = null;
      try {
        const boxes = [$("nodes").getBBox(), $("links").getBBox()].filter(r => r.width || r.height);
        if (boxes.length) {
          const x0 = Math.min(...boxes.map(r => r.x)), y0 = Math.min(...boxes.map(r => r.y));
          const x1 = Math.max(...boxes.map(r => r.x + r.width)), y1 = Math.max(...boxes.map(r => r.y + r.height)) + 40;   // room for the entity rows
          const pad = 30;
          svg.setAttribute("viewBox", `${x0 - pad} ${y0 - pad} ${x1 - x0 + 2 * pad} ${y1 - y0 + 2 * pad}`);
        }
      } catch (e) {}
    }
    let mask = "";
    if (spotOn && spot.size) {   // a dark veil with a hole around each spotlit module and its entity row
      mask = "M-100000,-100000H100000V100000H-100000Z";
      for (const n of G().nodes) if (spot.has(n.id)) {
        const x = n.x - 14, y = n.y - 14, w = W + 28, h = H + 48, r = 12;
        mask += `M${x + r},${y}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 -${r},${r}h-${w - 2 * r}a${r},${r} 0 0 1 -${r},-${r}v-${h - 2 * r}a${r},${r} 0 0 1 ${r},-${r}z`;
      }
    }
    if (last.mask !== mask) { last.mask = mask; d.getElementById("pvspotmask").setAttribute("d", mask); }
    fadeInk();
    put(d, "pvink", ink.innerHTML);
    const dot = d.getElementById("pvdot");
    if (pointer && ptr) {
      const vb = svg.viewBox.baseVal, k = vb && vb.width ? Math.min(svg.clientWidth / vb.width, svg.clientHeight / vb.height) : 1;
      dot.setAttribute("r", 11 / (k || 1));   // the same size on screen at any zoom
      dot.setAttribute("cx", ptr.x); dot.setAttribute("cy", ptr.y); dot.setAttribute("visibility", "visible");
    }
    else dot.setAttribute("visibility", "hidden");
    // live plots over the canvas, when the 📈 Plot panel is open
    const pl = $("plbody"), plots = $("plots");
    const showPlots = !!(running && pl && plots && !plots.hidden && pl.innerHTML);
    d.getElementById("pvplots").hidden = !showPlots;
    if (showPlots) put(d, "pvplots", pl.innerHTML);
    if (!panels) return;
    // the editor's panels: module panel, bottom pane, open dialogs
    put(d, "pvside", ed && visible($("side")) && $("side").children.length ? snap($("side")) : "");
    put(d, "pvbottom", ed && $("bottom").classList.contains("open") ? snap($("bottom")) : "");
    const dlgs = ed ? [...document.querySelectorAll(".dlg")].filter(x => !x.hidden && getComputedStyle(x).display !== "none") : [];
    put(d, "pvdlg", dlgs.map(snap).join(""));
    scrollLike($("side"), d.querySelector("#pvside #side"));
    scrollLike($("panes"), d.querySelector("#pvbottom #panes"));
    const boxes = d.querySelectorAll("#pvdlg .dlgbox");
    dlgs.forEach((x, i) => scrollLike(x.querySelector(".dlgbox"), boxes[i]));
  }

  // ---------- pen: strokes in model coordinates, drawn here and copied to the big screen ----------
  const ink = document.createElementNS("http://www.w3.org/2000/svg", "g");
  ink.id = "pvinkm"; $("world").appendChild(ink);
  const INK = "#e02424", KEEP = 6000, FADE = 1500;
  function fadeInk() {
    const now = performance.now();
    for (const p of [...ink.children]) {
      if (p === (stroke && stroke.el)) continue;
      const age = now - +p.dataset.t;
      if (age > KEEP + FADE) p.remove();
      else if (age > KEEP) p.setAttribute("opacity", (1 - (age - KEEP) / FADE).toFixed(2));
    }
  }
  setInterval(() => { if (!win && ink.children.length) fadeInk(); }, 500);
  const fmt1 = v => Math.round(v * 10) / 10;
  $("canvas").addEventListener("pointerdown", ev => {
    if (pen && win && ev.button === 0) {
      ev.stopPropagation(); ev.preventDefault();
      const p = toWorld(ev), el = document.createElementNS("http://www.w3.org/2000/svg", "path");
      el.setAttribute("stroke", INK); el.dataset.t = performance.now();
      stroke = {el, d: `M${fmt1(p.x)},${fmt1(p.y)}`}; el.setAttribute("d", stroke.d + "l0.01,0"); ink.appendChild(el);
      $("canvas").setPointerCapture(ev.pointerId);
      return;
    }
    if (spotOn && win && ev.button === 0) {   // pick the spotlit modules; the editor still gets the click
      const p = toWorld(ev), n = G().nodes.find(n => p.x >= n.x && p.x <= n.x + W && p.y >= n.y && p.y <= n.y + H);
      if (!n) spot = new Set();
      else if (ev.shiftKey) spot.has(n.id) ? spot.delete(n.id) : spot.add(n.id);
      else spot = new Set([n.id]);
    }
  }, true);
  $("canvas").addEventListener("pointermove", ev => {
    if (!stroke) return;
    ev.stopPropagation();
    const p = toWorld(ev);
    stroke.d += `L${fmt1(p.x)},${fmt1(p.y)}`; stroke.el.setAttribute("d", stroke.d); stroke.el.dataset.t = performance.now();
  }, true);
  const endStroke = () => { if (stroke) { stroke.el.dataset.t = performance.now(); stroke = null; } };
  $("canvas").addEventListener("pointerup", endStroke, true);
  $("canvas").addEventListener("pointercancel", endStroke, true);
  document.addEventListener("keydown", ev => { if (ev.key === "Escape" && pen) setPen(false); });

  $("canvas").addEventListener("pointermove", ev => { if (win) ptr = toWorld(ev); });
  $("canvas").addEventListener("pointerleave", () => { ptr = null; });

  addMenuItem("tools", {id: "mi-present", label: "🖥 Layar presentasi (2 layar)…", sep: true, action: open});
  window.openPresentation = open;
})();
