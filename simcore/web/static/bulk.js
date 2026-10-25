// Periksa banyak laporan (lecturer): check a whole class's reports at once. Takes report
// .html files, a folder, or the .zip an LMS gives for "download all submissions", checks each
// verification code, and lists the reports with what needs a closer look:
//  - code mismatch (the report was edited after it was made) or not a report at all;
//  - the same Model ID handed in under different NIMs (one model file, several students);
//  - the same module layout (positions and names) under different NIMs and Model IDs;
//  - other NIMs in the model's author history; several reports from one NIM.
// The table exports to CSV for the grade sheet; a row opens the single-report check.
(function () {
  const dlg = document.createElement("div");
  dlg.className = "dlg"; dlg.hidden = true; dlg.id = "bulkdlg";
  dlg.setAttribute("role", "dialog"); dlg.setAttribute("aria-modal", "true"); dlg.setAttribute("aria-labelledby", "bulktitle");
  dlg.innerHTML = `<div class="dlgbox wide"><h3 id="bulktitle">Periksa banyak laporan</h3>
    <div id="bulkdrop" tabindex="0" role="button" aria-label="Pilih file laporan">
      <b>Seret file laporan (.html) atau .zip ke sini</b><br>
      <span class="hint">atau</span> <button id="bulkfiles">Pilih file…</button> <button id="bulkfolder">Pilih folder…</button>
      <div class="hint">File .zip dari LMS ("download all submissions") bisa langsung dimasukkan. Semua diperiksa di browser ini; tidak ada yang diunggah.</div>
    </div>
    <div id="bulkbar" hidden><span id="bulkstat"></span><span style="flex:1"></span>
      <label><input type="checkbox" id="bulkonly"> Hanya yang perlu dicek</label>
      <button id="bulkcsv">Unduh CSV</button><button id="bulkclear">Kosongkan</button></div>
    <div id="bulkout"></div>
    <div class="dlgbtns"><button id="bulkclose" class="primary">Tutup</button></div></div>`;
  document.body.appendChild(dlg);
  const pick = (dir) => { const i = document.createElement("input"); i.type = "file"; i.multiple = true; if (dir) i.webkitdirectory = true; else i.accept = ".html,.htm,.zip"; i.onchange = () => add([...i.files]); i.click(); };
  const st = document.createElement("style");
  st.textContent = `#bulkdrop { border: 2px dashed var(--line); border-radius: 10px; padding: 16px; text-align: center; margin-bottom: 10px; }
  #bulkdrop.over { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, transparent); }
  #bulkbar { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
  #bulkbar[hidden] { display: none; }
  #bulkout { max-height: 55vh; overflow: auto; }
  #bulkout table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
  #bulkout th, #bulkout td { border-bottom: 1px solid var(--line); padding: 4px 6px; text-align: left; vertical-align: top; }
  #bulkout th { position: sticky; top: 0; background: var(--panel); cursor: pointer; white-space: nowrap; }
  #bulkout tr.row { cursor: pointer; }
  #bulkout tr.row:hover td { background: color-mix(in srgb, var(--accent) 7%, transparent); }
  #bulkout tr.bad td:first-child { box-shadow: inset 3px 0 var(--err); }
  #bulkout tr.warn td:first-child { box-shadow: inset 3px 0 var(--warn); }
  #bulkout .flags { color: var(--warn); }
  #bulkout tr.bad .flags { color: var(--err); }`;
  document.head.appendChild(st);

  let items = [], sortKey = "nim", sortDir = 1;
  const drop = $("bulkdrop");
  $("bulkfiles").onclick = ev => { ev.stopPropagation(); pick(false); };
  $("bulkfolder").onclick = ev => { ev.stopPropagation(); pick(true); };
  drop.onclick = () => pick(false);
  drop.onkeydown = ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(false); } };
  drop.ondragover = ev => { ev.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = ev => { ev.preventDefault(); drop.classList.remove("over"); add([...ev.dataTransfer.files]); };
  $("bulkclose").onclick = () => { dlg.hidden = true; };
  dlg.addEventListener("keydown", ev => { if (ev.key === "Escape") dlg.hidden = true; });
  $("vopen").addEventListener("click", () => { dlg.hidden = true; });   // the model from a report replaces the one in the editor
  $("bulkclear").onclick = () => { items = []; show(); };
  $("bulkonly").onchange = () => show();
  $("bulkcsv").onclick = () => download(`Periksa_laporan_${new Date().toISOString().slice(0, 10)}.csv`, "﻿" + csv(), "text/csv");

  // ---------- reading files, including .zip archives (stored or deflated entries) ----------
  async function unzip(file) {
    const buf = new Uint8Array(await file.arrayBuffer()), dv = new DataView(buf.buffer);
    let eocd = -1;
    for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) throw new Error("bukan file zip");
    const n = dv.getUint16(eocd + 10, true);
    let p = dv.getUint32(eocd + 16, true);
    const out = [];
    for (let k = 0; k < n && dv.getUint32(p, true) === 0x02014b50; k++) {
      const method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true);
      const nl = dv.getUint16(p + 28, true), el = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), off = dv.getUint32(p + 42, true);
      const name = new TextDecoder().decode(buf.subarray(p + 46, p + 46 + nl));
      p += 46 + nl + el + cl;
      if (name.endsWith("/")) continue;
      const lo = off + 30 + dv.getUint16(off + 26, true) + dv.getUint16(off + 28, true), raw = buf.subarray(lo, lo + size);
      out.push({name, read: async () => {
        if (method === 0) return new TextDecoder().decode(raw);
        if (method !== 8) throw new Error("kompresi zip tidak didukung");
        return await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream("deflate-raw"))).text();
      }});
    }
    return out;
  }
  async function add(files) {
    $("bulkstat").textContent = "Membaca…"; $("bulkbar").hidden = false;
    for (const f of files) {
      const name = f.webkitRelativePath || f.name;
      if (/\.zip$/i.test(f.name)) {
        try { for (const e of await unzip(f)) if (/\.html?$/i.test(e.name)) items.push(check(`${f.name} › ${e.name}`, await e.read().catch(() => ""))); }
        catch (e) { items.push({file: name, ok: false, why: "File zip tidak bisa dibaca: " + e.message}); }
      } else if (/\.html?$/i.test(f.name)) items.push(check(name, await f.text()));
    }
    analyse(); show();
  }
  function layoutKey(m) {   // where each module sits and what it is called — rarely identical by chance
    const nodes = [];
    const walk = (g, pre) => { for (const n of (g && g.nodes) || []) { nodes.push(`${pre}${n.type}:${(n.props || {}).name || ""}@${Math.round(n.x)},${Math.round(n.y)}`); if (n.sub) walk(n.sub, pre + n.id + "/"); } };
    walk(m, "");
    return nodes.length >= 3 ? nodes.sort().join("|") : "";
  }
  function check(file, html) {
    const r = verifyReport(html);
    if (!r.p) return {file, ok: false, why: r.why, html};
    const p = r.p, me = p.identity || {}, meta = (p.model && p.model.meta) || {};
    return {file, html, ok: r.ok, report: true, name: me.name || "", nim: String(me.nim || ""), kelas: me.kelas || "", created: p.created || "",
            model: (p.model && p.model.name) || "", mid: meta.id || "", code: r.code, layout: layoutKey(p.model),
            authors: (meta.authors || []).map(a => String(a.nim || "")), reps: ((p.model || {}).run || {}).replications ?? ""};
  }
  function analyse() {
    const group = key => { const m = new Map(); for (const it of items) if (it.report && key(it)) (m.get(key(it)) || m.set(key(it), []).get(key(it))).push(it); return m; };
    const byMid = group(it => it.mid), byLayout = group(it => it.layout), byNim = group(it => it.nim);
    for (const it of items) {
      it.flags = []; it.level = "";
      if (!it.report) { it.flags.push(it.why); it.level = "bad"; continue; }
      if (!it.ok) { it.flags.push("Kode tidak cocok: isi laporan diubah setelah dibuat"); it.level = "bad"; }
      const nims = list => [...new Set(list.map(x => x.nim).filter(n => n !== it.nim))];
      const sameMid = nims(byMid.get(it.mid) || []);
      if (sameMid.length) it.flags.push(`Model ID sama dengan NIM ${sameMid.join(", ")}`);
      const sameLayout = nims((byLayout.get(it.layout) || []).filter(x => x.mid !== it.mid));
      if (sameLayout.length) it.flags.push(`Tata letak model identik dengan NIM ${sameLayout.join(", ")}`);
      const hist = [...new Set(it.authors.filter(n => n && n !== it.nim))];
      if (hist.length) it.flags.push(`Riwayat penulis memuat NIM ${hist.join(", ")}`);
      if ((byNim.get(it.nim) || []).length > 1) it.flags.push(`${byNim.get(it.nim).length} laporan dari NIM ini`);
      if (!it.level && it.flags.length) it.level = "warn";
    }
  }

  // ---------- the table ----------
  const COLS = [["no", "#"], ["nim", "NIM"], ["name", "Nama"], ["kelas", "Kelas"], ["created", "Dibuat"], ["model", "Model"], ["mid", "Model ID"], ["reps", "Replikasi"], ["status", "Kode"], ["flags", "Perlu dicek"], ["file", "File"]];
  const statusOf = it => !it.report ? "✖ bukan laporan" : it.ok ? "✅ cocok" : "❌ tidak cocok";
  const val = (it, k) => k === "status" ? statusOf(it) : k === "flags" ? it.flags.join("; ") : k === "created" ? (it.created || "") : String(it[k] ?? "");
  function rows() {
    const r = items.map((it, i) => ({it, i}));
    r.sort((a, b) => sortKey === "no" ? (a.i - b.i) * sortDir : val(a.it, sortKey).localeCompare(val(b.it, sortKey), "id", {numeric: true}) * sortDir || a.i - b.i);
    return $("bulkonly").checked ? r.filter(x => x.it.level) : r;
  }
  function show() {
    const n = items.length, bad = items.filter(x => x.level === "bad").length, warn = items.filter(x => x.level === "warn").length;
    $("bulkbar").hidden = !n;
    $("bulkstat").innerHTML = n ? `<b>${n}</b> file · <span style="color:var(--err)">${bad} bermasalah</span> · <span style="color:var(--warn)">${warn} perlu dicek</span> · ${n - bad - warn} aman` : "";
    if (!n) { $("bulkout").innerHTML = ""; return; }
    const head = COLS.map(([k, t]) => `<th data-k="${k}" aria-sort="${sortKey === k ? (sortDir > 0 ? "ascending" : "descending") : "none"}">${t}${sortKey === k ? (sortDir > 0 ? " ▲" : " ▼") : ""}</th>`).join("");
    const body = rows().map(({it, i}) => `<tr class="row ${it.level}" data-i="${i}" tabindex="0">${COLS.map(([k]) =>
      k === "no" ? `<td>${i + 1}</td>` : k === "created" ? `<td>${it.created ? esc(fmtDate(it.created)) : ""}</td>` : k === "flags" ? `<td class="flags">${it.flags.map(esc).join("<br>")}</td>` : `<td>${esc(val(it, k))}</td>`).join("")}</tr>`).join("");
    $("bulkout").innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
      <p class="hint">Klik baris untuk melihat detail dan membuka modelnya. "Perlu dicek" bukan bukti menyalin: kerja kelompok atau model awal dari dosen juga bisa membuat Model ID atau tata letak sama.</p>`;
    for (const th of $("bulkout").querySelectorAll("th")) th.onclick = () => { sortDir = sortKey === th.dataset.k ? -sortDir : 1; sortKey = th.dataset.k; show(); };
    for (const tr of $("bulkout").querySelectorAll("tr.row")) {
      const open = () => { const it = items[+tr.dataset.i]; document.body.appendChild($("vbody").closest(".dlg")); showVerify(it.file, it.html || ""); };   // on top of this dialog
      tr.onclick = open; tr.onkeydown = ev => { if (ev.key === "Enter") open(); };
    }
  }
  function csv() {
    const q = v => /[",\n;]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
    const cols = COLS.filter(([k]) => k !== "no");
    return [cols.map(c => c[1]).join(","), ...rows().map(({it}) => cols.map(([k]) => q(k === "created" && it.created ? fmtDate(it.created) : val(it, k))).join(","))].join("\n");
  }

  addMenuItem("file", {id: "mi-bulk", label: "Periksa banyak laporan…", action: () => { dlg.hidden = false; drop.focus(); }});
  window.openBulkCheck = () => { dlg.hidden = false; };
})();
