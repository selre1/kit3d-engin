import ifcopenshell.util.element

def extract_parents(ifc_object):
    parents = []
    current = ifc_object

    while current:
        parent = ifcopenshell.util.element.get_container(current)
        if parent:
            parents.append({
                "id": parent.GlobalId,
                "ifcClass": parent.is_a()
            })
        current = parent

    return parents