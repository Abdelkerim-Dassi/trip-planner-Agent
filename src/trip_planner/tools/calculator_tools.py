"""Calculator tool for budget math.

Uses a restricted AST evaluator instead of ``eval`` so the agent cannot execute
arbitrary Python through this tool.
"""

import ast
import operator

from crewai.tools import tool

# Allowed binary and unary operators for the safe evaluator.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Unsupported expression")


class CalculatorTool:
    @tool("Make a calculation")
    def calculate(operation: str) -> str:
        """Useful to perform mathematical calculations like sum, minus, multiplication,
        division, etc. The input should be a valid mathematical expression, such as
        '2+2', '200*7', '10/2', or '5000/2*10'.
        """
        try:
            tree = ast.parse(operation, mode="eval")
            return str(_eval_node(tree))
        except ZeroDivisionError:
            return f"Error calculating '{operation}': Division by zero is not allowed."
        except (SyntaxError, ValueError, TypeError):
            return (
                f"Error calculating '{operation}': "
                "Invalid or unsupported mathematical expression."
            )
