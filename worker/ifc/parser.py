import ifcopenshell.util.element


class IfcParser:
    def __init__(self, ifc, logger):
        self.ifc = ifc
        self.logger = logger
        self.stats = {
            "total_elements": 0,
            "unique_guids": 0,
            "duplicate_guids": 0,
        }

    def iter_elements(self):
        seen = set()
        total = 0
        dup = 0

        for building in self.ifc.by_type("IfcBuilding"):
            for el in ifcopenshell.util.element.get_decomposition(building):
                total += 1
                guid = getattr(el, "GlobalId", None)
                if guid and guid in seen:
                    dup += 1
                    continue
                if guid:
                    seen.add(guid)
                yield el, building

        self.log_stats(total=total, unique=len(seen), dup=dup)

    def log_stats(self, total, unique, dup):
        self.stats["total_elements"] = total
        self.stats["unique_guids"] = unique
        self.stats["duplicate_guids"] = dup
        if dup:
            self.logger.warning(
                f"IFC parser duplicate GUIDs detected: total={total}, unique={unique}, dup={dup}"
            )
        else:
            self.logger.info(
                f"IFC parser GUID stats: total={total}, unique={unique}"
            )
