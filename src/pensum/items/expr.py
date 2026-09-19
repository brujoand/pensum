"""Arithmetic an item template can ask for, and nothing else.

A template says `legs: 2 * hens + 4 * sheep` in a YAML file, and that string has
to become a number. `eval()` would do it in one line and would also hand every
data file in the repository the right to run arbitrary Python, which is not a
right a question about sheep should have. So this parses the string to an AST
and walks it, refusing any node it does not recognise.

What is allowed is deliberately small: the four operations, integer division and
remainder, a bounded power, comparison, `and`/`or`/`not`, and names bound by the
caller. No calls, no attributes, no subscripts, no lambdas, no literals other
than numbers. An author who needs something outside that is describing a
question this format should not be generating.

The same walk answers a second question the schema needs: `names()` reports the
variables an expression reads, which is what tells a template which of its
fields are free parameters and which are derived from them.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from functools import lru_cache
from typing import Any

__all__ = ["ExpressionError", "evaluate", "names", "parse"]

# Bounded so an author cannot write `9 ** 9 ** 9` and hang the build enumerating
# a domain. Nothing in a school arithmetic question needs more reach.
MAX_POWER = 8

_BINARY: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_COMPARE: dict[type[ast.cmpop], Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}


class ExpressionError(ValueError):
    """An expression that will not parse, will not evaluate, or is not allowed.

    One class rather than several because every one of them is the same thing to
    the author: the line they wrote is not an expression this format accepts,
    and the message says which part.
    """


@lru_cache(maxsize=1024)
def parse(source: str) -> ast.Expression:
    """Parse an expression, refusing anything that is not one.

    Separate from `evaluate` because a template is checked once, when the file
    loads, and evaluated once per instance. Parsing per instance would turn a
    typo into a failure at question time rather than at load time.

    Cached on the source string, so enumerating two thousand instances of a
    template parses each of its expressions once rather than two thousand times.
    The tree is only ever read, so handing the same one to every caller is safe.
    """
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as error:
        raise ExpressionError(f"{source!r} is not an expression: {error.msg}") from error
    _check(tree.body, source)
    return tree


def names(tree: ast.Expression) -> set[str]:
    """Every variable the expression reads."""
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def evaluate(tree: ast.Expression, bindings: dict[str, Any]) -> Any:
    """Evaluate a parsed expression against a set of bound names."""
    return _eval(tree.body, bindings)


def _check(node: ast.expr, source: str) -> None:
    """Walk the tree once at parse time, so a bad node is a load-time error."""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, int | float) or isinstance(node.value, bool):
            raise ExpressionError(f"{source!r}: only numbers are allowed, not {node.value!r}")
        return

    if isinstance(node, ast.Name):
        return

    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINARY:
            raise ExpressionError(f"{source!r}: {type(node.op).__name__} is not allowed")
        _check(node.left, source)
        _check(node.right, source)
        return

    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _UNARY:
            raise ExpressionError(f"{source!r}: {type(node.op).__name__} is not allowed")
        _check(node.operand, source)
        return

    if isinstance(node, ast.BoolOp):
        for value in node.values:
            _check(value, source)
        return

    if isinstance(node, ast.Compare):
        for op in node.ops:
            if type(op) not in _COMPARE:
                raise ExpressionError(f"{source!r}: {type(op).__name__} is not allowed")
        _check(node.left, source)
        for comparator in node.comparators:
            _check(comparator, source)
        return

    raise ExpressionError(f"{source!r}: {type(node).__name__} is not allowed here")


def _eval(node: ast.expr, bindings: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in bindings:
            raise ExpressionError(f"{node.id} is not defined")
        return bindings[node.id]

    if isinstance(node, ast.BinOp):
        left = _eval(node.left, bindings)
        right = _eval(node.right, bindings)
        if isinstance(node.op, ast.Pow) and right > MAX_POWER:
            raise ExpressionError(f"a power above {MAX_POWER} is not allowed")
        if isinstance(node.op, ast.Div | ast.FloorDiv | ast.Mod) and right == 0:
            # Reported rather than raised as ZeroDivisionError because this is
            # reachable from a parameter value, not only from a typo: an author
            # dividing by `hens - 4` has written a domain that must exclude 4.
            raise ExpressionError("division by zero")
        return _BINARY[type(node.op)](left, right)

    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_eval(node.operand, bindings))

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(value, bindings) for value in node.values)
        return any(_eval(value, bindings) for value in node.values)

    if isinstance(node, ast.Compare):
        left = _eval(node.left, bindings)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval(comparator, bindings)
            if not _COMPARE[type(op)](left, right):
                return False
            left = right
        return True

    raise ExpressionError(f"{type(node).__name__} is not allowed here")
