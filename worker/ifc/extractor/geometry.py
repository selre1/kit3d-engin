import numpy as np
import ifcopenshell.geom as geom
from shapely.geometry import Polygon, MultiPolygon

class GeometryExtractor:
    def __init__(self, logger):
        self.logger = logger
        self.settings = geom.settings()
        self.settings.set(self.settings.USE_WORLD_COORDS, True)
        self.settings.set(self.settings.APPLY_DEFAULT_MATERIALS, True)

    def extract(self, ifc_object):
        if not ifc_object.Representation:
            return None

        shape = geom.create_shape(self.settings, ifc_object)

        verts = np.reshape(shape.geometry.verts, (-1, 3))
        faces = np.reshape(shape.geometry.faces, (-1, 3))
        if len(faces) == 0:
            return None

        polygons = [
            Polygon([
                tuple(verts[i0]),
                tuple(verts[i1]),
                tuple(verts[i2])
            ])
            for i0, i1, i2 in faces
        ]
        geom_mp = MultiPolygon(polygons)
        return {
            "tri_count": len(faces),
            "geom_wkb": geom_mp.wkb,
            "materials": getattr(shape.geometry, "materials", None),
            "material_ids": getattr(shape.geometry, "material_ids", None),
        }
