from psycopg2.extras import execute_values

class DBWriter:
    BATCH_SIZE = 1000

    def __init__(self,conn, logger):
        self.conn = conn
        self.logger = logger

    def upsert_ifc_objects(self, rows):
        if not rows:
            return {}
        with self.conn.cursor() as cur:
            result = {}
            for i in range(0, len(rows), self.BATCH_SIZE):
                batch = rows[i:i + self.BATCH_SIZE]
                execute_values(
                    cur,
                    """
                    INSERT INTO ifc_object (guid, job_id, project_id, ifc_class, properties, color)
                    VALUES %s
                    ON CONFLICT (project_id, guid) DO UPDATE
                    SET
                        job_id = EXCLUDED.job_id,
                        ifc_class = EXCLUDED.ifc_class,
                        properties = EXCLUDED.properties,
                        color = EXCLUDED.color
                    RETURNING ifc_object_id, guid
                    """,
                    batch,
                    page_size=len(batch),
                )
                result.update({guid: ifc_object_id for ifc_object_id, guid in cur.fetchall()})
            return result

    def upsert_ifc_meshes(self, rows):
        if not rows:
            return
        with self.conn.cursor() as cur:
            for i in range(0, len(rows), self.BATCH_SIZE):
                batch = rows[i:i + self.BATCH_SIZE]
                execute_values(
                    cur,
                    """
                    INSERT INTO ifc_mesh (ifc_object_id, geom, shaders)
                    VALUES %s
                    ON CONFLICT (ifc_object_id) DO UPDATE
                    SET
                        geom = EXCLUDED.geom,
                        shaders = EXCLUDED.shaders
                    """,
                    batch,
                    template="(%s, ST_Force3D(ST_SetSRID(ST_GeomFromWKB(%s), 5186)), %s::jsonb)"
                )
