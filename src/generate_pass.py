import ast
from _ast import AST
from ast import iter_fields
from pprint import pprint

from scope_tracker import ScopeTracker

INDENT_STEP = 4

DEBUG_SHOW_NODES = False

binop_to_string = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
}

python_type_to_c_type = {
    "int": "int",
    "float": "double",
}

# scoped-symbol:
# <func/class>::<symbol>


class GeneratePass(ScopeTracker):
    def __init__(self, symbols, tree, output_file, lines):
        super().__init__(lines)
        self.syms = symbols
        self.indent_level = 0
        self.out_string = ""
        self.outf = output_file

        # Local context stuff
        self.num_arguments = 0

        # Run the tree
        self.visit(tree)

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
        else:
            raise self.exception(f"Unknown advanced type description {adv_type=}")

    def emit_scope_local_decls(self):
        # Passing self.current_node into self.syms methods for exception handling
        local_syms = self.syms.find_local_syms(self.current_scope())
        if len(local_syms) > 0 and self.current_scope() != "":
            self.output("/* Local Variable Declarations */\n", indent=True)
        for name in sorted(local_syms):
            local_name = self.syms.unscoped_sym(name)
            local_type = self.syms.find_type(name, self.current_node)
            if ":" in local_type:  # advanced types, like list:int etc.
                self.emit_advanced_decl(local_type, local_name)
            else:
                self.output(f"{local_type} {local_name};\n", indent=True)
        if len(local_syms) > 0:
            self.output("\n")

    #
    # Visit Functions
    #

    def visit_Global(self, node):
        pass

    def visit_Module(self, node):
        self.emit_scope_local_decls()
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Passing node into self.syms methods for exception handling
        func_name = node.name
        ret_type = self.syms.find_ret_type(self.scoped_sym(func_name), node=node)
        self.output(f"\n{ret_type} {func_name}")
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

    def visit_arguments(self, node):
        self.num_arguments = 0
        self.output("(")
        self.generic_visit(node)
        self.output(") {\n")
        self.emit_scope_local_decls()
        self.output("/* Main Code */\n", indent=True)

    def visit_arg(self, node):
        # Passing node into self.syms methods for exception handling
        s = ""
        if self.num_arguments > 0:
            s += ", "
        self.num_arguments += 1
        scoped_sym = self.scoped_sym(node.arg)
        scoped_typ = self.syms.find_type(scoped_sym, node=node)
        s += f"{scoped_typ} {node.arg}"
        return s

    def visit_AnnAssign(self, node):
        # Passing node into self.syms methods for exception handling
        target = node.target.id
        scoped_target = self.scoped_sym(target)
        known_type = self.syms.find_type(scoped_target, node=node)
        tgt_type = node.annotation.id
        assert known_type == tgt_type
        value = self.visit(node.value)
        self.output(f"{target} = {value};\n", indent=True)

    def visit_Assign(self, node):
        # Passing node into self.syms methods for exception handling
        targets = node.targets
        tgt_type = self.syms.find_type(self.scoped_sym(targets[0].id), node=node)
        tgt_names = []
        for target in targets:
            tgt_name = target.id
            assert self.syms.find_type(self.scoped_sym(tgt_name), node=node) == tgt_type
            tgt_names.append(target.id)
        tgt_s = " = ".join(tgt_names)
        value = self.visit(node.value)
        self.output(f"{tgt_s} = {value};\n", indent=True)

    def visit_Return(self, node):
        if node.value is None:
            self.output("return;\n", indent=True)
            return
        s = "return ("
        s += str(self.visit(node.value))
        s += ");\n"
        self.output(s, indent=True)

    def visit_Constant(self, node):
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
        self.generic_visit(node)
        self.output(";\n")

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        op_s = binop_to_string[node.op.__class__]
        right = self.visit(node.right)
        return f"({left} {op_s} {right})"

    def visit_UnaryOp(self, node):
        s = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            s = f"-{s}"
        return s

    def visit_Index(self, node):
        return str(self.visit(node.value))

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            s = node.func.value.id + "." + node.func.attr
        else:
            s = node.func.id
        s += "("
        if len(node.args) > 0:
            self.num_arguments = 0
            for arg in node.args:
                if self.num_arguments > 0:
                    s += ", "
                self.num_arguments += 1
                if isinstance(arg, ast.Constant):
                    value = self.visit(arg)
                    if isinstance(value, str):
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
                    s += str(ret)
        if len(s) > 0:
            self.output(s, indent=True)
