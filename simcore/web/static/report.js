// Student identity, model authorship and the report students hand in.
// Loaded after the editor script (uses model, lastResults, snapshot, G, toast, esc, ...).
//  - Identitas mahasiswa (name, NIM, class) is kept in this browser and stamped into the
//    model (model.meta) on Save and Export JSON: the model keeps an ID from its first save
//    and a list of everyone who saved it, so a copied file still names its first author.
//    The history is sealed, so editing it by hand is noticed, and every module carries a
//    random mark that travels with it through Import and copy/paste, so modules taken from
//    someone else's model are recognised even when the history was deleted from the file.
//  - File → Laporan: a self-contained HTML report (or print it to PDF) with the student's
//    watermark on every page and a verification code over its contents.
//  - File → Periksa laporan: the lecturer opens a report file to check its code and history.

const ATL_ID_KEY = "atl.identity";
function atlIdentity() { try { return JSON.parse(localStorage.getItem(ATL_ID_KEY) || "null"); } catch (e) { return null; } }
function atlHash(str) {   // cyrb53: a short, stable fingerprint (not a security guarantee)
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) { const c = str.charCodeAt(i); h1 = Math.imul(h1 ^ c, 2654435761); h2 = Math.imul(h2 ^ c, 1597334677); }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).toUpperCase().padStart(14, "0");
}
const atlCode = s => { const h = atlHash("atlverse-simulation|" + s); return `ATL-${h.slice(0, 4)}-${h.slice(4, 8)}-${h.slice(8, 12)}`; };

const metaSeal = meta => atlHash("atl-meta|" + JSON.stringify([meta.id, meta.created, meta.authors || [], !!meta.edited, !!meta.lost]));
function eachModule(m, fn) { const walk = g => { for (const n of (g && g.nodes) || []) { fn(n); if (n.sub) walk(n.sub); } }; walk(m); }
function moduleMarks(m) { const a = []; eachModule(m, n => { if (n.mk) a.push(n.mk); }); return a; }
function markModules(m) {   // a random mark per module; a duplicate inside one model gets a new one
  const seen = new Set();
  eachModule(m, n => { if (!n.mk || seen.has(n.mk)) n.mk = "k" + atlHash(Math.random() + "|" + performance.now()).slice(0, 10); seen.add(n.mk); });
}
// Problems with a model's history, for the report checks.
function historyFlags(meta) {
  const f = [];
  if (meta && meta.edited) f.push("Riwayat penulis model pernah diubah manual (di luar aplikasi)");
  if (meta && meta.lost) f.push("Model dimulai dari modul yang diimpor atau ditempel tanpa riwayatnya");
  if (meta && meta.seal && meta.seal !== metaSeal(meta)) f.push("Riwayat penulis di laporan ini tidak sah");
  return f;
}
function stampModel(m) {   // who worked on this model; returns m
  const me = atlIdentity(), now = new Date().toISOString();
  const hadMarks = moduleMarks(m).length > 0;
  if (!m.meta) m.meta = hadMarks ? {lost: true} : {};   // marked modules without a history: it was removed
  else if (m.meta.seal ? m.meta.seal !== metaSeal(m.meta) : m.meta.v >= 2) m.meta.edited = true;
  markModules(m);
  m.meta.id ||= "M-" + atlHash(now + Math.random()).slice(0, 10);
  m.meta.created ||= now;
  if (me && me.nim) {
    const a = m.meta.authors ||= [], last = a[a.length - 1];
    if (last && last.nim === me.nim) { last.name = me.name; last.kelas = me.kelas; last.last = now; }
    else a.push({name: me.name, nim: me.nim, kelas: me.kelas || "", first: now, last: now});
  }
  m.meta.v = 2; m.meta.seal = metaSeal(m.meta);
  return m;
}

// ---------- Identitas dialog ----------
const idDlg = document.createElement("div");
idDlg.className = "dlg"; idDlg.id = "iddlg"; idDlg.hidden = true;
idDlg.setAttribute("role", "dialog"); idDlg.setAttribute("aria-modal", "true"); idDlg.setAttribute("aria-labelledby", "idtitle");
idDlg.innerHTML = `<div class="dlgbox" style="width:min(440px,100%)">
  <h3 id="idtitle">Identitas mahasiswa</h3>
  <p class="hint">Dicatat di model saat Save / Export JSON dan dicetak sebagai watermark di laporan. Disimpan hanya di browser ini.</p>
  <div class="idgrid">
    <label for="idname">Nama</label><input id="idname" autocomplete="name">
    <label for="idnim">NIM</label><input id="idnim" inputmode="numeric">
    <label for="idkelas">Kelas</label><input id="idkelas" placeholder="mis. TI-3A">
  </div>
  <p id="idmsg" class="hint" style="color:var(--bad, #c0392b)"></p>
  <div class="dlgbtns"><button id="idok" class="primary">Simpan</button><button id="idcancel">Batal</button></div>
</div>`;
document.body.appendChild(idDlg);
const idStyle = document.createElement("style");
idStyle.textContent = `.idgrid { display: grid; grid-template-columns: 70px 1fr; gap: 8px 10px; align-items: center; }
.idgrid input { width: 100%; box-sizing: border-box; }
#idchip { font-size: 13px; cursor: pointer; padding: 4px 10px; border: 1px solid var(--line); border-radius: 999px; white-space: nowrap; max-width: 150px; overflow: hidden; text-overflow: ellipsis; }
#idchip:hover { border-color: var(--accent); }
#idchip.none { color: #b45309; border-color: #f59e0b; }
#idchip:hover { color: var(--accent); }
.dlg .warn { color: #b45309; font-weight: 600; }`;
document.head.appendChild(idStyle);
let idThen = null;
function askIdentity(then) {
  const me = atlIdentity() || {};
  $("idname").value = me.name || ""; $("idnim").value = me.nim || ""; $("idkelas").value = me.kelas || ""; $("idmsg").textContent = "";
  idThen = then || null; idDlg.hidden = false; $("idname").focus();
}
function closeIdentity(ok) {
  if (ok) {
    const me = {name: $("idname").value.trim(), nim: $("idnim").value.trim(), kelas: $("idkelas").value.trim()};
    if (!me.name || !me.nim) { $("idmsg").textContent = "Nama dan NIM wajib diisi."; return; }
    try { localStorage.setItem(ATL_ID_KEY, JSON.stringify(me)); } catch (e) {}
    if (!String(model.run.analyst || "").trim()) model.run.analyst = `${me.name} (${me.nim})`;
    showIdChip();
  }
  idDlg.hidden = true;
  const t = idThen; idThen = null;
  if (ok && t) t();
}
$("idok").onclick = () => closeIdentity(true);
$("idcancel").onclick = () => closeIdentity(false);
idDlg.addEventListener("keydown", ev => { if (ev.key === "Escape") closeIdentity(false); if (ev.key === "Enter") closeIdentity(true); });
const idChip = document.createElement("span"); idChip.id = "idchip"; idChip.setAttribute("role", "button"); idChip.tabIndex = 0;
idChip.onclick = () => askIdentity(); idChip.onkeydown = ev => { if (ev.key === "Enter") askIdentity(); };
$("helpbar").appendChild(idChip);
function showIdChip() {
  const me = atlIdentity();
  idChip.textContent = me ? `👤 ${me.name.split(" ")[0]}` : "👤 Identitas"; idChip.classList.toggle("none", !me);
  idChip.setAttribute("aria-label", me ? `Identitas: ${me.name}` : "Isi identitas mahasiswa");
  idChip.title = me ? `${me.name} · ${me.nim}${me.kelas ? " · " + me.kelas : ""} — klik untuk mengubah` : "Isi identitas mahasiswa (untuk laporan dan watermark)";
}
showIdChip();
const withIdentity = fn => atlIdentity() ? fn() : askIdentity(fn);

// stamp on Save (button and Ctrl+S)
const _atlSave = save;
save = async function () { stampModel(model); return _atlSave(); };
$("bsave").onclick = save;

// ---------- File and Help menus ----------
{
  const _fileAction = fileAction;
  fileAction = function (v) { if (v === "json") stampModel(model); return _fileAction(v); };
  addMenuItem("file", {id: "mi-report", label: "Laporan HTML (unduh)", sep: true, action: () => withIdentity(() => exportReport(false))});
  addMenuItem("file", {id: "mi-pdf", label: "Laporan PDF (cetak)…", action: () => withIdentity(() => exportReport(true))});
  addMenuItem("file", {id: "mi-verify", label: "Periksa laporan…", action: () => $("verifyinput").click()});
  addMenuItem("help", {id: "mi-identity", label: "Identitas mahasiswa…", sep: true, action: () => askIdentity()});
  const inp = document.createElement("input"); inp.type = "file"; inp.id = "verifyinput"; inp.accept = ".html,text/html"; inp.hidden = true;
  document.body.appendChild(inp);
  inp.onchange = async () => { const file = inp.files[0]; inp.value = ""; if (file) showVerify(file.name, await file.text()); };
}

// ---------- the report ----------
const LOGO_SVG = `<svg viewBox="0 0 64 64" aria-hidden="true"><g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="5.5">
<path d="M7 49 L23 15 Q24.5 12 27.5 12 H28.5 Q31.5 12 33 15 L45 41 Q46.5 44 49.5 44 H50 L57 30" stroke="#00509e" transform="translate(0 -7.5)"/><path d="M7 49 L23 15 Q24.5 12 27.5 12 H28.5 Q31.5 12 33 15 L45 41 Q46.5 44 49.5 44 H50 L57 30" stroke="#ffc800"/><path d="M7 49 L23 15 Q24.5 12 27.5 12 H28.5 Q31.5 12 33 15 L45 41 Q46.5 44 49.5 44 H50 L57 30" stroke="#0072ce" transform="translate(0 7.5)"/></g></svg>`;
const REPORT_CSS = `
:root { --ink: #1a1714; --muted: #5c544a; --rule: #cfc4b1; --yellow: #ffc800; --blue: #0072ce; --navy: #00509e; }
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: var(--ink); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.band { height: 10px; background: linear-gradient(90deg, var(--yellow) 0%, var(--yellow) 15%, var(--blue) 100%); }
header.top { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; padding: 18px 32px 12px; border-bottom: 2px solid var(--ink); flex-wrap: wrap; }
.brand { font-weight: 700; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.brand b { color: var(--blue); }
.brand svg { width: 22px; height: 22px; }
h1 { margin: 6px 0 0; font-size: 26px; }
main { padding: 8px 32px 40px; max-width: 1100px; }
.who { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px 24px; margin: 14px 0; padding: 12px 14px; border: 1px solid var(--rule); border-radius: 8px; }
.who div span { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.who div b { font-weight: 600; }
h2 { font-size: 17px; margin: 22px 0 6px; padding-bottom: 4px; border-bottom: 1px solid var(--rule); break-after: avoid; }
h3 { font-size: 14px; margin: 14px 0 4px; }
table { border-collapse: collapse; margin: 4px 0 10px; font-size: 12.5px; break-inside: avoid; }
th, td { border: 1px solid var(--rule); padding: 3px 8px; text-align: left; }
th { background: #f6f1e7; font-weight: 600; }
td { font-variant-numeric: tabular-nums; }
.diagram { border: 1px solid var(--rule); border-radius: 8px; padding: 8px; break-inside: avoid; }
.diagram svg { width: 100%; height: auto; max-height: 520px; display: block; }
.chart svg { max-width: 640px; width: 100%; height: auto; display: block; }
.hist { font-size: 12.5px; color: var(--muted); }
.warn { color: #9a3412; font-weight: 600; }
footer.foot { position: fixed; left: 0; right: 0; bottom: 0; background: var(--navy); color: #fff; font: 11px/1.2 ui-monospace, "SFMono-Regular", Menlo, monospace; padding: 6px 32px; display: flex; justify-content: space-between; gap: 12px; }
.wm { position: fixed; inset: 0; pointer-events: none; overflow: hidden; z-index: 5; }
.wm div { position: absolute; white-space: nowrap; font-size: 22px; font-weight: 700; color: rgba(0, 80, 158, .085); transform: rotate(-28deg); transform-origin: left top; user-select: none; }
.actions { position: fixed; top: 18px; right: 24px; z-index: 6; display: flex; gap: 8px; }
.actions button { font: inherit; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--navy); background: var(--navy); color: #fff; cursor: pointer; }
pre.txt { white-space: pre-wrap; font-size: 11px; border: 1px solid var(--rule); padding: 8px; border-radius: 6px; }
table.pg { break-inside: auto; border-collapse: collapse; width: 100%; } table.pg > * > tr > td { border: 0; padding: 0; margin: 0; }
.pgspace { height: 0; }
@media print { .actions { display: none; } @page { margin: 12mm 10mm 10mm; } .pgspace { height: 30px; } }
`;

function inlineSvg(live) {   // a standalone copy of an on-screen SVG with its computed colours inlined
  const copy = live.cloneNode(true);
  const props = ["fill", "fill-opacity", "stroke", "stroke-width", "stroke-dasharray", "stroke-opacity", "opacity", "font-size", "font-family", "font-weight", "text-anchor", "dominant-baseline", "visibility", "display"];
  const a = [live, ...live.querySelectorAll("*")], b = [copy, ...copy.querySelectorAll("*")];
  a.forEach((el, i) => {
    const cs = getComputedStyle(el);
    b[i].setAttribute("style", props.map(p => `${p}:${cs.getPropertyValue(p)}`).join(";"));
    b[i].removeAttribute("class");
  });
  return copy;
}
function diagramSvg() {
  const root = document.documentElement, theme = root.dataset.theme;
  root.dataset.theme = "light";
  try {
    const svg = inlineSvg($("canvas"));
    for (const id of ["gridrect", "ghost", "band", "ents"]) svg.querySelector("#" + id)?.remove();
    svg.querySelectorAll(".badge, .portcount, [id^=badge-], [id^=pc-]").forEach(e => e.textContent = "");
    const w = svg.querySelector("#world"); w.removeAttribute("transform");
    const nodes = G().nodes; if (!nodes.length) return "";
    const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
    const x0 = Math.min(...xs) - 20, y0 = Math.min(...ys) - 20, x1 = Math.max(...xs) + W + 20, y1 = Math.max(...ys) + H + 30;
    svg.setAttribute("viewBox", `${x0} ${y0} ${x1 - x0} ${y1 - y0}`);
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.removeAttribute("id"); svg.querySelectorAll("[id]").forEach(e => { if (!["arrow", "gridpat"].includes(e.id)) e.removeAttribute("id"); });
    return svg.outerHTML;
  } finally { if (theme) root.dataset.theme = theme; else delete root.dataset.theme; }
}
function summaryHtml() {
  const live = $("p-summary"), copy = live.cloneNode(true);
  const liveSvgs = live.querySelectorAll("svg"), copySvgs = copy.querySelectorAll("svg");
  copySvgs.forEach((s, i) => s.replaceWith(inlineSvg(liveSvgs[i])));
  copy.querySelectorAll(".learn, button, .qm, script").forEach(e => e.remove());
  copy.querySelectorAll("a").forEach(a => a.replaceWith(document.createTextNode(a.textContent)));
  copy.querySelectorAll("[id], [class], [onclick], [tabindex], [role]").forEach(e => { e.removeAttribute("onclick"); e.removeAttribute("tabindex"); e.removeAttribute("role"); });
  copy.querySelectorAll(".chart, .chartbox").forEach(e => e.classList.add("chart"));
  return copy.innerHTML;
}
const fmtDate = iso => { try { return new Date(iso).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"}); } catch (e) { return iso; } };

function reportPayload() {
  const me = atlIdentity(), res = lastResults;
  stampModel(model);
  const created = new Date().toISOString();
  const m = JSON.parse(snapshot());
  return {v: 1, identity: me, created, model: m, report: res.report, code: CODE_PH};
}
// The verification code covers the whole file: it is computed with this placeholder in
// every place the code appears, then written in. Checking replaces it back and recomputes.
const CODE_PH = "ATL-????-????-????";
const sealReport = html => { const code = atlCode(html); return {html: html.split(CODE_PH).join(code), code}; };
function buildReport(print) { return sealReport(reportHtml(print)).html; }
function reportHtml(print) {
  const p = reportPayload(), me = p.identity, meta = p.model.meta || {}, run = model.run;
  const authors = meta.authors || [];
  const foreign = authors.filter(a => a.nim !== me.nim);
  const hist = authors.map(a => `${esc(a.name)} (${esc(a.nim)}) ${fmtDate(a.first)}${a.last && a.last !== a.first ? " – " + fmtDate(a.last) : ""}`).join(" → ");
  const wmText = esc(`${me.name} · ${me.nim} · ${p.code}`);
  let wm = "";
  for (let r = 0; r < 14; r++) for (let c = 0; c < 4; c++) wm += `<div style="left:${c * 30 - 10 + (r % 2) * 15}%;top:${r * 9 + 4}%">${wmText}</div>`;
  const reps = res => res.replications.length;
  const setup = [["Replikasi", run.replications], ["Panjang replikasi", `${run.length} ${run.length_units || ""}`], ["Warm-up", `${run.warmup || 0} ${run.warmup_units || ""}`], ["Satuan waktu dasar", model.time_units]];
  const scen = typeof scenarioReportHtml === "function" ? scenarioReportHtml() : "";
  const data = JSON.stringify(p).replace(/</g, "\\u003c");
  return `<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laporan ${esc(model.name)} — ${esc(me.name)} (${esc(me.nim)})</title>
<meta name="generator" content="Atlverse Simulation"><meta name="atl-code" content="${p.code}">
<style>${REPORT_CSS}</style></head>
<body>
<div class="band"></div>
<div class="actions"><button onclick="print()">Cetak / Simpan PDF</button></div>
<header class="top"><div><div class="brand">${LOGO_SVG}Atlverse <b>Simulation</b></div><h1>Laporan Simulasi: ${esc(model.name)}</h1></div>
<div style="text-align:right;font:12px ui-monospace,monospace;color:#5c544a">Kode verifikasi<br><b style="font-size:15px;color:#00509e">${p.code}</b></div></header>
<table class="pg"><tfoot><tr><td><div class="pgspace"></div></td></tr></tfoot><tbody><tr><td>
<main>
<section class="who">
  <div><span>Nama</span><b>${esc(me.name)}</b></div><div><span>NIM</span><b>${esc(me.nim)}</b></div>
  <div><span>Kelas</span><b>${esc(me.kelas || "–")}</b></div><div><span>Dibuat</span><b>${fmtDate(p.created)}</b></div>
  <div><span>Model ID</span><b>${esc(meta.id || "–")}</b></div><div><span>Replikasi</span><b>${reps(lastResults)}</b></div>
</section>
<p class="hist">Riwayat penulis model: ${hist || "–"}${foreign.length ? `<br><span class="warn">⚠ Model ini juga disimpan oleh NIM lain: ${foreign.map(a => esc(a.nim)).join(", ")}</span>` : ""}</p>
${run.description ? `<h2>Deskripsi</h2><p>${esc(run.description)}</p>` : ""}
<h2>Model</h2><div class="diagram">${diagramSvg()}</div>
<h2>Run Setup</h2><table>${setup.map(([k, v]) => `<tr><th>${k}</th><td>${esc(v)}</td></tr>`).join("")}</table>
<h2>Hasil (Category Overview)</h2>${summaryHtml()}
${scen}
<details><summary><b>Laporan teks lengkap</b> (klik untuk membuka; tidak ikut dicetak bila tertutup)</summary><pre class="txt">${esc(lastResults.report)}</pre></details>
</main>
</td></tr></tbody></table>
<div class="wm" aria-hidden="true">${wm}</div>
<footer class="foot"><span>Atlverse Simulation · ${esc(me.name)} · ${esc(me.nim)}</span><span>${p.code}</span></footer>
<script type="application/json" id="atl-data">${data}</script>
${print ? "<script>addEventListener('load', () => setTimeout(() => print(), 300));</script>" : ""}
</body></html>`;
}
function exportReport(print) {
  if (!lastResults) { toast("Jalankan model sampai selesai dulu — laporan memakai hasil run terakhir"); return; }
  const noMarks = (k, v) => k === "mk" ? undefined : v;   // marks added on save do not change the model
  if (lastResults._model && JSON.stringify(lastResults._model.nodes, noMarks) !== JSON.stringify(model.nodes, noMarks)) toast("Catatan: model sudah diubah sejak run terakhir — jalankan ulang agar laporan sesuai");
  const html = buildReport(print), me = atlIdentity();
  const file = `Laporan_${(model.name || "model").replace(/[^\w-]+/g, "_")}_${me.nim}.html`;
  if (print) {
    const w = open(URL.createObjectURL(new Blob([html], {type: "text/html"})), "_blank");
    if (!w) { download(file, html, "text/html"); toast("Pop-up diblokir — laporan diunduh; buka file lalu Cetak / Simpan PDF"); }
  } else { download(file, html, "text/html"); toast("Laporan diunduh: " + file); }
  return html;
}

// ---------- Periksa laporan (lecturer) ----------
function verifyReport(html) {
  const m = html.match(/<script type="application\/json" id="atl-data">([\s\S]*?)<\/script>/);
  if (!m) return {ok: false, why: "Bukan laporan Atlverse Simulation (data laporan tidak ditemukan)."};
  let p; try { p = JSON.parse(m[1]); } catch (e) { return {ok: false, why: "Data laporan rusak."}; }
  const code = (html.match(/<meta name="atl-code" content="([^"]+)"/) || [])[1] || "";
  const again = code ? atlCode(html.split(code).join(CODE_PH)) : "–";
  p.code = code;
  return {ok: !!code && again === code, p, code, again};
}
const vDlg = document.createElement("div");
vDlg.className = "dlg"; vDlg.hidden = true; vDlg.setAttribute("role", "dialog"); vDlg.setAttribute("aria-modal", "true"); vDlg.setAttribute("aria-labelledby", "vtitle");
vDlg.innerHTML = `<div class="dlgbox"><h3 id="vtitle">Periksa laporan</h3><div id="vbody"></div>
  <div class="dlgbtns"><button id="vopen">Buka modelnya</button><button id="vclose" class="primary">Tutup</button></div></div>`;
document.body.appendChild(vDlg);
$("vclose").onclick = () => vDlg.hidden = true;
vDlg.addEventListener("keydown", ev => { if (ev.key === "Escape") vDlg.hidden = true; });
function showVerify(name, html) {
  const r = verifyReport(html), b = $("vbody");
  $("vopen").hidden = !r.p;
  if (!r.p) { b.innerHTML = `<p><b>${esc(name)}</b></p><p class="warn">✖ ${esc(r.why)}</p>`; vDlg.hidden = false; return; }
  const p = r.p, me = p.identity || {}, a = (p.model.meta || {}).authors || [];
  const others = a.filter(x => x.nim !== me.nim);
  b.innerHTML = `<p><b>${esc(name)}</b></p>
    <p style="font-size:15px">${r.ok ? '✅ <b>Kode cocok</b> — isi laporan tidak diubah setelah dibuat.' : '❌ <b>Kode tidak cocok</b> — isi laporan diubah setelah dibuat.'}</p>
    <table class="res"><tr><th>Mahasiswa</th><td>${esc(me.name)} · ${esc(me.nim)}${me.kelas ? " · " + esc(me.kelas) : ""}</td></tr>
    <tr><th>Dibuat</th><td>${fmtDate(p.created)}</td></tr><tr><th>Model</th><td>${esc(p.model.name)} · ID ${esc((p.model.meta || {}).id || "–")}</td></tr>
    <tr><th>Kode</th><td>${esc(r.code)}${r.ok ? "" : ` (dihitung ulang: ${esc(r.again)})`}</td></tr>
    <tr><th>Riwayat penulis</th><td>${a.map(x => `${esc(x.name)} (${esc(x.nim)})`).join(" → ") || "–"}</td></tr></table>
    ${others.length ? `<p class="warn">⚠ Model juga disimpan oleh NIM lain: ${others.map(x => esc(x.nim)).join(", ")}. Bisa jadi kerja kelompok, atau file disalin.</p>` : ""}
    ${historyFlags(p.model.meta).map(t => `<p class="warn">⚠ ${esc(t)}.</p>`).join("")}
    <p class="hint">Dua laporan dengan Model ID yang sama berasal dari file model yang sama. Kode verifikasi mendeteksi perubahan isi laporan, tetapi bukan jaminan kriptografis.</p>`;
  $("vopen").onclick = async () => { vDlg.hidden = true; const prev = snapshot(); setModel(await upgraded(p.model)); undo = [prev]; updateButtons(); markDirty(); requestAnimationFrame(fit); toast("Model dari laporan dibuka — Ctrl+Z kembali"); };
  vDlg.hidden = false;
}
