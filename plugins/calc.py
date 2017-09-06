# Safely evaluate mathematical expressions.
# See https://stackoverflow.com/a/9558001 for the base implementation.

import ast
import cmath
import copy
import functools
import math
import operator as op
import random

from cloudbot import hook


def safe_pow(a, b):
    # Determine whether the result will fit into 1024 bits. 710 =~ 1024*log(2)
    if abs(a) > 0 and b * math.log(abs(a)) > 710:
        raise Exception("result out of range evaluating exponentiation")
    return op.pow(a, b)


def safe_mul(a, b):
    # Determine whether the result will fit into 1024 bits. 710 =~ 1024*log(2)
    if abs(a) > 0 and abs(b) > 0 and math.log(abs(a)) + math.log(abs(b)) > 710:
        raise Exception("result out of range evaluating multiplication")
    return op.mul(a, b)


def safe_lshift(a, b):
    # Determine whether the result will fit into 1024 bits
    if math.log(abs(a)) / math.log(2) + abs(b) > 1024:
        raise Exception("result out of range evaluating lshift")
    return op.lshift(a, b)


def eval_expr(expr):
    return eval_node(ast.parse(expr, mode='eval').body)


operators = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: safe_mul,
    ast.Div: op.truediv,

    ast.Mod: op.mod,
    ast.Pow: safe_pow,

    ast.BitXor: op.xor,
    ast.BitAnd: op.and_,
    ast.BitOr: op.or_,
    ast.Invert: op.invert,
    ast.LShift: safe_lshift,
    ast.RShift: op.rshift,

    ast.And: op.and_,
    ast.Or: op.or_,

    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Not: op.not_,

    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.Is: op.is_,
    ast.IsNot: op.is_not,
    ast.In: lambda obj, seq: op.contains(seq, obj),
    ast.NotIn: lambda obj, seq: not(op.contains(seq, obj)),
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

    # Math extras
    "sec": lambda x: 1 / math.cos(x),
    "csc": lambda x: 1 / math.sin(x),
    "cot": lambda x: 1 / math.tan(x),

    # 9.6. random
    "random": random.random,
    "randint": random.randint,
    "choice": random.choice,
    "sample": random.sample,
    "shuffle": lambda x: random.sample(x, len(x)),

    # 2. Built-in functions
    "bool": bool,
    "bin": bin,
    "complex": complex,
    "dict": dict,
    "divmod": divmod,
    "filter": filter,
    "float": float,
    "hex": hex,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "oct": oct,
    "reduce": functools.reduce,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
}
constants = {
    "pi": math.pi,
    "e": math.e,

    "True": True,
    "False": False,
}
def eval_node(node, context=None):
    if isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.NameConstant):
        return node.value
    elif isinstance(node, ast.Str):
        return str(node.s)
    elif isinstance(node, (ast.Tuple, ast.List)):
        return tuple(map(lambda x: eval_node(x, context), node.elts))
    elif isinstance(node, ast.Dict):
        result = dict()
        for key, value in zip(node.keys, node.values):
            result[eval_node(key, context)] = eval_node(value, context)
        return result
    elif isinstance(node, ast.BoolOp):
        return operators[type(node.op)](eval_node(node.values[0], context), eval_node(node.values[1], context))
    elif isinstance(node, ast.BinOp):
        return operators[type(node.op)](eval_node(node.left, context), eval_node(node.right, context))
    elif isinstance(node, ast.UnaryOp):
        return operators[type(node.op)](eval_node(node.operand, context))
    elif isinstance(node, ast.Call):
        # context is unnecessary here, because all supported functions are in 'funcs'
        function = eval_node(node.func)
        args = map(lambda x: eval_node(x, context), node.args)
        return function(*args)
    elif isinstance(node, ast.Compare):
        lhs = eval_node(node.left, context)
        result = True
        for i in range(len(node.ops)):
            rhs = eval_node(node.comparators[i], context)
            result &= operators[type(node.ops[i])](lhs, rhs)
            lhs = rhs
        return result
    elif isinstance(node, ast.Name):
        if node.id in constants:
            return constants[node.id]
        if context and node.id in context:
            return context[node.id]
        if node.id in funcs:
            return funcs[node.id]
        raise Exception("unknown identifier '{}'".format(node.id))
    elif isinstance(node, ast.Lambda):
        def lambda_eval(*x):
            args = list(x)
            new_context = copy.deepcopy(context) if context else dict()
            default_arg_index = 0
            for i, arg in enumerate(node.args.args):
                if i < len(args):
                    new_context[arg.arg] = args[i]
                else:
                    new_context[arg.arg] = eval_node(node.args.defaults[default_arg_index], new_context)
                    default_arg_index += 1
            return eval_node(node.body, new_context)
        return lambda_eval
    elif isinstance(node, ast.Subscript):
        values = eval_node(node.value, context)
        indices = eval_node(node.slice, context)
        return values[indices]
    elif isinstance(node, ast.Index):
        return eval_node(node.value, context)
    elif isinstance(node, ast.Slice):
        start = eval_node(node.lower, context) if node.lower is not None else None
        stop = eval_node(node.upper, context) if node.upper is not None else None
        step = eval_node(node.step, context) if node.step is not None else None
        return slice(start, stop, step)
    else:
        raise Exception("unsupported AST node type {}".format(node))


@hook.command("calc", "eval")
def on_message(reply, text):
    """calc <expression> - evaluate a mathematical expression in Python syntax."""
    try:
        result = eval_expr(text)
        if isinstance(result, (filter, map, reversed, zip)):
            result = list(result)
        if len(str(result)) > 400:
            reply("Exception: result too large")
        else:
            reply(result)
    except Exception as e:
        reply("Exception: {}".format(e))

