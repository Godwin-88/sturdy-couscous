from __future__ import annotations

import ast
import operator as _op
from dataclasses import dataclass
from typing import Any, Dict

import numpy as np

from .config import BacktestConfig, cfg


@dataclass(frozen=True)
class Formula:
    expression: str
    safe: bool = True


_OPERATORS = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.Pow: _op.pow,
    ast.USub: _op.neg,
}


def _safe_eval(node: ast.AST, bar: Dict[str, Any]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        name = node.id
        if name not in bar:
            raise KeyError(name)
        val = bar[name]
        if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
            return 0.0
        return float(val)
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left, bar)
        right = _safe_eval(node.right, bar)
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise TypeError(f"Disallowed op {op_type}")
        return float(_OPERATORS[op_type](left, right))
    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand, bar)
        return float(_OPERATORS[type(node.op)](operand))
    if isinstance(node, ast.Call):
        fn_name = getattr(node.func, "id", "")
        if fn_name == "clip":
            args = [_safe_eval(a, bar) for a in node.args]
            lo = float(args[1]) if len(args) > 1 else -1.0
            hi = float(args[2]) if len(args) > 2 else 1.0
            return float(np.clip(float(args[0]), lo, hi))
        raise NameError(f"Only 'clip' is allowed in formulas, got {fn_name}")
    raise TypeError(f"Unsupported AST node {type(node).__name__}")


def evaluate_formula(formula: Formula, bar: Dict[str, Any]) -> float:
    tree = ast.parse(formula.expression, mode="eval")
    value = _safe_eval(tree.body, bar)
    return float(np.clip(value, -1.0, 1.0))
