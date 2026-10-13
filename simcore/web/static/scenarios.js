// Scenarios: a small Process Analyzer. Each scenario sets some controls (resource capacity,
// variable initial value, time between arrivals, replications); all scenarios run as batch
// runs and the responses are compared with their 95% half widths, in a table and a chart.
// Scenarios are saved with the model (model.scenarios). Loaded after the editor script.

const T975 = [0, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086];
const tq = df => df < 1 ? NaN : df <= 20 ? T975[df] : df <= 30 ? 2.086 - (df - 20) * 0.0044 : df <= 60 ? 2.042 - (df - 30) * 0.00061 : 1.96;
function meanHw(xs) {
  const v = xs.filter(x => typeof x === "number" && isFinite(x));
  if (!v.length) return {mean: NaN, hw: NaN, n: 0};
  const m = v.reduce((a, b) => a + b, 0) / v.length;
  if (v.length < 2) return {mean: m, hw: NaN, n: 1};
  const sd = Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / (v.length - 1));
  return {mean: m, hw: tq(v.length - 1) * sd / Math.sqrt(v.length), n: v.length};
}

// ---------- controls ----------
function scenControls() {   // every control the model offers: {key, label, get(m), set(m, v)}
  const out = [];
  for (const [name, r] of Object.entries(model.data.resources))
    if (r.type !== "Based on Schedule") out.push({key: "res:" + name, label: `${name} · Capacity`,
      get: m => (m.data.resources[name] || {}).capacity, set: (m, v) => { if (m.data.resources[name]) m.data.resources[name].capacity = String(v); }});
  for (const name of Object.keys(model.data.variables || {}))
    out.push({key: "var:" + name, label: `${name} · Initial Value`,
      get: m => (m.data.variables[name] || {}).initial_values, set: (m, v) => { if (m.data.variables[name]) m.data.variables[name].initial_values = String(v); }});
  eachNode((n, fid) => {
    if (n.type === "create" && has(n.props.type, "Random (Expo)", "Constant")) {
      const find = m => { let hit = null; eachNode((x, id) => { if (id === fid) hit = x; }, m); return hit; };
      out.push({key: "create:" + fid, label: `${n.props.name} · Time Between Arrivals`,
        get: m => (find(m) || {props: {}}).props.value, set: (m, v) => { const x = find(m); if (x) x.props.value = String(v); }});
    }
  });
  return out;
}

// ---------- responses ----------
const SYS_TALLY = /\.(nva_time|va_time|wait_time|tran_time|other_time|nva_cost|va_cost|wait_cost|tran_cost|other_cost|TotalTime|TotalCost|(VA|NVA|Wait|Transfer|Other|Total)(Time|Cost)PerEntity)$/;
function scenResponses(res) {   // {key: {label, unit, values per replication}}
  const reps = res.replications, r = reps[0], out = {};
  const add = (key, label, f, pct) => { out[key] = {label, pct: !!pct, values: reps.map(x => { try { return f(x); } catch (e) { return undefined; } })}; };
  for (const k of Object.keys(r.resources)) add("util:" + k, `${k} · Utilization`, x => x.resources[k].instantaneous_utilization, true);
  for (const q of Object.keys(r.queues).filter(q => !q.startsWith("__"))) {
    add("wq:" + q, `${q} · Waiting Time`, x => x.queues[q].waiting_time.average);
    add("nq:" + q, `${q} · Number Waiting`, x => x.queues[q].number_waiting.average);
  }
  for (const t of Object.keys(r.entities.in_ || {})) {
    if (r.tallies[`${t}.TotalTime`]) add("tt:" + t, `${t} · Total Time`, x => x.tallies[`${t}.TotalTime`].average);
    add("out:" + t, `${t} · Number Out`, x => x.entities.out[t]);
  }
  for (const k of Object.keys(r.tallies).filter(k => !SYS_TALLY.test(k) && !/\.Queue\.WaitingTime$/.test(k))) add("tally:" + k, `${k} (Tally)`, x => x.tallies[k].average);
  for (const k of Object.keys(r.counters).filter(k => !/\.Number(In|Out)$/.test(k))) add("count:" + k, `${k} (Counter)`, x => x.counters[k]);
  for (const k of Object.keys(r.dstats || {})) add("tp:" + k, `${k} (Time Persistent)`, x => x.dstats[k].average);
  for (const k of Object.keys(r.outputs || {})) add("output:" + k, `${k} (Output)`, x => x.outputs[k]);
  for (const v of Object.values(out)) v.stat = meanHw(v.values);
  return out;
}
const DEFAULT_RESP = /^(util|wq|tt|count|output):/;

// ---------- state ----------
let scen = null;   // {controls: [keys], rows: [{name, values, reps}]}, a working copy while the dialog is open
let scenRes = null;   // {modelSig, rows: [{name, values, reps, responses}], shown: [keys], chart: key}
const scenSig = () => JSON.stringify([model.nodes, model.data, model.run]);
function scenInit() {
  const saved = model.scenarios;
  if (saved && saved.rows && saved.rows.length) return clone(saved);
  const ctr = scenControls().filter(c => c.key.startsWith("res:")).slice(0, 2).map(c => c.key);
  const now = scenValues(model, ctr);
  return {controls: ctr, rows: [{name: "Base", values: now, reps: String(Math.max(5, parseInt(model.run.replications) || 1))}]};
}
function scenValues(m, keys) {
  const all = Object.fromEntries(scenControls().map(c => [c.key, c])), o = {};
  for (const k of keys) if (all[k]) o[k] = String(all[k].get(m) ?? "");
  return o;
}

// ---------- dialog ----------
const sDlg = document.createElement("div");
sDlg.className = "dlg"; sDlg.id = "scendlg"; sDlg.hidden = true;
sDlg.setAttribute("role", "dialog"); sDlg.setAttribute("aria-modal", "true"); sDlg.setAttribute("aria-labelledby", "scentitle");
sDlg.innerHTML = `<div class="dlgbox wide">
  <h3 id="scentitle">Scenarios (Process Analyzer)</h3>
  <p class="hint">Bandingkan beberapa skenario: pilih <b>control</b> yang diubah, isi nilainya per skenario, lalu <b>Run semua</b>. Setiap skenario dijalankan sebagai batch run (tanpa animasi) dengan jumlah replikasinya sendiri; hasil ditampilkan sebagai rata-rata ± half width 95%.</p>
  <details id="scenctl"><summary><b>Controls</b> (yang diubah antar skenario)</summary><div id="scenctllist" class="scenchecks"></div></details>
  <div style="overflow:auto"><table class="res" id="scentable"></table></div>
  <div class="dlgbtns" style="justify-content:flex-start"><button id="scenadd">+ Skenario</button><span style="flex:1"></span><span id="scenstatus" class="hint"></span><button id="scenrun" class="primary">▶ Run semua</button></div>
  <div id="scenout"></div>
  <div class="dlgbtns"><button id="scenclose" class="primary">Tutup</button></div>
</div>`;
document.body.appendChild(sDlg);
const sStyle = document.createElement("style");
sStyle.textContent = `.scenchecks { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 2px 12px; padding: 6px 0; font-size: 12.5px; }
.scenchecks label { display: flex; gap: 6px; align-items: center; }
#scentable input { width: 90px; } #scentable input.sname { width: 120px; }
#scentable td, #scentable th { white-space: nowrap; }
.scenbest { font-weight: 700; color: var(--accent); }
.scenchart { max-width: 720px; } .scenchart svg { width: 100%; height: auto; display: block; }
#scenout h4 { margin: 14px 0 4px; font-size: 13px; }`;
document.head.appendChild(sStyle);

function openScenarios() {
  if (typeof anim !== "undefined" && anim) { toast("Selesaikan atau End animasi dulu"); return; }
  scen = scenInit(); sDlg.hidden = false; renderScen();
  if (scenRes && scenRes.modelSig === scenSig()) renderScenOut(); else $("scenout").innerHTML = "";
}
function saveScen() { model.scenarios = clone(scen); markDirty(); }
function renderScen() {
  const ctrls = scenControls(), byKey = Object.fromEntries(ctrls.map(c => [c.key, c]));
  scen.controls = scen.controls.filter(k => byKey[k]);
  $("scenctllist").innerHTML = ctrls.length ? "" : '<span class="hint">Model ini belum punya control: tambahkan Resource berkapasitas tetap, Variable, atau Create Random/Constant.</span>';
  for (const c of ctrls) {
    const l = document.createElement("label"), cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = scen.controls.includes(c.key);
    cb.onchange = () => {
      if (cb.checked) { scen.controls.push(c.key); for (const r of scen.rows) r.values[c.key] ??= String(c.get(model) ?? ""); }
      else scen.controls = scen.controls.filter(k => k !== c.key);
      saveScen(); renderScen();
    };
    l.append(cb, document.createTextNode(c.label)); $("scenctllist").appendChild(l);
  }
  const t = $("scentable");
  t.innerHTML = `<tr><th>Skenario</th>${scen.controls.map(k => `<th>${esc(byKey[k].label)}</th>`).join("")}<th>Replications</th><th></th></tr>`;
  scen.rows.forEach((row, i) => {
    const tr = document.createElement("tr");
    const cell = (val, set, cls, aria) => { const td = document.createElement("td"), inp = document.createElement("input"); inp.value = val ?? ""; if (cls) inp.className = cls; inp.setAttribute("aria-label", aria); inp.oninput = () => { set(inp.value); saveScen(); }; td.appendChild(inp); tr.appendChild(td); };
    cell(row.name, v => row.name = v, "sname", `Skenario ${i + 1} nama`);
    for (const k of scen.controls) cell(row.values[k] ?? String(byKey[k].get(model) ?? ""), v => row.values[k] = v, "", `Skenario ${i + 1} ${byKey[k].label}`);
    cell(row.reps, v => row.reps = v, "", `Skenario ${i + 1} replications`);
    const td = document.createElement("td");
    const b = (txt, title, fn) => { const x = document.createElement("button"); x.textContent = txt; x.title = title; x.setAttribute("aria-label", title); x.onclick = fn; td.appendChild(x); };
    b("⧉", `Duplikat skenario ${i + 1}`, () => { scen.rows.splice(i + 1, 0, {...clone(row), name: row.name + " (2)"}); saveScen(); renderScen(); });
    b("↧", `Terapkan skenario ${i + 1} ke model`, () => applyScenario(row));
    if (scen.rows.length > 1) b("✕", `Hapus skenario ${i + 1}`, () => { scen.rows.splice(i, 1); saveScen(); renderScen(); });
    tr.appendChild(td); t.appendChild(tr);
  });
  $("scenctl").open = !scen.controls.length;
}
function applyScenario(row) {
  const all = Object.fromEntries(scenControls().map(c => [c.key, c]));
  change(() => { for (const k of scen.controls) if (all[k] && row.values[k] !== undefined) all[k].set(model, row.values[k]); });
  toast(`Nilai skenario "${row.name}" diterapkan ke model`);
}
$("scenadd").onclick = () => {
  const last = scen.rows[scen.rows.length - 1];
  scen.rows.push({name: `Skenario ${scen.rows.length + 1}`, values: clone(last.values), reps: last.reps});
  saveScen(); renderScen();
};
$("scenclose").onclick = () => { sDlg.hidden = true; };
sDlg.addEventListener("keydown", ev => { if (ev.key === "Escape" && !scenBusy) sDlg.hidden = true; });

let scenBusy = false;
async function runScenarios() {
  if (scenBusy) return;
  scenBusy = true; $("scenrun").disabled = true;
  const all = Object.fromEntries(scenControls().map(c => [c.key, c]));
  const out = [];
  try {
    for (const [i, row] of scen.rows.entries()) {
      $("scenstatus").textContent = `Menjalankan "${row.name}" (${i + 1}/${scen.rows.length})…`;
      const m = clone(model);
      for (const k of scen.controls) if (all[k]) all[k].set(m, row.values[k]);
      m.run.batch_run = true; m.run.replications = String(parseInt(row.reps) || 1);
      delete m.scenarios;
      let res;
      try { res = await api("POST", "/api/run", m); }
      catch (e) { $("scenstatus").textContent = `"${row.name}": ${e.message}`; showProblems(e); return; }
      out.push({name: row.name, values: clone(row.values), reps: res.replications.length, responses: scenResponses(res)});
    }
    const keys = Object.keys(out[0].responses);
    const keep = scenRes && scenRes.shown ? scenRes.shown.filter(k => keys.includes(k)) : [];
    scenRes = {modelSig: scenSig(), controls: [...scen.controls], labels: Object.fromEntries(scenControls().map(c => [c.key, c.label])), rows: out,
               shown: keep.length ? keep : keys.filter(k => DEFAULT_RESP.test(k)).slice(0, 6), chart: null};
    scenRes.chart = scenRes.shown[0] || keys[0];
    $("scenstatus").textContent = `Selesai: ${out.length} skenario`;
    renderScenOut();
  } finally { scenBusy = false; $("scenrun").disabled = false; }
}
$("scenrun").onclick = runScenarios;

const sfmt = (v, pct) => typeof v !== "number" || !isFinite(v) ? "–" : pct ? (v * 100).toFixed(1) + "%" : fmt(v);
function scenTableHtml(R) {
  const head = `<tr><th>Skenario</th>${R.controls.map(k => `<th>${esc(R.labels[k] || k)}</th>`).join("")}<th>Rep</th>${R.shown.map(k => `<th>${esc(R.rows[0].responses[k]?.label || k)}</th>`).join("")}</tr>`;
  const best = {};
  for (const k of R.shown) {   // the lowest wait/time/queue and the highest output/count are marked
    const vals = R.rows.map(r => r.responses[k]?.stat.mean);
    if (R.rows.length < 2 || vals.some(v => typeof v !== "number")) continue;
    const hi = /^(out|count|output):/.test(k), lo = /^(wq|nq|tt):/.test(k);
    if (hi) best[k] = vals.indexOf(Math.max(...vals)); else if (lo) best[k] = vals.indexOf(Math.min(...vals));
  }
  const body = R.rows.map((r, i) => `<tr><td>${esc(r.name)}</td>${R.controls.map(k => `<td>${esc(r.values[k] ?? "")}</td>`).join("")}<td>${r.reps}</td>${R.shown.map(k => {
    const s = r.responses[k]; if (!s) return "<td>–</td>";
    const hw = isFinite(s.stat.hw) ? ` ± ${sfmt(s.stat.hw, s.pct)}` : "";
    return `<td${best[k] === i ? ' class="scenbest" title="terbaik"' : ""}>${sfmt(s.stat.mean, s.pct)}${hw}</td>`;
  }).join("")}</tr>`).join("");
  return `<table class="res">${head}${body}</table>`;
}
function scenChartSvg(R, key) {   // horizontal bars with 95% half-width whiskers
  const rows = R.rows.map(r => ({name: r.name, s: r.responses[key]})).filter(r => r.s);
  if (!rows.length) return "";
  const pct = rows[0].s.pct, bh = 22, gap = 10, left = 150, w = 520, h = rows.length * (bh + gap) + 30;
  const max = Math.max(...rows.map(r => (r.s.stat.mean || 0) + (isFinite(r.s.stat.hw) ? r.s.stat.hw : 0)), 1e-9);
  const x = v => left + (Math.max(0, v) / max) * (w - left - 70);
  let g = "";
  rows.forEach((r, i) => {
    const y = 10 + i * (bh + gap), m = r.s.stat.mean, hw = r.s.stat.hw;
    g += `<text x="${left - 8}" y="${y + bh / 2 + 4}" text-anchor="end" font-size="12" fill="currentColor">${esc(r.name)}</text>`;
    g += `<rect x="${left}" y="${y}" width="${Math.max(0, x(m) - left)}" height="${bh}" fill="#0072ce" opacity=".85"/>`;
    if (isFinite(hw)) g += `<path d="M${x(m - hw)},${y + bh / 2}H${x(m + hw)}M${x(m - hw)},${y + 5}V${y + bh - 5}M${x(m + hw)},${y + 5}V${y + bh - 5}" stroke="#ffc800" stroke-width="2.5"/>`;
    g += `<text x="${x(isFinite(hw) ? m + hw : m) + 6}" y="${y + bh / 2 + 4}" font-size="12" fill="currentColor">${sfmt(m, pct)}</text>`;
  });
  g += `<line x1="${left}" x2="${left}" y1="4" y2="${h - 22}" stroke="#98a2b3"/>`;
  g += `<text x="${left}" y="${h - 6}" font-size="11" fill="#667085">garis kuning: selang kepercayaan 95% (rata-rata ± half width)</text>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(rows[0].s.label)} per skenario">${g}</svg>`;
}
function renderScenOut() {
  const R = scenRes, o = $("scenout"); if (!R) { o.innerHTML = ""; return; }
  const keys = Object.keys(R.rows[0].responses);
  o.innerHTML = `<h4>Hasil</h4>${scenTableHtml(R)}
    <details><summary>Pilih response yang ditampilkan</summary><div class="scenchecks" id="scenresp"></div></details>
    <h4>Grafik: <select id="scenchartsel" aria-label="Response di grafik"></select></h4><div class="scenchart">${scenChartSvg(R, R.chart)}</div>
    <p class="hint">Jika selang kepercayaan (garis kuning) dua skenario <b>tidak bertumpuk</b>, perbedaannya cukup meyakinkan. Jika bertumpuk, tambah replikasi sebelum menyimpulkan. Warna biru tebal di tabel = nilai terbaik (waktu/antrean terkecil, output terbesar).</p>`;
  for (const k of keys) {
    const l = document.createElement("label"), cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = R.shown.includes(k);
    cb.onchange = () => { R.shown = cb.checked ? [...R.shown, k] : R.shown.filter(x => x !== k); renderScenOut(); };
    l.append(cb, document.createTextNode(R.rows[0].responses[k].label)); $("scenresp").appendChild(l);
    const op = document.createElement("option"); op.value = k; op.textContent = R.rows[0].responses[k].label; $("scenchartsel").appendChild(op);
  }
  $("scenchartsel").value = R.chart;
  $("scenchartsel").onchange = () => { R.chart = $("scenchartsel").value; renderScenOut(); };
}
function scenarioReportHtml() {   // for the report (report.js)
  if (!scenRes || scenRes.modelSig !== scenSig()) return "";
  const charts = scenRes.shown.map(k => `<h3>${esc(scenRes.rows[0].responses[k].label)}</h3><div class="chart">${scenChartSvg(scenRes, k)}</div>`).join("");
  return `<h2>Perbandingan skenario</h2>${scenTableHtml(scenRes)}${charts}`;
}

addMenuItem("tools", {id: "mi-scen", label: "Scenarios (Process Analyzer)…", action: () => openScenarios()});
