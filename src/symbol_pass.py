import ast
from pprint import pprint

# scoped-symbol:
# <func/class>::<symbol>
from scope_tracker import ScopeTracker


class SymbolPass(ScopeTracker):
    def __init__(self, tree, lines):
        super().__init__()
        self.symbols = (
            {}
        )  # key = scope, value = set of scoped symbol-names in this scope
        self.types = {}  # key = scoped-symbol, value = python type
        self.lines = lines
        self.visit(tree)

    def exception_message(self, node, text):
        msg = f"In line {node.lineno}: ["
        src_lines = self.lines[node.lineno - 1 : node.end_lineno]
        src_lines[-1] = src_lines[-1][: node.end_col_offset]
        src_lines[0] = src_lines[0][node.col_offset :]
        src_text = " ".join(src_lines)
        msg += src_text
        msg += "] " + text
        return msg

    def get_type_from_value(self, value_node):
        if isinstance(value_node, ast.Constant):
            value = value_node.value
            if isinstance(value, int):
                return "int"
            elif isinstance(value, str):
                msg = self.exception_message(value_node, "Strings not yet supported")
                raise Exception(msg)
            elif isinstance(value, float):
                return "float"
            else:
                raise Exception(self.err_prefix(value_node) + f"Unsupported constant value type: {value}")
        elif isinstance(value_node, ast.UnaryOp):
            if not (isinstance(value_node.op, ast.USub) or isinstance(value_node.op, ast.UAdd)):
                msg = self.exception_message(value_node, "Only +/- unary operators supported.")
                raise Exception(msg)
            return self.get_type_from_value(value_node.operand)
        elif isinstance(value_node, ast.Name):
            target = self.scoped_sym(value_node.id)
            return self.find_type(target)
        elif isinstance(value_node, ast.BinOp):
            l_type = self.get_type_from_value(value_node.left)
            r_type = self.get_type_from_value(value_node.right)
            if l_type != r_type:
                msg = self.exception_message(value_node, "We do not support different types on binary operators.")
                raise Exception(msg)
            return l_type
        elif isinstance(value_node, ast.List) or isinstance(value_node, ast.Tuple):
            list_size = len(value_node.elts)
            if list_size == 0:
                raise Exception(
                    self.err_prefix(value_node)
                    + "We are unable to handle empty lists, yet"
                )
            el0_type = self.get_type_from_value(value_node.elts[0])
            if not all(
                [self.get_type_from_value(x) == el0_type for x in value_node.elts]
            ):
                msg = self.exception_message(
                    value_node, "Only homogeneous lists and tuples are supported."
                )
                raise Exception(msg)
            return f"list:{list_size}:{el0_type}"
        else:
            msg = self.exception_message(
                value_node,
                f"Cannot obtain type information from unexpected node of type {value_node}",
            )
            raise Exception(msg)

    def add_symbol_to_scope(self, symbol, scope=None):
        if scope is None:
            this_scope = self.current_scope()
        else:
            this_scope = scope
        scope_symbols = self.symbols.get(this_scope, set())
        scope_symbols.add(symbol)
        self.symbols[this_scope] = scope_symbols

    def is_known_in_scope(self, symbol, scope=None):
        if scope is None:
            this_scope = self.current_scope()
        else:
            this_scope = scope
        return symbol in self.symbols.get(this_scope, set())

    def is_known_global(self, symbol):
        return self.is_known_in_scope(symbol, self.current_scope())

    def add_scoped_symbol_type(self, s_name, s_type, node):
        scoped_sym = self.scoped_sym(s_name)
        if scoped_sym in self.types:
            msg = self.exception_message(
                node, f"Symbol {s_name} already has a type associated with it,"
            )
            raise Exception(msg)
        self.types[scoped_sym] = s_type

    def set_func_ret_type(self, symbol, new_type):
        assert symbol in self.types
        assert self.types[symbol] == "func"
        self.types[symbol] = f"func:{new_type}"

    def handle_annotated_variable(self, var_name, var_type, node):
        """An annotated assignment is local by definition"""
        scoped_target = self.scoped_sym(var_name)
        known_type = self.types.get(scoped_target, var_type)
        if known_type != var_type:
            msg = self.exception_message(
                node,
                f"Variable {var_name} annotated as being of type {var_type} "
                f"but it is already known as being of type {known_type}",
            )
            raise Exception(msg)
        if self.is_known_in_scope(var_name):
            msg = self.exception_message(
                node,
                f"Variable {var_name} is already known in scope {self.current_scope()}",
            )
            raise Exception(msg)
        self.add_symbol_to_scope(scoped_target)
        self.add_scoped_symbol_type(scoped_target, var_type, node)

    def find_local_syms(self, scope):
        scope_syms = self.symbols.get(scope, set())
        return set([x for x in scope_syms if x.startswith(scope)])

    def find_type(self, symbol):
        if symbol in self.types:
            return self.types[symbol]
        elif self.unscoped_sym(symbol) in self.types:
            return self.types[self.unscoped_sym(symbol)]
        else:
            raise Exception(
                f"Trying to find type for {symbol=} but it cannot be found."
            )

    def find_ret_type(self, scoped_func_name):
        stored_type = self.find_type(scoped_func_name)
        if stored_type == "func":
            return "void"
        elif ":" in stored_type:
            parts = stored_type.split(":")
            assert len(parts) == 2
            assert parts[0] == "func"
            return parts[1]
        else:
            raise Exception(
                f"Internal error trying to find ret type for {scoped_func_name}"
            )

    @staticmethod
    def unscoped_sym(symbol):
        if symbol.find("::") >= 0:
            parts = symbol.split("::")
            return parts[-1]
        else:
            return symbol

    def visit_Global(self, node):
        this_scope = self.current_scope()
        this_scope_symbols = self.symbols.get(this_scope, set())
        this_scope_symbols.update(node.names)
        self.symbols[this_scope] = this_scope_symbols

    def visit_AnnAssign(self, node):
        """Assignment with annotation"""
        self.handle_annotated_variable(node.target.id, node.annotation.id, node)

    def visit_Assign(self, node):
        """Assignment without annotation:
           Check if symbol is new or existing.
           If existing, try to check if the type is the same. In C we can't change types..."""
        for target in node.targets:
            tgt_id = target.id
            tgt_ty = self.get_type_from_value(node.value)
            if self.is_known_global(tgt_id):
                scoped_target = tgt_id
            else:
                scoped_target = self.scoped_sym(tgt_id)
            if scoped_target not in self.types:  # First time we see this, so store it
                self.add_scoped_symbol_type(scoped_target, tgt_ty, node)
                self.add_symbol_to_scope(scoped_target)
            known_type = self.types[scoped_target]
            assert known_type == tgt_ty

    def visit_FunctionDef(self, node):
        func_name = node.name

        # Register this function, first try to find return type
        if node.returns is not None:
            self.add_scoped_symbol_type(func_name, f"func:{node.returns.id}", node)
        else:
            self.add_scoped_symbol_type(
                func_name, "func", node
            )  # In this case we will try in visit_Return

        self.enter_scope(func_name)
        self.generic_visit(node)  # visit all children of this node
        self.exit_scope(func_name)

    def visit_Return(self, node):
        if node.value is None:
            type_of_this_return = "void"
        else:
            type_of_this_return = self.get_type_from_value(node.value)
        known_type = self.find_type(
            self.current_scope()
        )  # current scope is exactly our function...
        if known_type == "func":
            self.set_func_ret_type(self.current_scope(), type_of_this_return)
        else:
            if f"func:{type_of_this_return}" != known_type:
                show_known_type = known_type.split(":")[1]
                raise Exception(
                    f"In line {node.lineno}: Function should return '{show_known_type}' "
                    f"but this return statement is of type '{type_of_this_return}'"
                )

    def visit_arg(self, node):
        arg_name = node.arg
        if node.annotation is not None:
            arg_type = node.annotation.id
            self.handle_annotated_variable(arg_name, arg_type, node)
        else:  # So we know the argument, but not its type... We'll store it as a symbol but not its type
            self.add_symbol_to_scope(self.scoped_sym(arg_name))

    def visit(self, node):
        """Visit a node."""
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        # if visitor == self.generic_visit:
        #    print(f"Would call {method} {node!r}")
        return visitor(node)
