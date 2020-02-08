import ast
from _ast import AST
from ast import iter_fields
from pprint import pprint

from scope_tracker import ScopeTracker
from symbol_pass import SymbolPass

INDENT_STEP = 4

DEBUG_SHOW_NODES = False

binop_to_string_dict = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Lt: "<",
    ast.Gt: ">",
    ast.LtE: "<=",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
}

boolop_to_string_dict = {
    ast.And: "and",
    ast.Or: "or",
    ast.Not: "not",
}

python_type_to_c_type = {
    "int": "int",
    "float": "double",
    "str": "string",
    "bool": "bool",
    "void": "void",
}

# scoped-symbol:
# <func/class>::<symbol>

MODULE_HEADING = """/* Generated by PyToC Translator */

#pragma GCC diagnostic ignored "-Wdeprecated"
#include <ArduinoSTL.h>
#include <string>

using namespace std;

"""


class GeneratePass(ScopeTracker):
    def __init__(self, symbols, tree, output_file, lines, headings=True):
        super().__init__(lines)
        self.syms = symbols
        self.indent_level = 0
        self.out_string = ""
        self.headings = headings
        self.outf = output_file

        # Local context stuff
        self.current_target = None  # hold assignment target during eval
        self.num_arguments = 0
        self.during_assign = False

        # Run the tree
        self.visit(tree)

    def boolop_to_string(self, obj_or_class):
        ret = boolop_to_string_dict.get(obj_or_class, None)
        if ret is None:
            return boolop_to_string_dict[obj_or_class.__class__]

    def binop_to_string(self, obj_or_class):
        ret = binop_to_string_dict.get(obj_or_class, None)
        if ret is None:
            return binop_to_string_dict[obj_or_class.__class__]

    def indented(self, s):
        return " " * self.indent_level + s

    def output(self, s, indent=False):
        if indent and (len(self.out_string) == 0 or self.out_string[-1] == "\n"):
            if "\n" in s.rstrip("\n"):
                lines = [self.indented(x).rstrip() for x in s.splitlines()]
                line = "\n".join(lines)
                if len(s) > 0 and s[-1] == "\n":
                    line += "\n"
                self.out_string += line
            else:
                self.out_string += self.indented(s)
        else:
            self.out_string += s
        if len(self.out_string) > 0 and self.out_string[-1] == "\n":
            self.outf.write(self.out_string)
            self.out_string = ""

    def indent(self):
        self.indent_level += INDENT_STEP

    def outdent(self):
        if self.indent_level >= INDENT_STEP:
            self.indent_level -= INDENT_STEP

    def emit_list_decl(self, parts, symbol):
        assert len(parts) == 3
        elem_type = parts[2]
        list_size = parts[1]
        self.output(f"{elem_type} {symbol}[{list_size}];\n", indent=True)

    def emit_advanced_decl(self, adv_type, symbol):
        assert ":" in adv_type
        parts = adv_type.split(":")
        selector = parts[0]
        if selector == "list":
            self.emit_list_decl(parts, symbol)
        # elif selector == "dict_t":
        #     self.output(f"dict_t {symbol};\n", indent=True)
        else:
            raise self.exception(f"Unknown advanced type description {adv_type=}")

    def emit_scope_local_decls(self):
        # Passing self.current_node into self.syms methods for exception handling
        local_syms = self.syms.find_local_syms(
            self.current_scope(), include_function_args=False
        )
        if len(local_syms) > 0 and self.current_scope() != "" and self.headings:
            self.output("/* Local Variable Declarations */\n", indent=True)
        for name in sorted(local_syms):
            local_name = self.syms.unscoped_sym(name)
            local_type = self.syms.find_type(name, self.current_node)
            if ":" in local_type:  # advanced types, like list:int etc.
                self.emit_advanced_decl(local_type, local_name)
            else:
                c_type = python_type_to_c_type[local_type]
                self.output(f"{c_type} {local_name};\n", indent=True)
        if len(local_syms) > 0:
            self.output("\n")

    def handle_builtin_typecall(self, node):
        builtin = node.func.id
        if builtin == 'str':
            return "string"
        elif builtin == 'tuple':
            return "tuple"
        raise self.exception("Unhandled case")

    # def prep_dict_key(self, key, key_type):
    #     if key_type == 'int':
    #         return f"((void*)({key}))"
    #     else:
    #         raise self.exception(f"Keys of type {key_type} not supported for dictionaries.")
    #
    # def prep_dict_val(self, val, val_type):
    #     if val_type == 'int':
    #         return f"((void*)({val}))"
    #     else:
    #         raise self.exception(f"Values of type {val_type} not supported for dictionaries.")

    #
    # Visit Functions
    #

    def visit_Global(self, node):
        pass

    def visit_Module(self, node):
        if self.headings:
            self.output(MODULE_HEADING + "\n")
        self.emit_scope_local_decls()
        self.generic_visit(node)

    # def visit_Dict(self, node):
    #     # This is hard... We need to use GCC's expression block ({ .. })
    #     this_dict_types = self.syms.get_type_from_value(node)
    #     _, key_type, val_type = this_dict_types.split(":")
    #     s = "({\n"
    #     self.indent()
    #     key_c_type = python_type_to_c_type[key_type]
    #     s += self.indented(f"dict_t ret = ht_create(DEFAULT_DICT_SIZE, sizeof({key_c_type}));\n")
    #     # TODO: emit code to handle NULL return from ht_create()
    #     for idx in range(len(node.keys)):
    #         key = self.visit(node.keys[idx])
    #         val = self.visit(node.values[idx])
    #         # Assuming int for now...
    #         key_s = self.prep_dict_key(key, key_type)
    #         val_s = self.prep_dict_val(val, val_type)
    #         s += self.indented(f"ht_put(ret, {key_s}, {val_s});\n")
    #     s += self.indented("ret;\n")
    #     s += self.indented("})")
    #     self.outdent()
    #     return s

    def visit_FunctionDef(self, node):
        # Passing node into self.syms methods for exception handling
        func_name = node.name
        ret_type = self.syms.find_ret_type(self.scoped_sym(func_name), node=node)
        c_ret_type = python_type_to_c_type[ret_type]
        self.output(f"\n{c_ret_type} {func_name}")
        self.enter_scope(func_name)
        self.indent()
        # Ugly hack to avoid seeing the return type again...
        keep_returns = None
        if node.returns is not None:
            keep_returns = node.returns
            node.returns = None
        self.generic_visit(node)  # visit all children of this node
        if keep_returns is not None:
            node.returns = keep_returns
        self.outdent()
        self.exit_scope(func_name)
        self.output("}\n\n\n")

    def visit_Compare(self, node):
        if len(node.comparators) != 1 or len(node.ops) != 1:
            raise self.exception(f"Only simple binary comparisons are supported")
        s = "(" + str(self.visit(node.left))
        op_s = self.binop_to_string(node.ops[0])
        s += f" {op_s} "
        s += str(self.visit(node.comparators[0])) + ")"
        return s

    def visit_BoolOp(self, node):
        op_s = self.boolop_to_string(node.op)
        ret = (
            "("
            + f" {op_s} ".join([str(self.visit(value)) for value in node.values])
            + ")"
        )
        return ret

    def visit_arguments(self, node):
        self.num_arguments = 0
        self.output("(")
        self.generic_visit(node)
        self.output(") {\n")
        self.emit_scope_local_decls()
        if self.headings:
            self.output("/* Main Code */\n", indent=True)

    def visit_arg(self, node):
        # Passing node into self.syms methods for exception handling
        s = ""
        if self.num_arguments > 0:
            s += ", "
        self.num_arguments += 1
        scoped_sym = self.scoped_sym(node.arg)
        scoped_typ = self.syms.find_type(scoped_sym, node=node)
        c_scoped_typ = python_type_to_c_type[scoped_typ]
        s += f"{c_scoped_typ} {node.arg}"
        return s

    def visit_AnnAssign(self, node):
        # Passing node into self.syms methods for exception handling
        self.during_assign = True
        target = node.target.id
        scoped_target = self.scoped_sym(target)
        known_type = self.syms.find_type(scoped_target, node=node)
        tgt_type = node.annotation.id
        assert known_type == tgt_type
        self.current_target = node.target
        value = self.visit(node.value)
        self.current_target = None
        if tgt_type == "str":
            if not isinstance(value, str):
                raise self.exception(
                    f"Assignment to {tgt_s} of {value=} which is not a string"
                )
        self.output(f"{target} = {value};\n", indent=True)
        self.during_assign = False

    def visit_Assign(self, node):
        # Passing node into self.syms methods for exception handling
        self.during_assign = True
        targets = node.targets
        tgt_type = self.syms.find_type(self.scoped_sym(targets[0].id), node=node)
        tgt_names = []
        for target in targets:
            tgt_name = target.id
            assert self.syms.find_type(self.scoped_sym(tgt_name), node=node) == tgt_type
            tgt_names.append(target.id)
        tgt_s = " = ".join(tgt_names)
        self.current_target = target.id
        value = self.visit(node.value)
        self.current_target = None
        if tgt_type == "str":
            if not isinstance(value, str):
                raise self.exception(
                    f"Assignment to {tgt_s} of {value=} which is not a string"
                )
        self.output(f"{tgt_s} = {value};\n", indent=True)
        self.during_assign = False

    def visit_Return(self, node):
        if node.value is None:
            self.output("return;\n", indent=True)
            return
        s = "return ("
        s += str(self.visit(node.value))
        s += ");\n"
        self.output(s, indent=True)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            if '"' in node.value:
                ret = node.value.replace('"', '\\"')
            if self.during_assign:
                return f'string("{node.value}")'
            else:
                return f'"{node.value}"'
        elif isinstance(node.value, bool):
            return str(node.value).lower()
        else:
            return node.value

    def visit_List(self, node):
        s = "["
        first = True
        for elem in node.elts:
            if first:
                first = False
            else:
                s += ", "
            s += str(self.visit(elem))
        s += "]"
        return s

    def visit_Tuple(self, node):
        return self.visit_List(node)

    def visit_Name(self, node):
        return node.id

    def visit_Load(self, node):
        self.generic_visit(node)

    def visit_Expr(self, node):
        was_docstring = self.generic_visit(node)
        if not was_docstring:
            self.output(";\n")

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        op_s = self.binop_to_string(node.op)
        right = self.visit(node.right)
        return f"({left} {op_s} {right})"

    def visit_UnaryOp(self, node):
        s = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            s = f"-{s}"
        elif isinstance(node.op, ast.Not):
            s = f"!{s}"
        return s

    def visit_Index(self, node):
        return str(self.visit(node.value))

    def visit_Call(self, node):
        is_string = False
        is_list = False
        if isinstance(node.func, ast.Attribute):
            s = node.func.value.id + "." + node.func.attr
        else:
            s = node.func.id
            if s in SymbolPass.builtin_typecall_names:
                s = self.handle_builtin_typecall(node)
                if s == "string":
                    is_string = True
                elif s in ("tuple", "list", "set"):
                    is_list = True
        if is_list:
            s = "["
        else:
            s += "("
        if len(node.args) > 0:
            self.num_arguments = 0
            for arg in node.args:
                if self.num_arguments > 0:
                    s += ", "
                self.num_arguments += 1
                if isinstance(arg, ast.Constant):
                    value = self.visit(arg)
                    if is_string:
                        value = f'"{value}"'
                elif isinstance(arg, ast.Subscript):
                    value = self.visit(arg.value)
                    value += "["
                    value += self.visit(arg.slice)
                    value += "]"
                elif isinstance(arg, ast.Name):
                    value = arg.id
                elif isinstance(arg, ast.BinOp):
                    value = self.visit_BinOp(arg)
                else:
                    raise Exception(f"Unexpected {arg=}")
                s += f"{value}"
        if is_list:
            s += "]"
        else:
            s += ")"
        return s

    def visit(self, node):
        """Visit a node."""
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        if visitor == self.generic_visit or DEBUG_SHOW_NODES:
            print(f"Going to call {method} {node!r}")
        self.current_node = node  # will be used for easy error reporting
        return visitor(node)

    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        s = ""
        is_docstring = False
        maybe_docstring = False
        if isinstance(node, ast.Expr) and self.current_target is None:
            maybe_docstring = True
        for field, value in iter_fields(node):
            if isinstance(value, list):
                if DEBUG_SHOW_NODES:
                    print(f"Iterating {node.__class__.__name__}.{field}")
                for item in value:
                    if isinstance(item, AST):
                        if DEBUG_SHOW_NODES:
                            print(f"Going to visit list item {item.__class__.__name__}")
                        ret = self.visit(item)
                        if ret is not None:
                            s += str(ret)
            elif isinstance(value, AST):
                if DEBUG_SHOW_NODES:
                    print(f"Going to visit value {value.__class__.__name__}")
                ret = self.visit(value)
                if ret is not None:
                    if maybe_docstring and isinstance(value, ast.Constant):
                        is_docstring = True
                        ret = ret[1:-1]
                    s += str(ret)
        if len(s) > 0:
            if is_docstring:
                self.output(f"/* {s} */\n", indent=True)
                return True
            else:
                self.output(s, indent=True)
        return None
