import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from simcore.web import api
from simcore.web.build import ENGINE, build

ROOT = Path(__file__).resolve().parent.parent
BANK = {"version": 2, "name": "Bank", "time_units": "minutes",
        "run": {"replications": "2", "length": "480", "length_units": "Minutes", "batch_run": True},
        "data": {"resources": {"Teller": {"type": "Fixed Capacity", "capacity": "1"}}},
        "nodes": [{"id": "1", "type": "create", "x": 0, "y": 0, "props": {"name": "In", "type": "Random (Expo)", "value": "5", "units": "Minutes", "entity_type": "C"}},
                  {"id": "2", "type": "process", "x": 0, "y": 0, "props": {"name": "Serve", "type": "Standard", "action": "Seize Delay Release",
                   "resources": [{"type": "Resource", "resource": "Teller", "quantity": "1"}], "delay_type": "Triangular",
                   "minimum": "3", "value": "4", "maximum": "6", "units": "Minutes"}},
                  {"id": "3", "type": "dispose", "x": 0, "y": 0, "props": {"name": "Out"}}],
        "links": [{"from": "1", "to": "2", "port": "out"}, {"from": "2", "to": "3", "port": "out"}],
        "meta": {"id": "M-TEST", "authors": [{"name": "A", "nim": "1"}]}, "scenarios": {"controls": [], "rows": []}}


class TestApi(unittest.TestCase):
    def test_run_is_json_and_can_stop(self):
        res = api.run_graph(BANK)
        json.dumps(res)   # NaN/inf cleaned
        self.assertEqual(res["replications_done"], 2)
        self.assertFalse(res["stopped"])
        self.assertIn("queues.Serve.Queue", res["across"])
        seen = []

        def progress(rep, reps, t):
            seen.append((rep, reps))
            return True   # End at the first check
        long = {**BANK, "run": {**BANK["run"], "length": "1000000"}}
        res = api.run_graph(long, progress)
        self.assertTrue(res["stopped"])
        self.assertEqual(seen[0], (1, 2))
        self.assertLess(res["replications"][0]["time"], 1000000)

    def test_validate_and_yaml(self):
        self.assertEqual(api.validate(BANK), [])
        bad = {**BANK, "links": []}
        self.assertTrue(api.validate(bad))
        self.assertIn("Teller", api.to_yaml(BANK))


class TestBuild(unittest.TestCase):
    def test_static_build(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "dist"
            names = build(out, ROOT / "models", {"UI Test", "Smoke"})
            page = (out / "index.html").read_text()
            self.assertLess(page.index('src="browser.js"'), page.index("<script>\n"))
            for f in ("worker.js", "sw.js", "learn.js", "report.js", "scenarios.js", "analyzer.js", "plots.js", "_headers", ".nojekyll"):
                self.assertTrue((out / f).exists(), f)
            self.assertEqual(json.loads((out / "models" / "index.json").read_text()), names)
            self.assertNotIn("UI Test", names)
            bundle = json.loads((out / "py" / "simcore.json").read_text())
            self.assertEqual(len(bundle), len(ENGINE))
            # the bundled engine imports and runs without PyYAML or the server
            (out / "engine").mkdir()
            for path, text in bundle.items():
                p = out / "engine" / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
            code = ("import sys, json; sys.modules['yaml'] = None; sys.path.insert(0, sys.argv[1]);"
                    "from simcore.web import api; print(api.run_graph(json.loads(sys.argv[2]))['replications_done'])")
            r = subprocess.run([sys.executable, "-I", "-c", code, str(out / "engine"), json.dumps(BANK)], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "2", r.stderr)
            self.assertNotIn("server", " ".join(bundle))


if __name__ == "__main__":
    unittest.main()
