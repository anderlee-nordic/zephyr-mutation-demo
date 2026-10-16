"""
Example external plugin: replace an enum constant with another one.

Not built in; load it with:
    python3 mutate.py --plugin plugins/enum_swap.py

It uses the prepare() hook to collect the candidate constants from the
file first, then mutates each use in an assignment or ==/!= comparison.
Case labels are left alone (swapping them only produces duplicate-case
compile errors).
"""

from mutators.core import MutationOperator, replace_node, text


class EnumConstantReplacement(MutationOperator):
    name = "ECR"
    description = "enum constant replacement (identifiers with PREFIX)"
    node_types = ("identifier",)

    PREFIX = "ST_"  # thermostat states; change for your own code

    def prepare(self, tree, src):
        found = set()
        stack = [tree.root_node]
        while stack:
            n = stack.pop()
            if n.type == "identifier" and text(n).startswith(self.PREFIX):
                found.add(text(n))
            stack.extend(n.children)
        self.constants = sorted(found)

    def mutate(self, node, src):
        name = text(node)
        if name not in self.constants:
            return
        parent = node.parent
        in_assignment = parent.type == "assignment_expression" and \
            parent.child_by_field_name("right") == node
        in_compare = parent.type == "binary_expression" and \
            text(parent.child_by_field_name("operator")) in ("==", "!=")
        if not (in_assignment or in_compare):
            return
        for other in self.constants:
            if other != name:
                yield replace_node(node, other, f"{name} -> {other}")
