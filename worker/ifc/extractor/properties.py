def extract_properties(ifc_object):
    props = {}
    for rel in ifc_object.IsDefinedBy or []:
        pset = getattr(rel, "RelatingPropertyDefinition", None)
        if not pset or not pset.is_a("IfcPropertySet"):
            continue

        group = props.setdefault(pset.Name, {})
        for p in pset.HasProperties:
            if p.is_a("IfcPropertySingleValue") and p.NominalValue:
                group[p.Name] = p.NominalValue.wrappedValue

    return props
