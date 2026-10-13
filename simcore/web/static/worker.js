// The in-browser build's engine: Pyodide runs simcore/web/api.py in this worker, so a
// run never freezes the page. Messages in: {id, op, body} with op run / yaml / validate /
// upgrade, or {stop: SharedArrayBuffer} once. Out: {id, progress}, {id, ok, result},
// {id, ok: false, error, problems, trace} and {loading} while Pyodide starts.
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
importScripts(PYODIDE + "pyodide.js");

let stop = null;   // Int32Array over a SharedArrayBuffer: [0] = 1 asks the run to end (needs cross-origin isolation)

const engine = (async () => {
  postMessage({loading: "Memuat Python (Pyodide)…"});
  const py = await loadPyodide({indexURL: PYODIDE});
  postMessage({loading: "Memuat engine simulasi…"});
  const files = await (await fetch("py/simcore.json")).json();
  for (const [path, text] of Object.entries(files)) {
    py.FS.mkdirTree("/engine/" + path.split("/").slice(0, -1).join("/"));
    py.FS.writeFile("/engine/" + path, text);
  }
  py.runPython(`
import json, sys, traceback
sys.path.insert(0, "/engine")
from simcore.web import api

def call(op, body, progress):
    try:
        g = json.loads(body) if body else {}
        if op == "run":
            out = api.run_graph(g, lambda rep, reps, t: bool(progress(rep, reps, t)))
        elif op == "yaml":
            out = {"yaml": api.to_yaml(g)}
        elif op == "validate":
            out = {"problems": api.validate(g)}
        elif op == "upgrade":
            out = api.upgrade(g)
        else:
            raise ValueError("unknown operation " + op)
        return json.dumps({"ok": True, "result": out})
    except api.GraphError as e:
        return json.dumps({"ok": False, "error": str(e), "problems": e.problems})
    except Exception as e:
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()})
`);
  postMessage({loading: ""});
  return {py, call: py.globals.get("call")};
})();
engine.catch(e => postMessage({loading: "", failed: String(e && e.message || e)}));

onmessage = async ({data}) => {
  if (data.stop) { stop = new Int32Array(data.stop); return; }
  const {id, op, body} = data;
  let eng;
  try { eng = await engine; } catch (e) { return postMessage({id, ok: false, error: "Engine simulasi gagal dimuat: " + (e.message || e) + " (perlu internet saat pertama kali)"}); }
  if (op === "yaml") { try { await eng.py.loadPackage("pyyaml"); } catch (e) { /* reported by the call below */ } }
  if (stop) Atomics.store(stop, 0, 0);
  const progress = (rep, reps, time) => {
    postMessage({id, progress: {running: true, rep, reps, time}});
    return stop ? Atomics.load(stop, 0) === 1 : false;
  };
  const out = JSON.parse(eng.call(op, body ? JSON.stringify(body) : "", progress));
  postMessage({id, ...out});
};
