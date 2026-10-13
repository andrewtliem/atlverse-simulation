# Atlverse Simulation (Python package `simcore`)

A discrete-event simulation engine in Python that implements the functionality of
Arena's SIMAN engine: entities flowing through blocks, resources and queues, transfer
(stations, routes, transporters, conveyors, guided vehicles), combined discrete/continuous
models, and SIMAN-style statistics with batch-means half widths.

Behaviour follows the published SIMAN language and the standard simulation literature
(L'Ecuyer's MRG32k3a streams, batch-means half widths). Results are statistically
comparable to Arena, not digit-for-digit identical (event ordering on ties differs). `COVERAGE.md` lists every
SIMAN block and element and its status.

Requirements: Python 3.10+ (PyYAML only for YAML model files).

Atlverse Simulation is an independent project. It is not affiliated with, endorsed by or
sponsored by Rockwell Automation. Arena and SIMAN are trademarks of Rockwell Automation,
used here only to describe compatibility.

## Three ways to build a model

**1. Web editor** — drag-and-drop modelling, run, and watch the animation:

```bash
python -m simcore.web            # opens http://127.0.0.1:8765, models saved in ./models
```

* Palette: Basic Process (Create, Dispose, Process, Decide, Batch, Separate, Assign, Record),
  Advanced Process (Seize, Delay, Release, Hold, Signal, Remove) and Advanced Transfer (Station, Route,
  Request, Transport, Free, Access, Convey, Exit). Drag onto the canvas, or click then click the canvas.
* Module dialogs follow Arena's prompts (from the Arena 14 help): e.g. Assign has a list of assignments of type
  Variable, Variable Array (1D/2D), Attribute, Entity Type, Entity Picture or Other; Process has Action, Priority,
  a resource list (resources or sets with selection rule, save attribute, set index), Delay Type with its
  parameters, Units, Allocation and Report Statistics; Decide has 2-way/N-way by chance or by condition with
  If/Named/Row/Column/Is/Value conditions; Seize/Hold have Arena's Queue Type (Queue, Set, Internal, Attribute,
  Expression). Prompts that do not apply are hidden, as in Arena. Every time field has its own units.
* Connect by dragging from a port ● to a module.
* Data tab, as Arena's data modules: Entity (picture, costs), Queue (ranking), Resource (fixed or schedule,
  schedule rule, costs, StateSet, failures), Variable and Attribute (rows/columns, data type, clear option,
  initial values), Schedule (capacity/arrival/other, time units, scale factor, durations), Set, Expression,
  Failure (count/time, units, up time only in a state), StateSet, Transporter, Conveyor.
* Live validation (Problems tab, red outlines), undo/redo, copy/paste, box select, pan/zoom,
  autosave in the browser, save/open on the server, JSON import/export, YAML export.
* Run shows a summary (entities, queues, resources, tallies, counters, across-replication half
  widths), the full SIMAN-style report, and the animation.
* Shortcuts: Del, Ctrl+Z/Y, Ctrl+C/V/D, Ctrl+A, Ctrl+S, F5 (run), Shift+click / Shift+drag to select.

**2. YAML** — the engine's own model format (`simcore/loader.py` documents every key):

```bash
python -m simcore examples/bank.yaml --reps 10
```

**3. Python API**:

```python
from simcore import *

m = Model("M/M/1", time_units="minutes")
m.resource("Server")
m.add(Create(interval="EXPO(1)"), Queue("Server.Queue"), Seize(resources=[("Server", 1)]),
      Delay(duration="EXPO(0.8)"), Release(resources=[("Server", 1)]), Dispose())
m.replicate(replications=5, length=10_000)
res = m.run()
print(res.report())
print(res.across("queues.Server.Queue.waiting_time.average"))
```

Expressions use SIMAN syntax: `EXPO(5)`, `TRIA(1, 2, 4)`, `SchedValue(Shift)`, `NQ(Server.Queue) > 3 .AND. Size == 2`,
`MR(Server)`, `TNOW`, `Entity.Type`, …  Any operand also accepts a Python callable
`fn(entity, model)`, and `Call(fn=...)` runs Python code in the flow (replaces SIMAN's EVENT/VBA).

## In the browser (for students)

```bash
python -m simcore.web.build dist          # static site: editor + engine (Pyodide) + example models
python -m http.server -d dist 8000        # try it at http://localhost:8000/
```

`dist/` runs entirely in the browser: the engine is this package running in Pyodide inside a
Web Worker (loaded from cdn.jsdelivr.net on the first visit, then cached for offline use by
`sw.js`). Put the folder on any static host — GitHub Pages (`.nojekyll` included), Netlify or
Cloudflare Pages (`_headers` included), or a campus web server. Saved models stay in each
browser; File → Export JSON gives a file to hand in. The End button needs the page to be
cross-origin isolated: `_headers` does it on Netlify/Cloudflare, `sw.js` on GitHub Pages;
without it End still stops the run but without partial results.

Classroom tools in the editor:

- **Identitas mahasiswa** (👤 in the header): name, NIM and class, stamped into the model
  (`meta`: model ID and every NIM that saved it).
- **File → Laporan HTML / PDF**: report with the model diagram, Run Setup, results and
  scenarios; a watermark with name, NIM and verification code on every page.
  **File → Periksa laporan** recomputes the code (it covers the whole file) and shows the
  model's author history.
- **Tools → Scenarios**: a small Process Analyzer (controls, responses, 95% half widths).
- **Tools → Input Analyzer**: fits UNIF, TRIA, NORM, EXPO, ERLA, GAMM, LOGN, WEIB, BETA, POIS
  (with offsets), ranked by square error, with chi-square and K-S p-values.
- **📈 Plot** while animating: queue lengths, resources busy and WIP against time.

## Random numbers

`model.rng_mode = "arena"` (default) uses Arena's generator setup (MRG32k3a streams and
substreams; legacy 16807 streams when SEEDS are given) and Arena's sampling algorithms,
some of which are approximations (GAMM, POIS > 12, NORM). `"exact"` uses statistically exact
samplers on the same streams. `model.disable_randomness = True` replaces every distribution
by its mean, like Arena's switch.

## Layout

| Path | Contents |
|---|---|
| `simcore/core.py` | entities, queues, resources, variables, simulation loop |
| `simcore/blocks.py` | SIMAN blocks |
| `simcore/model.py` | elements, expression resolver, replication runner, statistics collection |
| `simcore/transfer.py`, `guided.py` | free-path transporters, conveyors, guided vehicles |
| `simcore/continuous.py` | levels, rates, CSTATS, DETECT |
| `simcore/rng.py`, `stats.py` | random numbers/distributions, tallies, half widths |
| `simcore/loader.py` | YAML format and Arena-style modules (process, decide, batch, …) |
| `simcore/web/` | editor: `api.py` (operations shared by server and browser), `server.py`, `build.py` (static site), `static/` (page, `worker.js`, `browser.js`, `learn.js`, `report.js`, `scenarios.js`, `analyzer.js`, `plots.js`) |

## Tests

```bash
python -m unittest discover -s tests       # engine, loader, editor graph conversion
node tests/ui/editor.test.mjs              # editor in headless Chrome (server must be running)
node tests/ui/tools.test.mjs               # report, Scenarios, Input Analyzer, plots (also learn/tutorials)
```

## Speed

About 14,000 entities per second through a simple seize–delay–release model on one core.
Running under PyPy is the easiest speed-up for large models.
