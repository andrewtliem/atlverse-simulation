// Input Analyzer, after Arena's: paste or load observed data (service times, times between
// arrivals, ...), see the histogram, fit the usual distributions and get the expression to
// use in a module. Fits are ranked by square error, with chi-square and K-S tests, as in
// Arena. Loaded after the editor script; opened from Tools → Input Analyzer.

(function () {
// ---------- math ----------
function lgam(x) {   // log Gamma, Lanczos
  const g = 7, c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
    12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  if (x < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * x)) - lgam(1 - x);
  x -= 1; let a = c[0]; const t = x + g + 0.5;
  for (let i = 1; i < 9; i++) a += c[i] / (x + i);
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}
function gammaP(a, x) {   // regularized lower incomplete gamma
  if (x <= 0) return 0;
  if (x < a + 1) { let s = 1 / a, d = s, ap = a; for (let n = 0; n < 500; n++) { ap++; d *= x / ap; s += d; if (Math.abs(d) < Math.abs(s) * 1e-14) break; } return s * Math.exp(-x + a * Math.log(x) - lgam(a)); }
  let b = x + 1 - a, c = 1e300, d = 1 / b, h = d;
  for (let i = 1; i < 500; i++) { const an = -i * (i - a); b += 2; d = an * d + b; if (Math.abs(d) < 1e-300) d = 1e-300; c = b + an / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; const del = d * c; h *= del; if (Math.abs(del - 1) < 1e-14) break; }
  return 1 - Math.exp(-x + a * Math.log(x) - lgam(a)) * h;
}
function betaCf(a, b, x) {
  let qab = a + b, qap = a + 1, qam = a - 1, c = 1, d = 1 - qab * x / qap;
  if (Math.abs(d) < 1e-300) d = 1e-300; d = 1 / d; let h = d;
  for (let m = 1; m < 300; m++) {
    const m2 = 2 * m; let aa = m * (b - m) * x / ((qam + m2) * (a + m2));
    d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; h *= d * c;
    aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
    d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d;
    const del = d * c; h *= del; if (Math.abs(del - 1) < 1e-14) break;
  }
  return h;
}
function betaI(a, b, x) {   // regularized incomplete beta
  if (x <= 0) return 0; if (x >= 1) return 1;
  const bt = Math.exp(lgam(a + b) - lgam(a) - lgam(b) + a * Math.log(x) + b * Math.log(1 - x));
  return x < (a + 1) / (a + b + 2) ? bt * betaCf(a, b, x) / a : 1 - bt * betaCf(b, a, 1 - x) / b;
}
const erf = x => { const t = 1 / (1 + 0.5 * Math.abs(x)); const y = 1 - t * Math.exp(-x * x - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277))))))))); return x >= 0 ? y : -y; };
const phi = z => 0.5 * (1 + erf(z / Math.SQRT2));
function ksQ(l) { if (l < 0.2) return 1; let s = 0; for (let j = 1; j < 100; j++) s += 2 * (j % 2 ? 1 : -1) * Math.exp(-2 * j * j * l * l); return Math.min(1, Math.max(0, s)); }

// "nice" round numbers for offsets and bounds, as Arena shows them
const sig = (v, d = 4) => v === 0 || !isFinite(v) ? v : +v.toPrecision(d);
function niceFloor(v) { if (v <= 0) return Math.floor(v); const p = 10 ** Math.floor(Math.log10(v)); return Math.floor(v / p * 10) * p / 10; }
function niceCeil(v) { if (v <= 0) return Math.ceil(v); const p = 10 ** Math.floor(Math.log10(v)); return Math.ceil(v / p * 10) * p / 10; }
const num = v => String(sig(v));
const withOff = (o, e) => o ? `${num(o)} + ${e}` : e;

// ---------- fits: each returns {name, expr, k (parameters), cdf} or null ----------
function moments(x) { const n = x.length, m = x.reduce((a, b) => a + b, 0) / n; const v = x.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, n - 1); return {n, m, v, sd: Math.sqrt(v)}; }
function fitAll(x) {
  const {m, v, sd} = moments(x), lo = Math.min(...x), hi = Math.max(...x), fits = [];
  const add = f => { if (f && isFinite(f.cdf((lo + hi) / 2))) fits.push(f); };
  add({name: "Normal", dist: "NORM", expr: `NORM(${num(m)}, ${num(sd)})`, k: 2, cdf: t => phi((t - m) / sd)});
  add({name: "Uniform", dist: "UNIF", expr: `UNIF(${num(lo)}, ${num(hi)})`, k: 2, cdf: t => t <= lo ? 0 : t >= hi ? 1 : (t - lo) / (hi - lo)});
  if (hi > lo) {
    const c = Math.min(hi, Math.max(lo, 3 * m - lo - hi));
    add({name: "Triangular", dist: "TRIA", expr: `TRIA(${num(lo)}, ${num(c)}, ${num(hi)})`, k: 3,
      cdf: t => t <= lo ? 0 : t >= hi ? 1 : t <= c ? (t - lo) ** 2 / ((hi - lo) * (c - lo || 1e-12)) : 1 - (hi - t) ** 2 / ((hi - lo) * (hi - c || 1e-12))});
  }
  if (hi > lo) {   // Beta on [a, b]
    const a = niceFloor(lo), b = niceCeil(hi) > hi ? niceCeil(hi) : hi + (hi - lo) * 0.001;
    const mm = (m - a) / (b - a), vv = v / (b - a) ** 2, cc = mm * (1 - mm) / vv - 1;
    if (cc > 0) { const p = mm * cc, q = (1 - mm) * cc;
      add({name: "Beta", dist: "BETA", expr: `${num(a)} + ${num(b - a)} * BETA(${num(p)}, ${num(q)})`, k: 4, cdf: t => betaI(p, q, (t - a) / (b - a))}); }
  }
  // positive families, without and with an offset below the smallest value
  const offs = lo >= 0 ? [0] : [];
  if (lo > 0 && lo > 0.05 * m) offs.push(niceFloor(lo) < lo ? niceFloor(lo) : lo * 0.999);
  if (lo < 0) offs.push(niceFloor(lo) - (niceFloor(lo) === lo ? Math.abs(lo) * 0.01 : 0));
  for (const o of offs) {
    const y = x.map(t => t - o); if (y.some(t => t < 0)) continue;
    const ym = m - o, sfx = o ? " (offset)" : "";
    add({name: "Exponential" + sfx, dist: "EXPO", expr: withOff(o, `EXPO(${num(ym)})`), k: o ? 2 : 1, cdf: t => t <= o ? 0 : 1 - Math.exp(-(t - o) / ym)});
    const shape = ym * ym / v, scale = v / ym;
    add({name: "Gamma" + sfx, dist: "GAMM", expr: withOff(o, `GAMM(${num(scale)}, ${num(shape)})`), k: o ? 3 : 2, cdf: t => t <= o ? 0 : gammaP(shape, (t - o) / scale)});
    const ek = Math.max(1, Math.round(shape)), eb = ym / ek;
    add({name: "Erlang" + sfx, dist: "ERLA", expr: withOff(o, `ERLA(${num(eb)}, ${ek})`), k: o ? 3 : 2, cdf: t => t <= o ? 0 : gammaP(ek, (t - o) / eb)});
    if (y.every(t => t > 0)) {
      const ly = y.map(Math.log), lm = ly.reduce((a, b) => a + b, 0) / ly.length;
      const ls = Math.sqrt(ly.reduce((a, b) => a + (b - lm) ** 2, 0) / Math.max(1, ly.length - 1));
      if (ls > 0) {
        const mean = Math.exp(lm + ls * ls / 2), sdv = mean * Math.sqrt(Math.exp(ls * ls) - 1);
        add({name: "Lognormal" + sfx, dist: "LOGN", expr: withOff(o, `LOGN(${num(mean)}, ${num(sdv)})`), k: o ? 3 : 2, cdf: t => t <= o ? 0 : phi((Math.log(t - o) - lm) / ls)});
      }
      // Weibull: maximum likelihood shape by bisection
      const g = kk => { let a = 0, b = 0; for (let i = 0; i < y.length; i++) { const p = y[i] ** kk; a += p * ly[i]; b += p; } return a / b - 1 / kk - lm; };
      let k1 = 0.05, k2 = 50;
      if (g(k1) < 0 && g(k2) > 0) {
        for (let i = 0; i < 80; i++) { const mid = (k1 + k2) / 2; if (g(mid) > 0) k2 = mid; else k1 = mid; }
        const kk = (k1 + k2) / 2, lam = (y.reduce((a, t) => a + t ** kk, 0) / y.length) ** (1 / kk);
        add({name: "Weibull" + sfx, dist: "WEIB", expr: withOff(o, `WEIB(${num(lam)}, ${num(kk)})`), k: o ? 3 : 2, cdf: t => t <= o ? 0 : 1 - Math.exp(-(((t - o) / lam) ** kk))});
      }
    }
  }
  if (x.every(t => Number.isInteger(t) && t >= 0) && m > 0) {   // counts
    add({name: "Poisson", dist: "POIS", expr: `POIS(${num(m)})`, k: 1, discrete: true,
      cdf: t => { if (t < 0) return 0; let s = 0, p = Math.exp(-m); for (let i = 0; i <= Math.floor(t + 1e-9); i++) { s += p; p *= m / (i + 1); } return Math.min(1, s); }});
  }
  return fits;
}

function histogram(x, bins) {
  const lo = Math.min(...x), hi = Math.max(...x), w = (hi - lo) / bins || 1, c = new Array(bins).fill(0);
  for (const t of x) c[Math.min(bins - 1, Math.floor((t - lo) / w))]++;
  return {lo, hi, w, c, edges: c.map((_, i) => lo + i * w)};
}
function evaluateFit(f, x, h) {
  const n = x.length, cdf = f.cdf;
  // square error against the histogram (Arena's ranking)
  let se = 0; const exp = [];
  for (let i = 0; i < h.c.length; i++) {
    const a = h.lo + i * h.w, b = a + h.w;
    const p = Math.max(0, (i === h.c.length - 1 ? cdf(b + 1e-9) : cdf(b)) - (i === 0 ? cdf(a - 1e-9) : cdf(a)));
    exp.push(p); se += (h.c[i] / n - p) ** 2;
  }
  // chi-square on the histogram cells, merged until each expects at least 5
  const cells = []; let o = 0, e = 0;
  for (let i = 0; i < h.c.length; i++) { o += h.c[i]; e += exp[i] * n; if (e >= 5) { cells.push([o, e]); o = 0; e = 0; } }
  if (cells.length && (o || e)) { cells[cells.length - 1][0] += o; cells[cells.length - 1][1] += e; }
  const chi = cells.reduce((s, [ob, ex]) => s + (ob - ex) ** 2 / Math.max(ex, 1e-9), 0);
  const df = cells.length - 1 - (f.k || 1);
  const chiP = df >= 1 ? 1 - gammaP(df / 2, chi / 2) : NaN;
  // Kolmogorov-Smirnov
  const s = [...x].sort((a, b) => a - b); let d = 0;
  for (let i = 0; i < n; i++) { const F = cdf(s[i]); d = Math.max(d, (i + 1) / n - F, F - i / n); }
  const sq = Math.sqrt(n), ksP = f.discrete ? NaN : ksQ((sq + 0.12 + 0.11 / sq) * d);
  return {...f, se, chi, df, chiP, d, ksP, exp};
}

function parseData(text) {
  const toks = String(text).replace(/\r/g, "").split(/[\s;\t]+/).flatMap(t => /^-?\d+,\d+$/.test(t) ? [t.replace(",", ".")] : t.split(","));
  return toks.map(t => t.trim()).filter(t => t !== "").map(Number).filter(v => isFinite(v));
}

// ---------- dialog ----------
const aDlg = document.createElement("div");
aDlg.className = "dlg"; aDlg.id = "anadlg"; aDlg.hidden = true;
aDlg.setAttribute("role", "dialog"); aDlg.setAttribute("aria-modal", "true"); aDlg.setAttribute("aria-labelledby", "anatitle");
aDlg.innerHTML = `<div class="dlgbox wide">
  <h3 id="anatitle">Input Analyzer</h3>
  <p class="hint">Tempel data pengamatan (misalnya waktu layanan atau waktu antar-kedatangan), satu angka per baris atau dipisah spasi/koma; desimal boleh pakai koma (3,5). Atau muat file .txt / .csv. Distribusi diurutkan dari <b>square error</b> terkecil, seperti Arena.</p>
  <div class="anagrid">
    <div><textarea id="anadata" rows="9" aria-label="Data pengamatan" placeholder="4.2&#10;3.7&#10;5.1&#10;…"></textarea>
      <div class="dlgbtns" style="justify-content:flex-start;margin-top:6px"><button id="anafile">📂 Muat file…</button><button id="anasample">Contoh data</button><button id="anafit" class="primary">Fit All</button></div>
      <div id="anastats" class="hint"></div></div>
    <div><div id="anahist" class="anahist"></div>
      <label class="hint">Jumlah interval <input id="anabins" type="number" min="3" max="60" style="width:60px"></label></div>
  </div>
  <div id="anaout"></div>
  <div class="dlgbtns"><button id="anaclose" class="primary">Tutup</button></div>
  <input id="anafileinput" type="file" accept=".txt,.csv,.dat,text/plain,text/csv" hidden>
</div>`;
document.body.appendChild(aDlg);
const aStyle = document.createElement("style");
aStyle.textContent = `.anagrid { display: grid; grid-template-columns: minmax(220px, 1fr) 2fr; gap: 16px; }
@media (max-width: 760px) { .anagrid { grid-template-columns: 1fr; } }
#anadata { width: 100%; box-sizing: border-box; font-family: ui-monospace, monospace; font-size: 12.5px; }
.anahist svg { width: 100%; height: auto; display: block; }
#anaout table td:first-child { white-space: nowrap; }
#anaout tr.sel td { background: color-mix(in srgb, var(--accent) 12%, transparent); }
#anaout tr { cursor: pointer; }
.anaexpr { font-family: ui-monospace, monospace; font-size: 14px; padding: 6px 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); user-select: all; }
.anause { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }`;
document.head.appendChild(aStyle);

let ana = null;   // {x, h, fits, pick}
function openAnalyzer() { aDlg.hidden = false; $("anadata").focus(); if (ana) renderAna(); }
$("anaclose").onclick = () => aDlg.hidden = true;
aDlg.addEventListener("keydown", ev => { if (ev.key === "Escape") aDlg.hidden = true; });
$("anafile").onclick = () => $("anafileinput").click();
$("anafileinput").onchange = async () => { const f = $("anafileinput").files[0]; $("anafileinput").value = ""; if (f) { $("anadata").value = await f.text(); runAnalyzer(); } };
$("anasample").onclick = () => {   // 80 service times, about 2 + GAMM(1.2, 2.5)
  let s = 7, out = [];
  const u = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const z = () => Math.sqrt(-2 * Math.log(u())) * Math.cos(2 * Math.PI * u());
  const gam = () => -Math.log(u()) - Math.log(u()) + z() ** 2 / 2;   // Gamma(shape 2.5, scale 1)
  for (let i = 0; i < 80; i++) out.push((2 + 1.2 * gam()).toFixed(2));
  $("anadata").value = out.join("\n"); $("anabins").value = ""; runAnalyzer();
};
$("anafit").onclick = () => runAnalyzer();
$("anabins").onchange = () => runAnalyzer(+$("anabins").value);
function runAnalyzer(bins) {
  const x = parseData($("anadata").value);
  if (x.length < 5) { $("anaout").innerHTML = '<p class="hint">Masukkan minimal 5 angka (sebaiknya 30 atau lebih).</p>'; $("anahist").innerHTML = ""; $("anastats").textContent = ""; ana = null; return; }
  const k = bins >= 3 ? Math.min(60, bins) : Math.max(5, Math.min(40, Math.round(Math.sqrt(x.length))));
  $("anabins").value = k;
  const h = histogram(x, k);
  const fits = fitAll(x).map(f => evaluateFit(f, x, h)).sort((a, b) => a.se - b.se);
  ana = {x, h, fits, pick: 0};
  renderAna();
}
function histSvg(h, fit, n) {
  const W0 = 560, H0 = 220, L = 34, B = 26, w = (W0 - L - 8) / h.c.length;
  const maxP = Math.max(...h.c.map(c => c / n), ...(fit ? fit.exp : [0]), 1e-9);
  const y = p => H0 - B - (p / maxP) * (H0 - B - 10);
  let g = "";
  h.c.forEach((c, i) => { g += `<rect x="${L + i * w + 1}" y="${y(c / n)}" width="${Math.max(1, w - 2)}" height="${H0 - B - y(c / n)}" fill="#0072ce" opacity=".75"><title>${sig(h.edges[i], 4)}–${sig(h.edges[i] + h.w, 4)}: ${c}</title></rect>`; });
  if (fit) g += `<path d="${fit.exp.map((p, i) => `${i ? "L" : "M"}${L + (i + 0.5) * w},${y(p)}`).join("")}" fill="none" stroke="#ffc800" stroke-width="3"/>`;
  g += `<line x1="${L}" x2="${W0 - 8}" y1="${H0 - B}" y2="${H0 - B}" stroke="#98a2b3"/>`;
  const ticks = [0, Math.floor(h.c.length / 2), h.c.length];
  for (const t of ticks) g += `<text x="${L + t * w}" y="${H0 - 8}" font-size="11" text-anchor="middle" fill="currentColor">${sig(h.lo + t * h.w, 3)}</text>`;
  g += `<text x="${L - 4}" y="${y(maxP) + 4}" font-size="10" text-anchor="end" fill="currentColor">${(maxP * 100).toFixed(0)}%</text>`;
  return `<svg viewBox="0 0 ${W0} ${H0}" role="img" aria-label="Histogram data${fit ? " dan kurva " + fit.name : ""}">${g}</svg>`;
}
function renderAna() {
  const {x, h, fits} = ana, f = fits[ana.pick], n = x.length, mo = moments(x);
  $("anastats").innerHTML = `n = ${n} · min ${sig(Math.min(...x))} · max ${sig(Math.max(...x))} · rata-rata ${sig(mo.m)} · std dev ${sig(mo.sd)}`;
  $("anahist").innerHTML = histSvg(h, f, n) + `<div class="hint">Batang biru: data · garis kuning: ${f ? esc(f.name) : "–"}</div>`;
  const p = v => isFinite(v) ? (v < 0.005 ? "< 0.005" : v > 0.75 ? "> 0.75" : v.toFixed(3)) : "–";
  const good = f && (isFinite(f.chiP) ? f.chiP >= 0.05 : true) && (isFinite(f.ksP) ? f.ksP >= 0.05 : true);
  $("anaout").innerHTML = f ? `<div class="anause"><b>Expression:</b> <span class="anaexpr" id="anaexpr">${esc(f.expr)}</span>
      <button id="anacopy">Salin</button><button id="anause">Pakai di modul terpilih…</button></div>
    <p class="hint">${good ? "✅ Uji chi-square dan K-S tidak menolak distribusi ini (p ≥ 0.05): cocok dipakai." : "⚠ Salah satu uji menolak distribusi ini (p < 0.05). Pertimbangkan distribusi lain, data lebih banyak, atau distribusi empiris (CONT)."}
      p-value besar = data <i>konsisten</i> dengan distribusi; p-value kecil (&lt; 0.05) = tidak cocok.</p>
    <table class="res"><tr><th>Distribusi</th><th>Expression</th><th>Square Error</th><th>Chi-square p</th><th>K-S p</th></tr>
    ${fits.map((r, i) => `<tr data-i="${i}" class="${i === ana.pick ? "sel" : ""}" tabindex="0"><td>${i === 0 ? "★ " : ""}${esc(r.name)}</td><td><code>${esc(r.expr)}</code></td><td>${r.se.toFixed(5)}</td><td>${p(r.chiP)}</td><td>${p(r.ksP)}</td></tr>`).join("")}</table>
    <p class="hint">Klik baris untuk melihat kurvanya. ★ = square error terkecil. Chi-square: ${f.df >= 1 ? `${f.df} derajat bebas, statistik ${f.chi.toFixed(3)}` : "interval terlalu sedikit"}; K-S: D = ${f.d.toFixed(4)}.</p>` : '<p class="hint">Tidak ada distribusi yang bisa di-fit.</p>';
  $("anaout").querySelectorAll("tr[data-i]").forEach(tr => { const go = () => { ana.pick = +tr.dataset.i; renderAna(); }; tr.onclick = go; tr.onkeydown = ev => { if (ev.key === "Enter") go(); }; });
  if (!f) return;
  $("anacopy").onclick = async () => { try { await navigator.clipboard.writeText(f.expr); toast("Expression disalin"); } catch (e) { toast("Salin manual: " + f.expr); } };
  $("anause").onclick = () => useExpression(f.expr);
}
function useExpression(expr) {   // into the selected Create (Expression) or Process (Delay Type Expression)
  const n = sel && sel.size === 1 ? byId([...sel][0]) : null;
  if (!n || !has(n.type, "create", "process", "delay")) { toast("Pilih dulu satu modul Create, Process atau Delay di kanvas, lalu klik lagi"); return; }
  change(() => {
    if (n.type === "create") { n.props.type = "Expression"; n.props.expression = expr; }
    else if (n.type === "delay") n.props.delay_time = expr;
    else { n.props.delay_type = "Expression"; n.props.expression = expr; }
  });
  aDlg.hidden = true; toast(`${n.props.name}: ${expr}`);
}

addMenuItem("tools", {id: "mi-input", label: "Input Analyzer…", action: () => openAnalyzer()});
window.openAnalyzer = openAnalyzer;
window.atlInput = {fitAll, evaluateFit, histogram, parseData};   // for tests
})();
