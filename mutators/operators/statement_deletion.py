from mutators.core import MutationOperator, replace_node


class StatementDeletion(MutationOperator):
    name = "SDL"
    description = "statement deletion: statements, breaks and declarations"
    node_types = ("expression_statement", "break_statement", "declaration")

    LABELS = {
        "expression_statement": "delete statement",
        "break_statement": "delete break",
        "declaration": "delete declaration",
    }

    def mutate(self, node, src):
        if node.parent.type in ("compound_statement", "case_statement"):
            yield replace_node(node, ";", self.LABELS[node.type])
