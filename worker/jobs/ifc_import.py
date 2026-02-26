import json
from dotenv import load_dotenv

from worker.db.connection import get_db_connection
from worker.ifc.loader import IfcLoader
from worker.ifc.parser import IfcParser
from worker.utils.logger import setup_logger

from worker.ifc.extractor.properties import extract_properties
from worker.ifc.extractor.geometry import GeometryExtractor
from worker.ifc.extractor.material import MaterialProcessor

from worker.db.writer import DBWriter
from typing import List


class IfcImportJob:
    def __init__(self, payload):
        self.payload = payload
        self.ifc_path = payload["ifcPath"]
        self.project_id = payload["projectId"]
        self.job_id = payload["jobId"]
        self.logger = setup_logger(self.project_id, self.job_id)

    def run(self):
        conn = get_db_connection()
        conn.autocommit = False
        writer = DBWriter(conn, self.logger)

        try:
            self.logger.info(f"Job start: {self.job_id}")

            loader = IfcLoader(self.ifc_path)
            ifc_model = loader.load()

            parser = IfcParser(ifc_model, self.logger)

            geometry_extractor = GeometryExtractor(self.logger)
            material_processor = MaterialProcessor(self.logger)

            objects_processed = 0
            object_rows = []
            batch_items = []
            batch_size = 500
            skipped_no_geom = 0

            extract_element_data = self.extract_element_data
            flush_batch = self.flush_batch
            for el, _ in parser.iter_elements():
                result = extract_element_data(
                    el=el,
                    geometry_extractor=geometry_extractor,
                    material_processor=material_processor,
                )
                if not result:
                    skipped_no_geom += 1
                    continue

                object_row, batch_item = result
                object_rows.append(object_row)
                batch_items.append(batch_item)

                if len(object_rows) >= batch_size:
                    flush_batch(
                        writer=writer,
                        object_rows=object_rows,
                        batch_items=batch_items,
                    )
                objects_processed += 1

            if object_rows:
                flush_batch(
                    writer=writer,
                    object_rows=object_rows,
                    batch_items=batch_items,
                )

            self.logger.info(
                f"Total objects processed: {objects_processed}, "
                f"skipped_no_geom: {skipped_no_geom}"
            )

            conn.commit()

            self.logger.info(f"Job done: {self.job_id}")

        except Exception:
            conn.rollback()
            self.logger.exception("Job failed, rollback")
            raise

        finally:
            conn.close()

    def extract_element_data(
        self,
        el,
        geometry_extractor,
        material_processor,
    ):
        guid = el.GlobalId
        ifc_class = el.is_a()
        properties = extract_properties(el)

        geom_data = geometry_extractor.extract(el)
        if not geom_data:
            return None

        material_parts = material_processor.process(geom_data)
        settings = properties.get("설정") or {}
        object_color = settings.get("COLOR")

        shaders = self.build_mesh_shaders(
            tri_count=geom_data["tri_count"],
            material_parts=material_parts,
            material_cache=material_processor.material_cache,
        )
        shaders_json = json.dumps(shaders)

        object_row = (
            guid,
            self.job_id,
            self.project_id,
            ifc_class,
            json.dumps(properties),
            object_color,
        )
        batch_item = {
            "guid": guid,
            "geom_wkb": geom_data["geom_wkb"],
            "shaders_json": shaders_json,
        }
        return object_row, batch_item

    def flush_batch(self, writer, object_rows, batch_items):
        guid_to_id = writer.upsert_ifc_objects(object_rows)
        mesh_rows = []
        for item in batch_items:
            ifc_object_id = guid_to_id[item["guid"]]
            mesh_rows.append((
                ifc_object_id,
                item["geom_wkb"],
                item["shaders_json"],
            ))
        writer.upsert_ifc_meshes(mesh_rows)
        self.logger.info(f"DB flush done: size={len(object_rows)}")
        object_rows.clear()
        batch_items.clear()

    def build_mesh_shaders(
        self,
        tri_count: int,
        material_parts,
        material_cache,
        default_hex="#D3D3D3FF"
    ):
        basecolors = [default_hex] * tri_count
        rgba_to_hex = self.rgba_to_hex
        material_cache_local = material_cache
        hex_cache = {}

        for part in material_parts:
            mat_index = part["material_index"]
            face_indices = part["face_indices"]

            hexcolor = hex_cache.get(mat_index)
            if hexcolor is None:
                rgba = material_cache_local[mat_index]["color"]
                hexcolor = rgba_to_hex(rgba)
                hex_cache[mat_index] = hexcolor

            for idx in face_indices:
                if 0 <= idx < tri_count:
                    basecolors[idx] = hexcolor

        return {
            "EmissiveColors": basecolors,
            "PbrMetallicRoughness": {
                "BaseColors": basecolors
            }
        }
        
    def rgba_to_hex(self, rgba: List[float]) -> str:
        def to2(x: float) -> str:
            return f"{int(max(0, min(1, x)) * 255):02X}"

        r, g, b, a = rgba
        return "#" + to2(r) + to2(g) + to2(b) + to2(a)
