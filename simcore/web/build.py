"""Build the in-browser version: python -m simcore.web.build [OUT] [--models DIR]

OUT (default "dist") becomes a folder of static files that runs the editor and the engine
entirely in the browser (Pyodide), for any static host: GitHub Pages, Netlify, a campus web
server, or locally with `python -m http.server -d dist`. Saved models stay in each
student's browser; File -> Export JSON gives them a file to hand in.
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent      # .../simcore (the package)
STATIC = PKG / "web" / "static"
ENGINE = [p for p in sorted(PKG.glob("*.py")) if p.name != "__main__.py"] + [PKG / "web" / n for n in ("__init__.py", "api.py", "graph.py")]

HEADERS = """/*
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp
"""


def compact(source: str) -> str:
    """The module without comments and docstrings (smaller download; same code)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body.pop(0)
            if not body:
                body.append(ast.Pass())
    return ast.unparse(tree) + "\n"


def build(out: Path, models: Path | None, skip: set[str] = frozenset()) -> list[str]:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for f in STATIC.iterdir():
        if f.suffix in (".html", ".js", ".css", ".svg"):
            shutil.copy(f, out / f.name)
    page = (out / "index.html").read_text(encoding="utf-8")
    page = page.replace("<script>", '<script src="browser.js"></script>\n<script>', 1)
    (out / "index.html").write_text(page, encoding="utf-8")

    (out / "py").mkdir()
    bundle = {f"simcore/{p.relative_to(PKG).as_posix()}": compact(p.read_text(encoding="utf-8")) for p in ENGINE}
    (out / "py" / "simcore.json").write_text(json.dumps(bundle), encoding="utf-8")

    names = []
    (out / "models").mkdir()
    if models and models.is_dir():
        for m in sorted(models.glob("*.json")):
            if m.stem in skip:
                continue
            shutil.copy(m, out / "models" / m.name)
            names.append(m.stem)
    (out / "models" / "index.json").write_text(json.dumps(names, indent=1), encoding="utf-8")

    (out / "_headers").write_text(HEADERS, encoding="utf-8")   # Netlify / Cloudflare Pages
    (out / ".nojekyll").write_text("", encoding="utf-8")        # GitHub Pages: serve files as they are
    return names


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m simcore.web.build")
    ap.add_argument("out", nargs="?", default="dist")
    ap.add_argument("--models", default="models", help="example models to include (*.json)")
    ap.add_argument("--skip", default="UI Test,Smoke", help="comma-separated model names to leave out")
    a = ap.parse_args()
    out = Path(a.out)
    names = build(out, Path(a.models), {x.strip() for x in a.skip.split(",") if x.strip()})
    print(f"Built {out.resolve()} with {len(names)} example models.")
    print(f"Try it: python -m http.server -d {out} 8000  →  http://localhost:8000/")


if __name__ == "__main__":
    main()
