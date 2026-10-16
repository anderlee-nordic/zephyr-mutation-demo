from mutators.core import MutationOperator, replace_node


class BooleanConstantReplacement(MutationOperator):
    name = "BCR"
    description = "boolean literals: true <-> false"
    node_types = ("true", "false")

    def mutate(self, node, src):
        flip = "false" if node.type == "true" else "true"
        yield replace_node(node, flip, f"{node.type} -> {flip}")
