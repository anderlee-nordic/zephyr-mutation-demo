from mutators.core import (MutationOperator, field_text, replace_node,
                           replace_operator, text)


class LogicalConnectorReplacement(MutationOperator):
    name = "LCR"
    description = "logical connectors: && <-> ||"
    node_types = ("binary_expression",)

    TABLE = {"&&": "||", "||": "&&"}

    def mutate(self, node, src):
        op = text(node.child_by_field_name("operator"))
        repl = self.TABLE.get(op)
        if repl is None:
            return
        if node.parent.type == "binary_expression":
            # && binds tighter than ||: swapping the inner operator of
            # "a && b && c" as plain text would regroup it, so add parens
            new = (f"({field_text(node, 'left')} {repl} "
                   f"{field_text(node, 'right')})")
            yield replace_node(node, new, f"{op} -> {repl}")
        else:
            yield replace_operator(node, repl)
