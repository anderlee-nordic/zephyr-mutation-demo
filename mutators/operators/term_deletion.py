from mutators.core import MutationOperator, field_text, replace_node, text


class TermDeletion(MutationOperator):
    name = "TERM"
    description = "conditional operand deletion: keep one side of && / ||"
    node_types = ("binary_expression",)

    def mutate(self, node, src):
        op = text(node.child_by_field_name("operator"))
        if op not in ("&&", "||"):
            return
        yield replace_node(node, field_text(node, "left"),
                           f"drop right of {op}")
        yield replace_node(node, field_text(node, "right"),
                           f"drop left of {op}")
