# Safely evaluate mathematical expressions.
# See https://stackoverflow.com/a/9558001 for the base implementation.

import ast
import math
import operator as op

from cloudbot import hook


def safe_pow(a, b):
    if abs(a) > 1 and abs(b) > 100 or math.log10(a) > 10 and b > 2:
        raise Exception("result out of range evaluating {}**{}".format(a,b))
    return op.pow(a, b)


def eval_expr(expr):
    return eval_node(ast.parse(expr, mode='eval').body)


operators = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,

    ast.Mod: op.mod,
    ast.Pow: safe_pow,

    ast.BitXor: op.xor,
    ast.BitAnd: op.and_,
    ast.BitOr: op.or_,
    ast.Invert: op.invert,
    ast.LShift: op.lshift,
    ast.RShift: op.rshift,

    ast.And: op.and_,
    ast.Or: op.or_,

    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Not: op.not_,
}
funcs = {
    # 9.2.1. Number-theoretic and representation functions
    "abs": abs,
    "ceil": math.ceil,
    "fabs": math.fabs,
    "floor": math.floor,

    # 9.2.2. Power and logarithmic functions
    "exp": math.exp,
    "log": math.log,
    "pow": safe_pow,
    "log10": math.log10,
    "sqrt": math.sqrt,

    # 9.2.3. Trigonometric functions
    "acos": math.acos,
    "asin": math.asin,
    "atan": math.atan,
    "atan2": math.atan2,
    "cos": math.cos,
    "hypot": math.hypot,
    "sin": math.sin,
    "tan": math.tan,

    # Extras
    "sec": lambda x: 1/math.cos(x),
    "csc": lambda x: 1/math.sin(x),
    "cot": lambda x: 1/math.tan(x),
}
constants = {
    "pi": math.pi,
    "e": math.e,

    "True": True,
    "False": False,
}
def eval_node(node):
    if isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.NameConstant):
        return node.value
    elif isinstance(node, ast.BoolOp):
        return operators[type(node.op)](eval_node(node.values[0]), eval_node(node.values[1]))
    elif isinstance(node, ast.BinOp):
        return operators[type(node.op)](eval_node(node.left), eval_node(node.right))
    elif isinstance(node, ast.UnaryOp):
        return operators[type(node.op)](eval_node(node.operand))
    elif isinstance(node, ast.Call):
        if node.func.id in funcs:
            args = map(eval_node, node.args)
            return funcs[node.func.id](*args)
        raise Exception("unsupported function '{}'".format(node.func.id))
    elif isinstance(node, ast.Name):
        if node.id in constants:
            return constants[node.id]
        raise Exception("unknown identifier '{}'".format(node.id))
    else:
        raise TypeError(node)


@hook.command("calc")
def on_message(reply, text):
    try:
        result = eval_expr(text)
        if len(str(result)) > 400:
            reply("Exception: result too large")
        else:
            reply(result)
    except Exception as e:
        reply("Exception: " + str(e))
