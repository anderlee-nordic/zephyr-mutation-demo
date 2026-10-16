from mutators.core import MutationOperator, field_text, replace_node, text


class NegationRemoval(MutationOperator):
    name = "UOD"
    description = "unary operator deletion: !x -> x"
    node_types = ("unary_expression",)

    def mutate(self, node, src):
        if text(node.child_by_field_name("operator")) == "!":
            yield replace_node(node, field_text(node, "argument"), "remove !")
