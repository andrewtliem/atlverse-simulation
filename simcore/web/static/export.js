// Results to Excel (.xlsx), so students do not copy numbers out of the report by hand.
// Loaded after the editor script, report.js and scenarios.js (uses lastResults, summaryData,
// scenControls, scenResponses, scenRes, atlIdentity, download, toast, ...).
//  - Every finished run of a model is kept in this browser (Riwayat run): its parameters
//    (resource capacities, variable initial values, time between arrivals, run setup) and its
//    responses (mean and 95% half width over the replications), so runs with changed
//    parameters line up one row each in the workbook.
//  - File → Hasil ke Excel: sheets Ringkasan (identity, parameters, the Category Overview
//    tables), Per replikasi, Riwayat run, and Skenario when the Scenarios results are current.
// Numbers are written as numbers, so Excel with a comma decimal separator reads them right
// (a CSV with "3.25" would not). The .xlsx is a zip of a few XML files, written here.

// ---------- a minimal .xlsx writer ----------
const XL = (() => {
  const CRC = new Uint32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc32 = b => { let c = 0xffffffff; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  function zip(files) {   // [{name, text}] → Uint8Array, stored (no compression)
    const enc = new TextEncoder(), parts = [], dir = [];
    let off = 0;
    for (const f of files) {
      const name = enc.encode(f.name), data = enc.encode(f.text), crc = crc32(data);
      const h = new DataView(new ArrayBuffer(30));
      h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true);
      h.setUint32(14, crc, true); h.setUint32(18, data.length, true); h.setUint32(22, data.length, true); h.setUint16(26, name.length, true);
      const d = new DataView(new ArrayBuffer(46));
      d.setUint32(0, 0x02014b50, true); d.setUint16(4, 20, true); d.setUint16(6, 20, true); d.setUint16(8, 0x0800, true);
      d.setUint32(16, crc, true); d.setUint32(20, data.length, true); d.setUint32(24, data.length, true); d.setUint16(28, name.length, true); d.setUint32(42, off, true);
      parts.push(new Uint8Array(h.buffer), name, data); dir.push(new Uint8Array(d.buffer), name);
      off += 30 + name.length + data.length;
    }
    const dirLen = dir.reduce((a, b) => a + b.length, 0);
    const e = new DataView(new ArrayBuffer(22));
    e.setUint32(0, 0x06054b50, true); e.setUint16(8, files.length, true); e.setUint16(10, files.length, true); e.setUint32(12, dirLen, true); e.setUint32(16, off, true);
    const all = [...parts, ...dir, new Uint8Array(e.buffer)], out = new Uint8Array(all.reduce((a, b) => a + b.length, 0));
    let p = 0; for (const a of all) { out.set(a, p); p += a.length; }
    return out;
  }
  const x = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "");
  const col = i => { let s = ""; for (i++; i; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + (i - 1) % 26) + s; return s; };
  // styles: 0 normal, 1 bold, 2 header (bold, shaded), 3 0.0000, 4 0.00%, 5 title, 6 section (bold, blue)
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="0.0000"/></numFmts>
<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="14"/><name val="Calibri"/></font><font><b/><sz val="12"/><color rgb="FF00509E"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF6F1E7"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="7"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;
  // a cell is a value or {v, s}: numbers stay numbers, "12.5%" becomes 0.125 shown as a percent
  function cell(ref, c) {
    let v = c, s = 0;
    if (c && typeof c === "object") { v = c.v; s = c.s || 0; }
    if (typeof v === "string" && /^-?\d+(\.\d+)?%$/.test(v.trim())) { v = parseFloat(v) / 100; s = s || 4; }
    if (typeof v === "number") {
      if (!isFinite(v)) return "";
      if (!s && !Number.isInteger(v)) s = 3;
      return `<c r="${ref}"${s ? ` s="${s}"` : ""}><v>${v}</v></c>`;
    }
    if (v === undefined || v === null || v === "" || v === "–") return s ? `<c r="${ref}" s="${s}"/>` : "";
    return `<c r="${ref}" t="inlineStr"${s ? ` s="${s}"` : ""}><is><t xml:space="preserve">${x(v)}</t></is></c>`;
  }
  function sheet({rows, widths = [], freeze}) {
    const body = rows.map((r, i) => `<row r="${i + 1}">${(r || []).map((c, j) => cell(col(j) + (i + 1), c)).join("")}</row>`).join("");
    const cols = widths.length ? `<cols>${widths.map((w, j) => `<col min="${j + 1}" max="${j + 1}" width="${w}" customWidth="1"/>`).join("")}</cols>` : "";
    const pane = freeze ? `<sheetViews><sheetView workbookViewId="0"><pane ${freeze.c ? `xSplit="${freeze.c}" ` : ""}ySplit="${freeze.r}" topLeftCell="${col(freeze.c || 0)}${freeze.r + 1}" activePane="${freeze.c ? "bottomRight" : "bottomLeft"}" state="frozen"/></sheetView></sheetViews>` : "";
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">${pane}${cols}<sheetData>${body}</sheetData></worksheet>`;
  }
  function book(sheets) {   // [{name, rows, widths, freeze}] → Uint8Array
    const names = [];
    for (const s of sheets) {   // Excel: at most 31 characters, none of []:*?/\ , unique
      let n = String(s.name).replace(/[[\]:*?/\\]/g, " ").slice(0, 31) || "Sheet", k = 2;
      while (names.includes(n)) n = n.slice(0, 28) + " " + k++;
      names.push(n);
    }
    const ws = sheets.map((s, i) => ({name: `xl/worksheets/sheet${i + 1}.xml`, text: sheet(s)}));
    return zip([
      {name: "[Content_Types].xml", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${ws.map(w => `<Override PartName="/${w.name}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join("")}</Types>`},
      {name: "_rels/.rels", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`},
      {name: "xl/workbook.xml", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>${names.map((n, i) => `<sheet name="${x(n)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("")}</sheets></workbook>`},
      {name: "xl/_rels/workbook.xml.rels", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${ws.map((w, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("")}<Relationship Id="rId${ws.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`},
      {name: "xl/styles.xml", text: STYLES},
      ...ws,
    ]);
  }
  return {book};
})();

// ---------- Riwayat run: every finished run of this model, kept in this browser ----------
const RUNLOG_MAX = 50;
const runLogKey = () => "atl.runs." + ((model.meta && model.meta.id) || "name:" + (model.name || "Model"));
function runLog() { try { return JSON.parse(localStorage.getItem(runLogKey()) || "[]"); } catch (e) { return []; } }
function runParams(m) {   // [[label, value]]: the run setup and every Scenarios control
  const run = m.run || {};
  const out = [["Replikasi", run.replications], ["Panjang replikasi", `${run.length ?? ""} ${run.length_units || ""}`.trim()],
               ["Warm-up", `${run.warmup || 0} ${run.warmup_units || ""}`.trim()]];
  for (const c of scenControls()) { let v; try { v = c.get(m); } catch (e) {} out.push([c.label, v ?? ""]); }
  return out.map(([k, v]) => [k, /^-?\d+(\.\d+)?$/.test(String(v).trim()) ? +v : String(v ?? "")]);
}
function runEntry(res) {
  const resp = scenResponses(res);
  return {
    at: new Date().toISOString(), reps: res.replications.length, stopped: !!res.stopped,
    params: runParams(res._model || model),
    resp: Object.values(resp).map(r => [r.label, r.stat.mean, r.stat.hw, r.pct ? 1 : 0]),
  };
}
function logRun(res) {
  try {
    const log = runLog(); log.push(runEntry(res));
    localStorage.setItem(runLogKey(), JSON.stringify(log.slice(-RUNLOG_MAX)));
  } catch (e) { console.warn("run log", e); }
}
{
  const _pub = publishResults;
  publishResults = function (res) { _pub(res); logRun(res); addExcelButton(); };
}

// ---------- the workbook ----------
const fmtWhen = iso => { try { return new Date(iso).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"}); } catch (e) { return iso; } };
const xHead = v => ({v, s: 2}), xBold = v => ({v, s: 1}), xPct = v => typeof v === "number" ? {v, s: 4} : v;

function sheetSummary(res) {
  const me = atlIdentity() || {}, run = model.run, rows = [];
  rows.push([{v: `Hasil Simulasi: ${model.name}`, s: 5}]);
  rows.push([xBold("Nama"), me.name || ""], [xBold("NIM"), me.nim || ""], [xBold("Kelas"), me.kelas || ""],
            [xBold("Diunduh"), fmtWhen(new Date().toISOString())], [xBold("Model ID"), (model.meta && model.meta.id) || ""],
            [xBold("Replikasi selesai"), res.replications.length], [xBold("Satuan waktu dasar"), model.time_units]);
  if (res.stopped) rows.push([xBold("Catatan"), "Run dihentikan sebelum selesai (End): hasil sampai titik itu"]);
  if (run.description) rows.push([xBold("Deskripsi"), run.description]);
  rows.push([], [{v: "Parameter", s: 6}], [xHead("Parameter"), xHead("Nilai")]);
  for (const [k, v] of runParams(res._model || model)) rows.push([k, v]);
  const n = res.replications.length;
  rows.push([], [{v: `Category Overview${n > 1 ? ` (rata-rata ${n} replikasi)` : ""}`, s: 6}]);
  for (const t of summaryData) {
    if (t.section) { rows.push([], [{v: t.section, s: 6}]); continue; }
    rows.push([xBold(t.title)], t.cols.map(xHead), ...t.rows);
  }
  return {name: "Ringkasan", rows, widths: [34, 18, 18, 18, 18, 18, 18, 18, 18]};
}
function sheetReplications(res) {
  const resp = scenResponses(res), reps = res.replications, n = reps.length;
  const rows = [[xHead("Statistik"), ...reps.map((_, i) => xHead(`Rep ${i + 1}`)), xHead("Rata-rata"), xHead("Half width 95%"), xHead("Min"), xHead("Max")]];
  for (const r of Object.values(resp)) {
    const v = r.values.map(x => typeof x === "number" && isFinite(x) ? x : undefined), ok = v.filter(x => x !== undefined);
    const f = r.pct ? xPct : (y => y);
    rows.push([r.label, ...v.map(f), f(r.stat.mean), f(r.stat.hw), f(ok.length ? Math.min(...ok) : undefined), f(ok.length ? Math.max(...ok) : undefined)]);
  }
  return {name: "Per replikasi", rows, widths: [38, ...Array(n + 4).fill(13)], freeze: {r: 1, c: 1}};
}
function sheetRunLog() {
  const log = runLog(); if (!log.length) return null;
  const pk = [], rk = [];   // parameter and response labels, in the order first seen
  for (const e of log) { for (const [k] of e.params) if (!pk.includes(k)) pk.push(k); for (const [k] of e.resp) if (!rk.includes(k)) rk.push(k); }
  const head = [xHead("Run"), xHead("Waktu"), ...pk.map(xHead), ...rk.flatMap(k => [xHead(k), xHead(`${k} ± HW`)])];
  const rows = [[{v: "Riwayat run model ini (di browser ini). Kolom parameter yang berubah dari run sebelumnya ditandai tebal.", s: 1}], head];
  log.forEach((e, i) => {
    const P = Object.fromEntries(e.params), R = Object.fromEntries(e.resp.map(r => [r[0], r]));
    const prev = i ? Object.fromEntries(log[i - 1].params) : null;
    rows.push([i + 1, fmtWhen(e.at) + (e.stopped ? " (End)" : ""),
      ...pk.map(k => prev && String(prev[k]) !== String(P[k]) ? {v: P[k], s: 1} : P[k]),
      ...rk.flatMap(k => { const r = R[k]; if (!r) return [undefined, undefined]; const f = r[3] ? xPct : (y => y); return [f(r[1] ?? undefined), f(r[2] ?? undefined)]; })]);
  });
  return {name: "Riwayat run", rows, widths: [6, 20, ...pk.map(() => 16), ...rk.flatMap(() => [16, 12])], freeze: {r: 2, c: 2}};
}
function sheetScenarios() {
  if (typeof scenRes === "undefined" || !scenRes || scenRes.modelSig !== scenSig()) return null;
  const R = scenRes, keys = Object.keys(R.rows[0].responses);
  const rows = [[xHead("Skenario"), ...R.controls.map(k => xHead(R.labels[k] || k)), xHead("Replikasi"),
    ...keys.flatMap(k => [xHead(R.rows[0].responses[k].label), xHead(`${R.rows[0].responses[k].label} ± HW`)])]];
  for (const r of R.rows) rows.push([r.name, ...R.controls.map(k => { const v = r.values[k]; return /^-?\d+(\.\d+)?$/.test(String(v).trim()) ? +v : v; }), r.reps,
    ...keys.flatMap(k => { const s = r.responses[k]; if (!s) return [undefined, undefined]; const f = s.pct ? xPct : (y => y); return [f(s.stat.mean), f(s.stat.hw)]; })]);
  return {name: "Skenario", rows, widths: [18, ...R.controls.map(() => 16), 10, ...keys.flatMap(() => [16, 12])], freeze: {r: 1, c: 1}};
}
function buildWorkbook(res) {
  return XL.book([sheetSummary(res), sheetReplications(res), sheetRunLog(), sheetScenarios()].filter(Boolean));
}
function exportExcel() {
  const res = lastResults;
  if (!res) { toast("Jalankan model sampai selesai dulu — file Excel memakai hasil run terakhir"); return; }
  const me = atlIdentity(), d = new Date(), pad = v => String(v).padStart(2, "0");
  const stamp = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}`;
  const file = `Hasil_${(model.name || "model").replace(/[^\w-]+/g, "_")}${me && me.nim ? "_" + me.nim : ""}_${stamp}.xlsx`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([buildWorkbook(res)], {type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}));
  a.download = file; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  toast("Hasil diunduh: " + file);
}
function clearRunLog() {
  const n = runLog().length;
  try { localStorage.removeItem(runLogKey()); } catch (e) {}
  toast(n ? `Riwayat ${n} run model ini dikosongkan` : "Riwayat run model ini sudah kosong");
}
function addExcelButton() {   // in the Summary, next to the model name
  const top = $("sum-top"); if (!top || top.querySelector(".xlbtn")) return;
  const b = document.createElement("button"); b.className = "xlbtn"; b.textContent = "⬇ Excel";
  b.title = "Unduh hasil ke Excel (.xlsx): ringkasan, per replikasi dan riwayat run untuk membandingkan parameter";
  b.style.cssText = "float:right;font-size:12px;padding:2px 10px"; b.onclick = exportExcel;
  top.prepend(b);
}

addMenuItem("file", {id: "mi-xlsx", label: "Hasil ke Excel (.xlsx)", sep: true, action: exportExcel});
addMenuItem("file", {id: "mi-runlog-clear", label: "Kosongkan riwayat run", action: clearRunLog});
