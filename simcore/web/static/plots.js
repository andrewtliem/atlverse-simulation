// Live plots while a run is animated, like Arena's Plot animation: queue lengths (NQ),
// resources busy (NR) and entities in the system (WIP) against simulated time, drawn up to
// the animation clock. Loaded after the editor script; wraps startAnim, apply, draw, stopAnim.
(function () {
  const COLORS = ["#0072ce", "#f59e0b", "#16a34a", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"];
  const GROUPS = [["nq", "Panjang antrean (NQ)"], ["nr", "Resource sibuk (NR)"], ["wip", "Entity di sistem (WIP)"]];
  let P = null;   // {series: {key: {group, label, pts: [[t, v]], cap}}, lastDraw}
  let open = true;
  try { open = localStorage.getItem("atl.plots") !== "0"; } catch (e) {}

  const box = document.createElement("div");
  box.id = "plots"; box.hidden = true; box.setAttribute("aria-label", "Plot animasi");
  box.innerHTML = `<div class="plhead"><b>📈 Plot</b><span class="hint" id="pltime"></span><span style="flex:1"></span><button id="plmin" title="Sembunyikan plot" aria-label="Sembunyikan plot">–</button></div><div id="plbody"></div>`;
  $("stage").appendChild(box);
  const btn = document.createElement("button");
  btn.id = "bplots"; btn.textContent = "📈 Plot"; btn.title = "Tampilkan / sembunyikan plot antrean dan resource";
  $("aexit").before(btn);
  const st = document.createElement("style");
  st.textContent = `#plots { position: absolute; top: 10px; right: 10px; width: 340px; max-width: calc(100% - 20px); max-height: calc(100% - 70px); overflow: auto;
    background: color-mix(in srgb, var(--panel) 94%, transparent); border: 1px solid var(--line); border-radius: 8px; padding: 6px 8px; box-shadow: 0 4px 14px rgba(0,0,0,.12); z-index: 3; font-size: 12px; }
  #plots[hidden] { display: none; }
  .plhead { display: flex; gap: 8px; align-items: center; }
  .plhead button { padding: 0 8px; }
  .plg { margin-top: 6px; }
  .plg svg { width: 100%; height: auto; display: block; }
  .plleg { display: flex; flex-wrap: wrap; gap: 2px 10px; }
  .plleg i { display: inline-block; width: 10px; height: 3px; vertical-align: middle; margin-right: 4px; border-radius: 2px; }
  #bplots.on { border-color: var(--accent); color: var(--accent); }`;
  document.head.appendChild(st);
  const show = () => { box.hidden = !(P && open); btn.classList.toggle("on", open); btn.setAttribute("aria-pressed", String(open)); };
  const toggle = v => { open = v; try { localStorage.setItem("atl.plots", open ? "1" : "0"); } catch (e) {} show(); if (open) render(true); };
  btn.onclick = () => toggle(!open);
  $("plmin").onclick = () => toggle(false);

  function series(key, group, label) { return P.series[key] ||= {group, label, pts: [[0, 0]]}; }
  function record(key, group, label, t, v) {
    const s = series(key, group, label), last = s.pts[s.pts.length - 1];
    if (last[1] === v) return;
    if (last[0] === t) last[1] = v; else s.pts.push([t, v]);
  }

  let starting = false;   // startAnim calls stopAnim first
  const _startAnim = startAnim;
  startAnim = function (res, paused) {
    P = {series: {}, lastDraw: 0};
    for (const n of allNodes()) { const q = moduleQueue(n); if (q) series("q:" + q, "nq", q); }
    for (const r of Object.keys(model.data.resources)) series("r:" + r, "nr", r);
    series("wip", "wip", "WIP");
    starting = true;
    try { _startAnim(res, paused); } finally { starting = false; }
    show(); render(true);
  };
  const _apply = apply;
  apply = function (e) {
    _apply(e);
    if (!P) return;
    const [t, kind, a, b, c, d] = e;
    if (kind === "queue" && !String(a).startsWith("__")) record("q:" + a, "nq", a, t, b);
    else if (kind === "resource") { record("r:" + a, "nr", a, t, c); if (typeof d === "number") P.series["r:" + a].cap = Math.max(P.series["r:" + a].cap || 0, d); }
    else if (kind === "move" || kind === "dispose") record("wip", "wip", "WIP", t, anim.ents.size);
  };
  const _draw = draw;
  draw = function () { _draw(); if (P && open) render(false); };
  const _stopAnim = stopAnim;
  stopAnim = function () { _stopAnim(); if (!starting) { P = null; show(); } };

  function valueAt(pts, t) {   // step function value at time t
    let lo = 0, hi = pts.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (pts[mid][0] <= t) lo = mid; else hi = mid - 1; }
    return pts[lo][1];
  }
  function path(pts, t1, x, y, cols) {   // the step series up to t1, at most one corner pair per pixel column
    let d = "", prevV = null, i = 0;
    for (let col = 0; col <= cols; col++) {
      const t = t1 * col / cols;
      let mx = -Infinity, mn = Infinity;
      while (i < pts.length && pts[i][0] <= t) { mx = Math.max(mx, pts[i][1]); mn = Math.min(mn, pts[i][1]); i++; }
      const v = valueAt(pts, t);
      if (prevV === null) d += `M${x(0)},${y(v)}`;
      else {
        if (mx > -Infinity && (mx !== prevV || mn !== prevV)) d += `L${x(t)},${y(prevV)}L${x(t)},${y(mx)}L${x(t)},${y(mn)}`;
        d += `L${x(t)},${y(v)}`;
      }
      prevV = v;
    }
    return d;
  }
  function render(force) {
    if (!P || !anim || box.hidden) return;
    const now = performance.now();
    if (!force && now - P.lastDraw < 120) return;
    P.lastDraw = now;
    const t1 = Math.max(anim.t, 1e-9), end = Math.max(anim.end, t1);
    $("pltime").textContent = `t = ${fmt(anim.t)} ${model.time_units}`;
    let html = "";
    for (const [g, title] of GROUPS) {
      const ss = Object.entries(P.series).filter(([, s]) => s.group === g);
      if (!ss.length) continue;
      const W0 = 320, H0 = 92, L = 26, B = 14, cols = 160;
      const ymax = Math.max(1, ...ss.map(([, s]) => Math.max(s.cap || 0, ...s.pts.filter(p => p[0] <= t1).map(p => p[1]))));
      const x = t => L + (t / end) * (W0 - L - 4), y = v => H0 - B - (v / ymax) * (H0 - B - 6);
      let svg = `<line x1="${L}" x2="${W0 - 4}" y1="${H0 - B}" y2="${H0 - B}" stroke="var(--line)"/><line x1="${L}" x2="${L}" y1="4" y2="${H0 - B}" stroke="var(--line)"/>`;
      svg += `<text x="${L - 4}" y="${y(ymax) + 4}" font-size="10" text-anchor="end" fill="currentColor">${fmt(ymax)}</text><text x="${L - 4}" y="${H0 - B}" font-size="10" text-anchor="end" fill="currentColor">0</text>`;
      svg += `<text x="${W0 - 4}" y="${H0 - 2}" font-size="10" text-anchor="end" fill="currentColor">${fmt(end)}</text>`;
      svg += `<line x1="${x(t1)}" x2="${x(t1)}" y1="4" y2="${H0 - B}" stroke="var(--muted)" stroke-dasharray="2 3"/>`;
      let leg = "";
      ss.forEach(([k, s], i) => {
        const c = COLORS[i % COLORS.length];
        svg += `<path d="${path(s.pts, t1, x, y, cols)}" fill="none" stroke="${c}" stroke-width="1.6"/>`;
        leg += `<span><i style="background:${c}"></i>${esc(s.label)}: <b>${fmt(valueAt(s.pts, t1))}</b>${s.cap ? ` / ${fmt(s.cap)}` : ""}</span>`;
      });
      html += `<div class="plg"><div class="hint">${title}</div><svg viewBox="0 0 ${W0} ${H0}" role="img" aria-label="${title}">${svg}</svg><div class="plleg">${leg}</div></div>`;
    }
    $("plbody").innerHTML = html;
  }
})();
