from mutators.core import MutationOperator, replace_operator, text


class RelationalOperatorReplacement(MutationOperator):
    name = "ROR"
    description = "relational/equality operators: boundary shift and negation"
    node_types = ("binary_expression",)

    # Selective ROR: the boundary shift catches off-by-one, the negation
    # catches a flipped condition; the other replacements add little.
    TABLE = {
        "<":  ["<=", ">="],
        "<=": ["<", ">"],
        ">":  [">=", "<="],
        ">=": [">", "<"],
        "==": ["!="],
        "!=": ["=="],
    }

    def mutate(self, node, src):
        op = text(node.child_by_field_name("operator"))
        for repl in self.TABLE.get(op, []):
            yield replace_operator(node, repl)
