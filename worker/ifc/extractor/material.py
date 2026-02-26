import numpy as np

class MaterialProcessor:
    def __init__(self, logger):
        self.logger = logger
        self.material_cache = []  # project-wide material pool
        self._material_index_map = {}

    def get_material_index(self, color):
        """
        color: [r, g, b, a] (0~1)
        """
        key = tuple(color)
        cached = self._material_index_map.get(key)
        if cached is not None:
            return cached

        self.material_cache.append({
            "color": color
        })
        idx = len(self.material_cache) - 1
        self._material_index_map[key] = idx
        return idx

    def process(self, geom_data):
        """
        geom_data:
          {
            tri_count,
            materials,
            material_ids
          }
        """
        materials = geom_data.get("materials")
        mat_ids = geom_data.get("material_ids")

        if not materials or mat_ids is None:
            return [{
                "material_index": self.get_material_index([0.8, 0.8, 0.8, 1]),
                "face_indices": list(range(geom_data["tri_count"]))
            }]

        if hasattr(mat_ids, "ravel"):
            mat_ids = mat_ids.ravel()
        else:
            mat_ids = np.asarray(mat_ids).reshape(-1)

        face_indices_by_mid = {}
        for face_idx, mid in enumerate(mat_ids):
            face_indices_by_mid.setdefault(int(mid), []).append(face_idx)

        parts = []
        get_material_index = self.get_material_index
        materials_len = len(materials)
        fallback = materials[0]
        for mid, face_indices in face_indices_by_mid.items():
            src = materials[mid] if mid < materials_len else fallback
            color = [
                src.diffuse.r(),
                src.diffuse.g(),
                src.diffuse.b(),
                1
            ]
            mat_index = get_material_index(color)
            parts.append({
                "material_index": mat_index,
                "face_indices": face_indices
            })

        return parts
