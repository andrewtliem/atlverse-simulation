// Expression Builder, as Arena's (right-click > Build Expression): every expression field
// gets an ƒx button (or right-click) that opens a dialog listing distributions, the model's
// own variables, attributes, resources, queues, … and functions, each with a small form.
// DISC and CONT are built from a table of values and probabilities, so students do not
// have to work out cumulative probabilities by hand. Loaded after the editor script.
(function () {
  const num = v => { const s = String(v).trim(); return s === "" ? "" : s; };
  const recordNames = type => allNodes().filter(n => n.type === "record" && (type ? type(n.props) : true)).map(n => n.props.name);
  const model_ = {   // names in the current model
    variables: () => [...new Set([...Object.keys(model.data.variables || {}), ...allNodes().flatMap(n => n.type === "assign" ? (n.props.assignments || []).filter(a => a.type === "Variable").map(a => a.variable) : [])])].filter(Boolean),
    attributes: () => [...new Set([...Object.keys(model.data.attributes || {}), ...allNodes().flatMap(n => n.type === "assign" ? (n.props.assignments || []).filter(a => a.type === "Attribute").map(a => a.attribute) : [])])].filter(Boolean),
    expressions: () => Object.keys(model.data.expressions || {}),
    resources: () => refOptions("resources"),
    queues: () => refOptions("queues"),
    schedules: () => refOptions("schedules"),
    sets: () => refOptions("sets"),
    entities: () => refOptions("entities"),
    counters: () => recordNames(p => !p.type || p.type === "Count"),
    tallies: () => recordNames(p => p.type && p.type !== "Count"),
  };
  // item: {name, desc, params: [{label, def, list: () => names}], make(values) → text}
  const fn = (name, desc, params, make) => ({name, desc, params, make: make || (v => `${name}(${v.join(", ")})`)});
  const P = (label, def = "", list) => ({label, def, list});
  const stream = P("Stream (opsional)", "");
  const dist = (name, desc, params) => fn(name, desc, [...params, stream], v => { const s = v.pop(); return `${name}(${[...v, ...(s ? [s] : [])].join(", ")})`; });
  const CATS = [
    ["Distribusi", () => [
      dist("EXPO", "Eksponensial: waktu antar-kedatangan acak (kedatangan Poisson). Rata-rata = Mean.", [P("Mean", "5")]),
      dist("TRIA", "Triangular: waktu proses dengan nilai terkecil, paling sering, dan terbesar.", [P("Min", "2"), P("Mode (paling sering)", "4"), P("Max", "7")]),
      dist("UNIF", "Uniform: semua nilai antara Min dan Max sama mungkinnya.", [P("Min", "1"), P("Max", "3")]),
      dist("NORM", "Normal: simetris di sekitar Mean. Hati-hati, bisa bernilai negatif.", [P("Mean", "10"), P("Std Dev", "2")]),
      dist("LOGN", "Lognormal: miring ke kanan, selalu positif. Parameter adalah mean dan std dev dari nilainya.", [P("Log Mean", "10"), P("Log Std", "3")]),
      dist("GAMM", "Gamma: GAMM(Beta = skala, Alpha = bentuk); rata-rata = Beta × Alpha.", [P("Beta (skala)", "2"), P("Alpha (bentuk)", "3")]),
      dist("ERLA", "Erlang: jumlah k tahap eksponensial; rata-rata = ExpoMean × k.", [P("ExpoMean", "2"), P("k", "3")]),
      dist("WEIB", "Weibull: sering untuk waktu antar-kerusakan. WEIB(Beta = skala, Alpha = bentuk).", [P("Beta (skala)", "10"), P("Alpha (bentuk)", "2")]),
      dist("BETA", "Beta: nilai antara 0 dan 1. Kalikan untuk rentang lain, mis. 2 + 6 * BETA(…).", [P("Beta", "2"), P("Alpha", "3")]),
      dist("POIS", "Poisson: jumlah kejadian (bilangan bulat) dengan rata-rata Mean.", [P("Mean", "4")]),
      {name: "DISC", desc: "Discrete: beberapa nilai tertentu, masing-masing dengan peluangnya. Isi tabel; peluang kumulatif dihitung otomatis.", table: "disc"},
      {name: "CONT", desc: "Continuous (empiris): nilai acak di dalam interval, dengan peluang tiap interval. Isi tabel; peluang kumulatif dihitung otomatis.", table: "cont"},
    ]],
    ["Variable & Attribute", () => [
      ...model_.variables().map(n => fn(n, "Variable (global): satu nilai untuk seluruh model.", [], () => n)),
      ...model_.attributes().map(n => fn(n, "Attribute: nilai milik entity yang sedang lewat.", [], () => n)),
      ...model_.expressions().map(n => fn(n, `Expression dari data module Expression: ${(model.data.expressions[n] || {}).expression || ""}`, [], () => n)),
    ]],
    ["Resource", () => [
      fn("NR", "Jumlah unit resource yang sedang sibuk.", [P("Resource", "", model_.resources)]),
      fn("MR", "Kapasitas resource saat ini.", [P("Resource", "", model_.resources)]),
      fn("STATE", "Status resource (IDLE, BUSY, FAILED, INACTIVE). Contoh: STATE(Teller) == BUSY", [P("Resource", "", model_.resources)]),
      fn("IRF", "1 jika resource sedang rusak (failed), 0 jika tidak.", [P("Resource", "", model_.resources)]),
      fn("RESUTIL", "Utilisasi resource sejauh ini.", [P("Resource", "", model_.resources)]),
      fn("NUMMEM", "Jumlah anggota sebuah set.", [P("Set", "", model_.sets)]),
      fn("MEMBER", "Anggota ke-i dari sebuah set.", [P("Set", "", model_.sets), P("Index", "1")]),
    ]],
    ["Antrean", () => [
      fn("NQ", "Jumlah entity yang sedang menunggu di antrean.", [P("Queue", "", model_.queues)]),
      fn("AQUE", "Nilai atribut entity pada urutan ke-Rank di antrean.", [P("Queue", "", model_.queues), P("Rank", "1"), P("Attribute", "", model_.attributes)]),
    ]],
    ["Statistik", () => [
      fn("NC", "Nilai counter (dari Record tipe Count).", [P("Counter", "", model_.counters)]),
      fn("TAVG", "Rata-rata tally sejauh ini (dari Record).", [P("Tally", "", model_.tallies)]),
      fn("TNUM", "Jumlah observasi tally.", [P("Tally", "", model_.tallies)]),
      fn("EntitiesIn", "Jumlah entity bertipe ini yang sudah masuk sistem.", [P("Entity Type", "", model_.entities)], v => `EntitiesIn(${v[0]})`),
      fn("EntitiesWIP", "Jumlah entity bertipe ini yang sedang di sistem.", [P("Entity Type", "", model_.entities)], v => `EntitiesWIP(${v[0]})`),
      fn("SchedValue", "Nilai schedule saat ini (mis. kapasitas atau laju kedatangan).", [P("Schedule", "", model_.schedules)]),
    ]],
    ["Waktu & entity", () => [
      fn("TNOW", "Waktu simulasi sekarang.", [], () => "TNOW"),
      fn("TFIN", "Waktu akhir replikasi.", [], () => "TFIN"),
      fn("NREP", "Nomor replikasi yang sedang berjalan.", [], () => "NREP"),
      fn("MREP", "Jumlah replikasi.", [], () => "MREP"),
      fn("Entity.Type", "Tipe entity yang sedang lewat. Contoh: Entity.Type == Pasien", [], () => "Entity.Type"),
      fn("Entity.CreateTime", "Waktu entity dibuat. TNOW - Entity.CreateTime = lama di sistem.", [], () => "Entity.CreateTime"),
      fn("Entity.SerialNumber", "Nomor seri entity.", [], () => "Entity.SerialNumber"),
      fn("IDENT", "Nomor entity (unik).", [], () => "IDENT"),
    ]],
    ["Matematika", () => [
      fn("MN", "Nilai terkecil dari dua angka.", [P("a"), P("b")]),
      fn("MX", "Nilai terbesar dari dua angka.", [P("a"), P("b")]),
      fn("ABS", "Nilai mutlak.", [P("x")]), fn("SQRT", "Akar kuadrat.", [P("x")]),
      fn("INT", "Bagian bulat (dibulatkan ke bawah menuju nol).", [P("x")]), fn("NINT", "Dibulatkan ke bilangan bulat terdekat.", [P("x")]),
      fn("MOD", "Sisa pembagian a dibagi b.", [P("a"), P("b")]),
      fn("EXP", "e pangkat x.", [P("x")]), fn("LN", "Logaritma natural.", [P("x")]), fn("LOG", "Logaritma basis 10.", [P("x")]),
    ]],
    ["Operator", () => [
      ...[["+", "tambah"], ["-", "kurang"], ["*", "kali"], ["/", "bagi"], ["^", "pangkat"], ["(", "kurung buka"], [")", "kurung tutup"],
          ["==", "sama dengan"], ["<>", "tidak sama dengan"], ["<", "kurang dari"], ["<=", "kurang dari atau sama"], [">", "lebih dari"], [">=", "lebih dari atau sama"],
          ["&&", "dan"], ["||", "atau"]].map(([o, d]) => fn(o, `Operator: ${d}.`, [], () => ` ${o} `)),
    ]],
  ];

  const dlg = document.createElement("div");
  dlg.className = "dlg"; dlg.id = "xbdlg"; dlg.hidden = true;
  dlg.setAttribute("role", "dialog"); dlg.setAttribute("aria-modal", "true"); dlg.setAttribute("aria-labelledby", "xbtitle");
  dlg.innerHTML = `<div class="dlgbox wide">
    <h3 id="xbtitle">Expression Builder</h3>
    <div class="xbgrid">
      <div class="xbcats" id="xbcats" role="tablist" aria-label="Kategori"></div>
      <div class="xbitems" id="xbitems" aria-label="Daftar"></div>
      <div class="xbform" id="xbform"><p class="hint">Pilih kategori di kiri, lalu salah satu item.</p></div>
    </div>
    <label for="xbexpr" class="xblabel">Current Expression</label>
    <textarea id="xbexpr" rows="2" spellcheck="false"></textarea>
    <div id="xbmsg" class="hint"></div>
    <div class="dlgbtns"><button id="xbclear">Kosongkan</button><span style="flex:1"></span><button id="xbok" class="primary">OK</button><button id="xbcancel">Batal</button></div>
  </div>`;
  document.body.appendChild(dlg);
  const st = document.createElement("style");
  st.textContent = `.xbwrap { position: relative; display: block; }
  .xbwrap > input.expr { width: 100%; box-sizing: border-box; padding-right: 30px; }
  .xbbtn { position: absolute; right: 2px; top: 50%; transform: translateY(-50%); border: 0; background: none; padding: 1px 5px; font: italic 600 12px Georgia, serif; color: var(--accent); cursor: pointer; border-radius: 4px; }
  .xbbtn:hover { background: color-mix(in srgb, var(--accent) 14%, var(--panel)); }
  .xbgrid { display: grid; grid-template-columns: 170px 210px 1fr; gap: 10px; min-height: 280px; }
  @media (max-width: 760px) { .xbgrid { grid-template-columns: 1fr; } }
  .xbcats, .xbitems { display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 6px; overflow: auto; max-height: 340px; }
  .xbcats button, .xbitems button { border: 0; border-bottom: 1px solid var(--line); border-radius: 0; text-align: left; background: none; padding: 6px 9px; }
  .xbcats button.on, .xbitems button.on { background: color-mix(in srgb, var(--accent) 14%, var(--panel)); font-weight: 600; }
  .xbitems button code { font-size: 12.5px; }
  .xbform { border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; overflow: auto; max-height: 340px; display: flex; flex-direction: column; gap: 6px; }
  .xbform .xbrow { display: grid; grid-template-columns: 130px 1fr; gap: 6px; align-items: center; }
  .xbform table { border-collapse: collapse; font-size: 12.5px; } .xbform td, .xbform th { padding: 2px 4px; }
  .xbform td input { width: 80px; }
  .xbpreview { font-family: ui-monospace, monospace; background: var(--bg); border: 1px solid var(--line); border-radius: 5px; padding: 5px 8px; word-break: break-all; }
  #xbexpr { width: 100%; box-sizing: border-box; font-family: ui-monospace, monospace; font-size: 13px; }
  .xblabel { display: block; margin-top: 10px; font-weight: 600; }
  #xbmsg.bad { color: #b45309; }`;
  document.head.appendChild(st);

  let target = null, cat = 0, item = null;
  function open(inp) {
    target = inp; $("xbexpr").value = inp.value; dlg.hidden = false; renderCats(); renderItems(); check();
    const at = inp.value.length; $("xbexpr").focus(); $("xbexpr").setSelectionRange(at, at);
  }
  function close(ok) {
    if (ok && target) { target.value = $("xbexpr").value.trim(); target.dispatchEvent(new Event("input", {bubbles: true})); target.dispatchEvent(new Event("change", {bubbles: true})); }
    dlg.hidden = true; if (target) target.focus(); target = null;
  }
  $("xbok").onclick = () => close(true);
  $("xbcancel").onclick = () => close(false);
  $("xbclear").onclick = () => { $("xbexpr").value = ""; check(); $("xbexpr").focus(); };
  dlg.addEventListener("keydown", ev => { if (ev.key === "Escape") close(false); });
  $("xbexpr").oninput = check;

  function renderCats() {
    const box = $("xbcats"); box.innerHTML = "";
    CATS.forEach(([name], i) => {
      const b = document.createElement("button"); b.textContent = name; b.className = i === cat ? "on" : ""; b.setAttribute("role", "tab");
      b.onclick = () => { cat = i; item = null; renderCats(); renderItems(); }; box.appendChild(b);
    });
  }
  function renderItems() {
    const box = $("xbitems"); box.innerHTML = "";
    const items = CATS[cat][1]();
    if (!items.length) box.innerHTML = '<p class="hint" style="padding:8px">Belum ada di model ini. Tambahkan dulu lewat modul Assign atau data module.</p>';
    for (const it of items) {
      const b = document.createElement("button"); b.innerHTML = `<code>${esc(it.name)}</code>`; b.className = item && item.name === it.name ? "on" : "";
      b.title = it.desc; b.onclick = () => { item = it; renderItems(); renderForm(); }; box.appendChild(b);
    }
    if (!item) $("xbform").innerHTML = `<p class="hint">${CATS[cat][0] === "Distribusi" ? "Pilih distribusi. Untuk mencari distribusi yang cocok dari data, pakai Tools → Input Analyzer." : "Pilih salah satu item."}</p>`;
  }
  function insert(text) {
    const ta = $("xbexpr"), a = ta.selectionStart ?? ta.value.length, b = ta.selectionEnd ?? a;
    ta.value = ta.value.slice(0, a) + text + ta.value.slice(b);
    const at = a + text.length; ta.focus(); ta.setSelectionRange(at, at); check();
  }
  function renderForm() {
    const f = $("xbform"), it = item; f.innerHTML = "";
    const h = document.createElement("div"); h.innerHTML = `<b><code>${esc(it.name)}</code></b><p class="hint" style="margin:4px 0">${esc(it.desc)}</p>`; f.appendChild(h);
    let make;
    if (it.table) make = tableForm(f, it.table);
    else {
      const ins = it.params.map((p, i) => {
        const row = document.createElement("div"); row.className = "xbrow"; f.appendChild(row);
        const l = document.createElement("label"); l.textContent = p.label; l.htmlFor = `xbp${i}`; row.appendChild(l);
        let e;
        if (p.list) { e = document.createElement("select"); for (const n of p.list()) { const o = document.createElement("option"); o.value = o.textContent = n; e.appendChild(o); } if (!e.options.length) { const o = document.createElement("option"); o.value = ""; o.textContent = "(belum ada di model)"; e.appendChild(o); } }
        else { e = document.createElement("input"); e.value = p.def; e.className = "expr"; e.dataset.xb = "skip"; }
        e.id = `xbp${i}`; row.appendChild(e); e.addEventListener("input", upd); e.addEventListener("change", upd); return e;
      });
      make = () => it.make(ins.map(e => num(e.value)));
    }
    const pv = document.createElement("div"); pv.className = "xbpreview"; f.appendChild(pv);
    const add = document.createElement("button"); add.className = "primary"; add.textContent = "Sisipkan ↓"; add.style.alignSelf = "flex-start"; f.appendChild(add);
    function upd() { const t = make(); pv.textContent = t || "–"; add.disabled = !t; }
    add.onclick = () => { const t = make(); if (t) insert(t); };
    f._upd = upd; upd();
  }
  function tableForm(f, kind) {   // DISC / CONT from values and probabilities (%)
    const rows = kind === "disc" ? [["1", "70"], ["2", "30"]] : [["5", "20"], ["10", "50"], ["15", "30"]];
    const wrap = document.createElement("div"); f.appendChild(wrap);
    let start = "0";
    function draw() {
      wrap.innerHTML = "";
      if (kind === "cont") {
        const r = document.createElement("div"); r.className = "xbrow";
        r.innerHTML = `<label for="xbstart">Nilai terkecil</label>`; const s = document.createElement("input"); s.id = "xbstart"; s.value = start;
        s.oninput = () => { start = s.value; f._upd(); }; r.appendChild(s); wrap.appendChild(r);
      }
      const t = document.createElement("table");
      t.innerHTML = `<tr><th>${kind === "disc" ? "Nilai" : "Sampai nilai"}</th><th>Peluang (%)</th><th>Kumulatif</th><th></th></tr>`;
      let cum = 0;
      rows.forEach((r, i) => {
        cum += parseFloat(r[1]) || 0;
        const tr = document.createElement("tr");
        const cell = (k, aria) => { const td = document.createElement("td"), e = document.createElement("input"); e.value = r[k]; e.setAttribute("aria-label", `${aria} baris ${i + 1}`); e.oninput = () => { r[k] = e.value; f._upd(); updCum(); }; td.appendChild(e); tr.appendChild(td); };
        cell(0, kind === "disc" ? "Nilai" : "Sampai nilai"); cell(1, "Peluang");
        const c = document.createElement("td"); c.className = "cum"; tr.appendChild(c);
        const x = document.createElement("td"), del = document.createElement("button"); del.className = "x"; del.textContent = "✕"; del.setAttribute("aria-label", `Hapus baris ${i + 1}`);
        del.disabled = rows.length < 2; del.onclick = () => { rows.splice(i, 1); draw(); f._upd(); }; x.appendChild(del); tr.appendChild(x);
        t.appendChild(tr);
      });
      wrap.appendChild(t);
      const add = document.createElement("button"); add.textContent = "+ Baris"; add.onclick = () => { rows.push(["", ""]); draw(); f._upd(); }; wrap.appendChild(add);
      const tot = document.createElement("div"); tot.className = "hint"; tot.id = "xbtot"; wrap.appendChild(tot);
      updCum();
    }
    function updCum() {
      let cum = 0; const cells = wrap.querySelectorAll("td.cum");
      rows.forEach((r, i) => { cum += parseFloat(r[1]) || 0; if (cells[i]) cells[i].textContent = (cum / 100).toFixed(4).replace(/\.?0+$/, ""); });
      const tot = $("xbtot"); if (tot) { tot.textContent = Math.abs(cum - 100) < 1e-6 ? "✓ Total peluang 100%" : `Total peluang ${+cum.toFixed(4)}% — harus 100%`; tot.className = Math.abs(cum - 100) < 1e-6 ? "hint" : "hint bad"; tot.style.color = Math.abs(cum - 100) < 1e-6 ? "" : "#b45309"; }
    }
    draw();
    return () => {
      const ok = rows.every(r => r[0] !== "" && isFinite(parseFloat(r[1])) && parseFloat(r[1]) >= 0);
      const total = rows.reduce((a, r) => a + (parseFloat(r[1]) || 0), 0);
      if (!ok || Math.abs(total - 100) > 1e-6) return "";
      let cum = 0; const parts = [];
      rows.forEach((r, i) => { cum += parseFloat(r[1]); const c = i === rows.length - 1 ? "1.0" : String(+(cum / 100).toFixed(6)); parts.push(c, num(r[0])); });
      return kind === "disc" ? `DISC(${parts.join(", ")})` : `CONT(0, ${num(start)}, ${parts.join(", ")})`;
    };
  }
  function check() {   // light checks while typing; the Problems tab has the full validation
    const s = $("xbexpr").value, m = $("xbmsg");
    let depth = 0; for (const ch of s) { if (ch === "(") depth++; if (ch === ")") depth--; if (depth < 0) break; }
    m.className = "hint" + (depth ? " bad" : "");
    m.textContent = depth > 0 ? `Kurang ${depth} kurung tutup ")"` : depth < 0 ? 'Ada kurung tutup ")" tanpa pasangan' : s.trim() ? "Tip: klik item di atas untuk menyisipkan di posisi kursor." : "Kosong: bangun expression dengan memilih item di atas, atau ketik langsung.";
  }

  // ƒx on every expression field, and right-click as in Arena
  function decorate(root) {
    for (const inp of root.querySelectorAll("input.expr:not([data-xb])")) {
      inp.dataset.xb = "1";
      if (inp.closest("#xbdlg")) continue;
      const wrap = document.createElement("span"); wrap.className = "xbwrap";
      inp.replaceWith(wrap); wrap.appendChild(inp);
      const b = document.createElement("button"); b.type = "button"; b.className = "xbbtn"; b.textContent = "ƒx"; b.tabIndex = -1;
      b.title = "Expression Builder (atau klik kanan pada kolom)"; b.setAttribute("aria-label", "Expression Builder"); if (inp.id) b.setAttribute("aria-describedby", inp.id);
      b.onclick = ev => { ev.preventDefault(); open(inp); };
      wrap.appendChild(b);
    }
  }
  document.addEventListener("contextmenu", ev => {
    const inp = ev.target.closest && ev.target.closest("input.expr");
    if (inp && !inp.closest("#xbdlg")) { ev.preventDefault(); open(inp); }
  });
  decorate(document.body);
  new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) decorate(n.matches && n.matches("input.expr") ? n.parentNode : n); })
    .observe(document.body, {childList: true, subtree: true});
  window.openExprBuilder = open;
})();
