// In-browser build (python -m simcore.web.build): answers the editor's /api calls without a
// server. Runs go to worker.js (Pyodide); saved models live in this browser's storage and
// the example models come with the build (models/index.json). Loaded before the editor
// script, which calls localApi() when it exists.
(function () {
  const STORE = "atl.model.";
  let worker = null, seq = 0, stopBuf = null, lastProgress = {running: false}, ready = false, watchdog = null, retried = false;
  const pending = new Map();
  const status = t => { const s = document.getElementById("status"); if (s) s.textContent = t; };

  function arm(ms) {
    clearTimeout(watchdog);
    watchdog = setTimeout(() => {
      if (ready || !worker) return;
      const err = new Error("Engine simulasi belum termuat. Periksa koneksi internet, lalu muat ulang halaman (Ctrl+Shift+R).");
      for (const p of pending.values()) p.reject(err);
      pending.clear(); status("Engine belum termuat — muat ulang halaman (Ctrl+Shift+R)");
      worker.terminate(); worker = null;
    }, ms);
  }
  function startWorker() {
    worker = new Worker("worker.js"); ready = false;
    // if Pyodide never arrives (network, a broken cache), say so instead of waiting forever:
    // 40 s for the worker's first message, then 3 minutes for the download itself
    arm(40000);
    if (self.crossOriginIsolated && typeof SharedArrayBuffer === "function") {
      stopBuf = new SharedArrayBuffer(4); worker.postMessage({stop: stopBuf});
    } else stopBuf = null;
    // a worker that cannot load Pyodide (e.g. a cache written by an older service worker):
    // once, wait for the updated service worker to take over, then start again and resend
    worker.onerror = ev => {
      if (ready || retried) return;
      retried = true; if (ev.preventDefault) ev.preventDefault();
      worker.terminate(); worker = null; status("Memperbarui engine…");
      const again = () => { if (worker) return; startWorker(); for (const [id, p] of pending) worker.postMessage({id, op: p.op, body: p.body}); };
      if (navigator.serviceWorker) {
        navigator.serviceWorker.getRegistration().then(r => r && r.update()).catch(() => {});
        navigator.serviceWorker.addEventListener("controllerchange", again, {once: true});
      }
      setTimeout(again, 4000);
    };
    worker.onmessage = ({data}) => {
      if ("loading" in data) { status(data.loading); if (data.loading === "") { ready = true; clearTimeout(watchdog); } else if (!ready) arm(180000); return; }
      if (data.failed) { status("Engine simulasi gagal dimuat — periksa koneksi internet lalu muat ulang halaman"); return; }
      if (data.progress) { lastProgress = data.progress; return; }
      const p = pending.get(data.id); if (!p) return;
      pending.delete(data.id); lastProgress = {running: false};
      if (data.ok) p.resolve(data.result);
      else { const e = new Error(data.error); e.problems = data.problems; p.reject(e); }
    };
  }
  function call(op, body) {
    if (!worker) startWorker();
    const id = ++seq;
    return new Promise((resolve, reject) => { pending.set(id, {resolve, reject, op, body}); worker.postMessage({id, op, body}); });
  }
  function stopRun() {
    if (!pending.size) return {stopping: false};
    if (stopBuf) { Atomics.store(new Int32Array(stopBuf), 0, 1); return {stopping: true}; }
    // without cross-origin isolation a busy worker cannot be told to stop: start a fresh one
    worker.terminate(); worker = null;
    for (const p of pending.values()) p.reject(new Error("Run dihentikan. Di browser ini hasil sementara tidak tersedia; jalankan lagi sampai selesai untuk melihat laporan."));
    pending.clear(); lastProgress = {running: false};
    startWorker();
    return {stopping: true};
  }

  let examples = null;
  async function exampleNames() {
    if (!examples) { try { examples = await (await fetch("models/index.json")).json(); } catch (e) { examples = []; } }
    return examples;
  }
  function savedNames() {
    const out = [];
    try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith(STORE)) out.push(k.slice(STORE.length)); } } catch (e) {}
    return out;
  }

  window.localApi = async function (method, url, body) {
    const path = url.split("?")[0];
    if (path === "/api/models" && method === "GET") return [...new Set([...savedNames(), ...await exampleNames()])].sort((a, b) => a.localeCompare(b));
    if (path.startsWith("/api/models/")) {
      const name = decodeURIComponent(path.slice("/api/models/".length));
      if (method === "PUT") {
        try { localStorage.setItem(STORE + name, JSON.stringify(body)); }
        catch (e) { throw new Error("Penyimpanan browser penuh — gunakan File → Export JSON untuk menyimpan ke file"); }
        return {saved: name};
      }
      let saved = null; try { saved = localStorage.getItem(STORE + name); } catch (e) {}
      if (saved) return JSON.parse(saved);
      if ((await exampleNames()).includes(name)) return await (await fetch("models/" + encodeURIComponent(name) + ".json")).json();
      throw new Error("no such model");
    }
    if (path === "/api/progress") return lastProgress;
    if (path === "/api/stop") return stopRun();
    if (path === "/api/run") return call("run", body);
    if (path === "/api/yaml") return call("yaml", body);
    if (path === "/api/validate") return call("validate", body);
    if (path === "/api/upgrade") return call("upgrade", body);
    throw new Error("not found: " + url);
  };
  window.ATL_BROWSER = true;
  // sw.js makes the page cross-origin isolated (for End) and caches it for offline use;
  // the first visit reloads once so the worker controls the page
  if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
    navigator.serviceWorker.register("sw.js").then(() => {
      let again = false; try { again = sessionStorage.getItem("atl.swreload") === "1"; } catch (e) {}
      if (!self.crossOriginIsolated && !again) {
        navigator.serviceWorker.ready.then(() => {
          if (pending.size) return;   // never interrupt a run; End works without partial results this time
          try { sessionStorage.setItem("atl.swreload", "1"); } catch (e) {}
          location.reload();
        });
      }
    }).catch(() => {});
  }
  addEventListener("load", () => setTimeout(() => { if (!worker) startWorker(); }, 300));   // load Pyodide early
})();
