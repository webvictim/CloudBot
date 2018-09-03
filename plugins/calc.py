# (Attempt to) safely evaluate (some) python expressions.
# See https://stackoverflow.com/a/9558001 for the base implementation.

import ast
import cmath
import math
import operator as op
import random
import resource
import time
import traceback
import types

from cloudbot import hook


# Limits on execution time and memory growth during expression evaluation, in
# seconds and bytes.
ExpressionEvaluationTimeout = 1.0
ExpressionEvaluationMemoryLimit = 10 << 20


def safe_pow(a, b):
    if not isinstance(a, (int, float, complex)) or not isinstance(b, (int, float, complex)):
        raise Exception("unsupported operand type(s) for exponentiation")
    # Determine whether the result will fit into 1024 bits. 710 =~ 1024*log(2)
    if abs(a) > 0 and b * math.log(abs(a)) > 710:
        raise Exception("result out of range evaluating exponentiation")
    return op.pow(a, b)


def safe_factorial(a):
    # Determine whether the result will fit into 1024 bits. log2(171!) =~ 1024.
    if a >= 171:
        raise Exception("result out of range evaluating factorial")
    return math.factorial(a)


def safe_mul(a, b):
    if (isinstance(a, str) and isinstance(b, int)) or (isinstance(a, int) and isinstance(b, str)):
        if len(a if isinstance(a, str) else b) * (b if isinstance(b, int) else a) > 400:
            raise Exception("result too large")
        return op.mul(a, b)
    if not isinstance(a, (int, float, complex)) or not isinstance(b, (int, float, complex)):
        raise Exception("unsupported operand type(s) for multiplication")
    # Determine whether the result will fit into 1024 bits. 710 =~ 1024*log(2)
    if abs(a) > 0 and abs(b) > 0 and math.log(abs(a)) + math.log(abs(b)) > 710:
        raise Exception("result out of range evaluating multiplication")
    return op.mul(a, b)


def safe_lshift(a, b):
    if not isinstance(a, int) or not isinstance(b, int):
        raise Exception("unsupported operand type(s) for left shift")
    # Determine whether the result will fit into 1024 bits
    if math.log(abs(a)) / math.log(2) + abs(b) > 1024:
        raise Exception("result out of range evaluating lshift")
    return op.lshift(a, b)


def eval_expr(expr):
    e = ExpressionEvaluator()
    return e.eval_node(ast.parse(expr, mode='eval').body)


def safe_range(x, y=None, z=None):
    limit = 100000
    if z is not None:
        if z and (y - x) / z > limit:
            raise Exception("range() is capped to {:,d} steps".format(limit))
        return range(x, y, z)
    elif y is not None:
        if (y - x) > limit:
            raise Exception("range() is capped to {:,d} steps".format(limit))
        return range(x, y)
    else:
        if x > limit:
            raise Exception("range() is capped to {:,d} steps".format(limit))
        return range(x)

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

allowed_stateless_functions = {
    # 9.2.1. Number-theoretic and representation functions
    "abs": abs,
    "ceil": math.ceil,
    "copysign": math.copysign,
    "fabs": math.fabs,
    "factorial": safe_factorial,
    "floor": math.floor,
    "fmod": math.fmod,
    "frexp": math.frexp,
    "fsum": math.fsum,
    "isfinite": math.isfinite,
    "isinf": math.isinf,
    "isnan": math.isnan,
    "ldexp": math.ldexp,
    "modf": math.modf,
    "trunc": math.trunc,

    # 9.2.2. Power and logarithmic functions
    "exp": math.exp,
    "expm1": math.expm1,
    "log": math.log,
    "log1p": math.log1p,
    "log2": math.log2,
    "log10": math.log10,
    "pow": safe_pow,
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

    # 9.2.4. Angular conversion
    "degrees": math.degrees,
    "radians": math.radians,

    # 9.2.5. Hyperbolic functions
    "acosh": math.acosh,
    "asinh": math.asinh,
    "atanh": math.atanh,
    "cosh": math.cosh,
    "sinh": math.sinh,
    "tanh": math.tanh,

    # Math extras
    "sec": lambda x: 1 / math.cos(x),
    "csc": lambda x: 1 / math.sin(x),
    "cot": lambda x: 1 / math.tan(x),

    # 9.6. random
    "random": random.random,
    "randint": random.randint,
    "randrange": random.randrange,
    "choice": random.choice,
    "sample": random.sample,
    "shuffle": lambda x: random.sample(x, len(x)),

    # 2. Built-in functions. Some built-ins, e.g. list(), are resource-
    #    limited. These are handled inside ExpressionEvaluator.
    "bool": bool,
    "bin": bin,
    "complex": complex,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "hex": hex,
    "int": int,
    "len": len,
    "max": max,
    "map": map,
    "min": min,
    "oct": oct,
    "ord": ord,
    "range": safe_range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "type": type,
    "zip": zip,
}

constants = {
    "e": math.e,
    "pi": math.pi,

    "True": True,
    "False": False,
}

modules = {
    "cmath": cmath,
}


def attribute_allowed(value, attribute):
    allowed_type_methods = {
        complex: ("conjugate", "imag", "real"),
        dict: ("clear", "copy", "get", "items", "keys", "pop", "popitem", "update", "values"),
        float: ("as_integer_ratio", "as_integer", "hex", "fromhex"),
        int: ("bit_length"),
        list: ("append", "extend", "insert", "remove", "pop", "clear", "index", "count", "sort", "reverse", "copy"),
        set: ("isdisjoint", "issubset", "issuperset", "union", "intersection", "difference", "symmetric_difference"),
        str: ("casefold", "capitalize", "endswith", "find", "isalnum", "isalpha", "isdecimal", "isdigit", "islower", "isnumeric", "isprintable", "isspace", "istitle", "isupper", "join", "lower", "replace", "rfind", "rindex", "rsplit", "rstrip", "split", "startswith", "strip", "swapcase", "title", "upper"),
    }
    allowed_module_methods = {
        cmath: ("phase", "polar", "rect", "exp", "log", "log10", "sqrt", "acos", "asin", "atan", "cos", "sin", "tan", "acosh", "asinh", "atanh", "cosh", "sinh", "tanh", "isinf", "isnan", "pi", "e"),
    }
    if attribute in ("count", "index"):
        return True
    if isinstance(value, types.ModuleType) and value in allowed_module_methods:
        return attribute in allowed_module_methods[value]
    if type(value) in allowed_type_methods:
        return attribute in allowed_type_methods[type(value)]
    return False


class ExpressionEvaluator:
    def __init__(self):
        self.start_time = time.time()
        self.memory_usage = self.get_memory_usage()
        self.allowed_stateful_functions = {
            "all": self.safe_all,
            "any": self.safe_any,
            "list": self.safe_list,
            "reduce": self.safe_reduce,
            "tuple": self.safe_tuple,
        }

    def eval_generators(self, composition, generator_index, context, callback):
        generator = composition.generators[generator_index]
        iterable = generator.iter
        if_statements = generator.ifs
        is_deepest_generator = len(composition.generators) == generator_index + 1
        for i in self.eval_node(iterable, context):
            context = context.copy() if context else {}

            # FIXME: This is hacky. It assumes that the target is either a name or a shallow tuple.
            if isinstance(generator.target, ast.Name):
                context[generator.target.id] = i
            elif isinstance(generator.target, ast.Tuple):
                target_ids = list(map(lambda x: x.id, generator.target.elts))
                for x in range(0, len(target_ids)):
                    context[target_ids[x]] = i[x]
            else:
                raise Exception("Unknown generator target {}".format(generator.target))

            skip = False
            for condition in if_statements:
                if not self.eval_node(condition, context):
                    skip = True
                    break
            if skip:
                continue

            if is_deepest_generator:
                callback(composition, context)
            else:
                self.eval_generators(composition, generator_index + 1, context, callback)

    def safe_tuple(self, iterable):
        return tuple(self.safe_list(iterable))

    def safe_list(self, iterable):
        result = []
        for item in iterable:
            self.check_evaluation_exceeded_limits()
            result.append(item)
        return result

    def safe_all(self, iterable):
        result = []
        for item in iterable:
            self.check_evaluation_exceeded_limits()
            if not item:
                return False
        return True

    def safe_any(self, iterable):
        result = []
        for item in iterable:
            self.check_evaluation_exceeded_limits()
            if item:
                return True
        return False

    def safe_reduce(self, callback, iterable):
        iterator = iter(iterable)
        accumulator = next(iterator)
        for i, item in enumerate(iterable):
            self.check_evaluation_exceeded_limits()
            accumulator = callback(accumulator, item)
        return accumulator

    def check_evaluation_exceeded_limits(self):
        if time.time() - self.start_time > ExpressionEvaluationTimeout:
            raise Exception("timed out evaluating expression")
        memory_usage = self.get_memory_usage()
        if memory_usage - self.memory_usage > ExpressionEvaluationMemoryLimit:
            raise Exception("memory threshold exceeded evaluating expression")

    def get_memory_usage(self):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024

    def eval_node(self, node, context=None):
        self.check_evaluation_exceeded_limits()

        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.NameConstant):
            return node.value
        elif isinstance(node, ast.Str):
            return str(node.s)
        elif isinstance(node, ast.Tuple):
            return tuple(map(lambda x: self.eval_node(x, context), node.elts))
        elif isinstance(node, ast.List):
            return list(map(lambda x: self.eval_node(x, context), node.elts))
        elif isinstance(node, ast.Dict):
            result = dict()
            for key, value in zip(node.keys, node.values):
                result[self.eval_node(key, context)] = self.eval_node(value, context)
            return result
        elif isinstance(node, ast.Set):
            return set(map(lambda x: self.eval_node(x, context), node.elts))
        elif isinstance(node, ast.BoolOp):
            if type(node.op) == ast.And:
                result = self.eval_node(node.values[0], context)
                for i in range(1, len(node.values)):
                    if not result:
                        return result
                    result = result and self.eval_node(node.values[i], context)
                return result
            assert(type(node.op) == ast.Or)
            result = self.eval_node(node.values[0], context)
            for i in range(1, len(node.values)):
                if result:
                    return result
                result = result or self.eval_node(node.values[i], context)
            return result
        elif isinstance(node, ast.BinOp):
            return operators[type(node.op)](self.eval_node(node.left, context), self.eval_node(node.right, context))
        elif isinstance(node, ast.UnaryOp):
            return operators[type(node.op)](self.eval_node(node.operand, context))
        elif isinstance(node, ast.Call):
            function = self.eval_node(node.func, context)
            args = map(lambda x: self.eval_node(x, context), node.args)
            return function(*args)
        elif isinstance(node, ast.Compare):
            lhs = self.eval_node(node.left, context)
            result = True
            for i in range(len(node.ops)):
                rhs = self.eval_node(node.comparators[i], context)
                result &= operators[type(node.ops[i])](lhs, rhs)
                lhs = rhs
            return result
        elif isinstance(node, ast.Name):
            if node.id in constants:
                return constants[node.id]
            if context and node.id in context:
                return context[node.id]
            if node.id in self.allowed_stateful_functions:
                return self.allowed_stateful_functions[node.id]
            if node.id in allowed_stateless_functions:
                return allowed_stateless_functions[node.id]
            if node.id in modules:
                return modules[node.id]
            raise Exception("unknown identifier '{}'".format(node.id))
        elif isinstance(node, ast.Lambda):
            def lambda_eval(*x):
                args = list(x)
                new_context = context.copy() if context else {}
                for i, arg in enumerate(node.args.args):
                    if i < len(args):
                        new_context[arg.arg] = args[i]
                    else:
                        new_context[arg.arg] = self.eval_node(node.args.defaults[i - len(args)], new_context)
                return self.eval_node(node.body, new_context)
            return lambda_eval
        elif isinstance(node, ast.Subscript):
            values = self.eval_node(node.value, context)
            indices = self.eval_node(node.slice, context)
            return values[indices]
        elif isinstance(node, ast.Index):
            return self.eval_node(node.value, context)
        elif isinstance(node, ast.Slice):
            start = self.eval_node(node.lower, context) if node.lower is not None else None
            stop = self.eval_node(node.upper, context) if node.upper is not None else None
            step = self.eval_node(node.step, context) if node.step is not None else None
            return slice(start, stop, step)
        elif isinstance(node, ast.Attribute):
            value = self.eval_node(node.value, context)
            attribute = node.attr
            if not attribute_allowed(value, attribute):
                raise Exception("unknown identifier '{}'".format(node.attr))
            return getattr(value, attribute)
        elif isinstance(node, ast.IfExp):
            condition = self.eval_node(node.test, context)
            return self.eval_node(node.body if condition else node.orelse, context)
        elif isinstance(node, (ast.ListComp, ast.GeneratorExp)):
            result = []
            def array_callback(composition, context):
                result.append(self.eval_node(composition.elt, context))
            self.eval_generators(node, 0, context, array_callback)
            return result
        elif isinstance(node, ast.DictComp):
            result = {}
            def dict_callback(composition, context):
                result[self.eval_node(composition.key, context)] = self.eval_node(composition.value, context)
            self.eval_generators(node, 0, context, dict_callback)
            return result
        elif isinstance(node, ast.SetComp):
            result = set()
            def set_callback(composition, context):
                result.add(self.eval_node(composition.elt, context))
            self.eval_generators(node, 0, context, set_callback)
            return result
        else:
            raise Exception("unsupported AST node type {}".format(node))


@hook.command("calc", "eval")
def on_message(reply, text):
    """eval <expression> - evaluate a Python expression."""
    try:
        result = eval_expr(text)
        result = str(result).replace("\n", "").replace("\r", "")

        if len(result) > 400:
            reply("Exception: result too large")
        else:
            reply(result)
    except Exception as e:
        traceback.print_exc()
        reply("Exception: {}".format(e))

