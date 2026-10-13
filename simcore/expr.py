"""SIMAN expression compiler.

Supports the SIMAN/Arena expression syntax:
  arithmetic  + - * / ** ^   comparisons == <> <= >= < > and .EQ. .NE. .LT. ...
  logic       .AND. .OR. .NOT. && ||
  calls       EXPO(5), NQ(Queue 1), MR(Server), Var(i, j), AINT(x), MN(a, b), ...
  names       attributes, variables, expressions, special variables (TNOW, NREP, J, ...)

Expressions compile once into a Python AST that is validated against a
whitelist and evaluated with a resolver supplied by the model. Python callables
are accepted wherever an expression is accepted.
"""

from __future__ import annotations

import ast
import math
import re
from typing import Any, Callable

_DOT_OPS = {
    ".EQ.": " == ", ".NE.": " != ", ".LT.": " < ", ".GT.": " > ",
    ".LE.": " <= ", ".GE.": " >= ", ".AND.": " and ", ".OR.": " or ", ".NOT.": " not ",
}

_ALLOWED = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Call,
    ast.Name, ast.Load, ast.Constant, ast.IfExp,
    ast.And, ast.Or, ast.Not, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.USub, ast.UAdd, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


class ExprError(ValueError):
    pass


def _translate(src: str) -> str:
    s = src.strip()
    # Strings are not part of numeric SIMAN expressions; keep quoted text intact.
    out, i = [], 0
    for m in re.finditer(r'"[^"]*"', s):
        out.append(_translate_code(s[i:m.start()]))
        out.append(m.group(0))
        i = m.end()
    out.append(_translate_code(s[i:]))
    return "".join(out)


def _translate_code(s: str) -> str:
    for k, v in _DOT_OPS.items():
        s = re.sub(re.escape(k), v, s, flags=re.I)
    s = s.replace("<>", "!=").replace("&&", " and ").replace("||", " or ").replace("^", "**")
    # Single '=' as comparison (SIMAN allows it in conditions).
    s = re.sub(r"(?<![=!<>])=(?!=)", "==", s)
    # Dotted symbol names (Entity.Type, Server.NumberBusy) become one identifier.
    s = re.sub(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)", lambda m: m.group(1).replace(".", _DOT), s)
    return s


_DOT = "__dot__"


class Compiled:
    __slots__ = ("source", "code", "names", "fn")

    def __init__(self, source: str, code, names: set[str]) -> None:
        self.source, self.code, self.names = source, code, names


_cache: dict[str, Compiled] = {}


def compile_expr(src: str) -> Compiled:
    if src in _cache:
        return _cache[src]
    py = _translate(src).strip()   # a leading .NOT. becomes ' not ...'
    # Symbol names in Arena may contain spaces/dots ("Queue 1", "Process 1.Queue").
    # Callers should register such names with `quote_names` first; here we
    # accept plain identifiers only.
    try:
        tree = ast.parse(py, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"cannot parse expression {src!r}: {e.msg}") from None
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExprError(f"unsupported syntax {type(node).__name__} in {src!r}")
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
            raise ExprError(f"only named functions may be called in {src!r}")
        if isinstance(node, ast.Name):
            names.add(node.id)
    # Route every name and call through the resolver, then wrap as lambda R, E: <expr>
    body = _Rewriter().visit(tree).body
    fn_tree = ast.Expression(ast.Lambda(
        ast.arguments(posonlyargs=[], args=[ast.arg("R"), ast.arg("E")], kwonlyargs=[], kw_defaults=[], defaults=[]),
        body))
    ast.fix_missing_locations(fn_tree)
    code = compile(fn_tree, f"<expr {src}>", "eval")
    c = Compiled(src, code, names)
    c.fn = eval(code, {"__builtins__": {}})
    _cache[src] = c
    return c


class _Rewriter(ast.NodeTransformer):
    """Name x -> R.name("x", E); call f(a) -> R.call("f", (a,), E)."""

    def visit_Call(self, node: ast.Call):
        name = node.func.id.replace(_DOT, ".")  # type: ignore[attr-defined]
        args = [self.visit(a) for a in node.args]
        return ast.Call(func=ast.Attribute(ast.Name("R", ast.Load()), "call", ast.Load()),
                        args=[ast.Constant(name), ast.Tuple(args, ast.Load()), ast.Name("E", ast.Load())],
                        keywords=[])

    def visit_Name(self, node: ast.Name):
        return ast.Call(func=ast.Attribute(ast.Name("R", ast.Load()), "name", ast.Load()),
                        args=[ast.Constant(node.id.replace(_DOT, ".")), ast.Name("E", ast.Load())],
                        keywords=[])


Value = Any


def evaluate(expr, resolver, entity=None) -> Value:
    """Evaluate a SIMAN expression, number or callable(entity, model)."""
    if isinstance(expr, (int, float)):
        return expr
    if isinstance(expr, str):
        try:
            return compile_expr(expr).fn(resolver, entity)
        except ZeroDivisionError:
            return math.inf
    if callable(expr):
        return expr(entity, resolver.model)
    raise ExprError(f"not an expression: {expr!r}")
