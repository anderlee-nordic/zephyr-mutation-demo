from mutators.core import MutationOperator, replace_operator, text


class ArithmeticOperatorReplacement(MutationOperator):
    name = "AOR"
    description = "arithmetic operators: + <-> -, * <-> /"
    node_types = ("binary_expression",)

    TABLE = {"+": ["-"], "-": ["+"], "*": ["/"], "/": ["*"]}

    def mutate(self, node, src):
        op = text(node.child_by_field_name("operator"))
        for repl in self.TABLE.get(op, []):
            yield replace_operator(node, repl)
