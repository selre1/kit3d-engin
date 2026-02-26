from worker.db.connection import get_db_connection


def update_job_status(job_id, status):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                if status == "RUNNING":
                    cur.execute(
                        "UPDATE import_job SET status=%s, started_at=now() WHERE job_id=%s",
                        (status, job_id),
                    )
                elif status in ("DONE", "FAILED"):
                    cur.execute(
                        "UPDATE import_job SET status=%s, finished_at=now() WHERE job_id=%s",
                        (status, job_id),
                    )
    finally:
        conn.close()


def init_tile_job_counts(tile_job_id, total_classes, output_dir):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tile_job
                    SET status=%s,
                        started_at=now(),
                        total_classes=%s,
                        done_classes=0,
                        failed_classes=0,
                        tile_path=%s
                    WHERE tile_job_id=%s
                    """,
                    ("RUNNING", total_classes, output_dir,tile_job_id),
                )
    finally:
        conn.close()


def update_tile_job_progress(tile_job_id, success):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                if success:
                    cur.execute(
                        """
                        UPDATE tile_job
                        SET done_classes = done_classes + 1
                        WHERE tile_job_id=%s
                        RETURNING total_classes, done_classes, failed_classes
                        """,
                        (tile_job_id,),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE tile_job
                        SET failed_classes = failed_classes + 1
                        WHERE tile_job_id=%s
                        RETURNING total_classes, done_classes, failed_classes
                        """,
                        (tile_job_id,),
                    )
                row = cur.fetchone()
                if not row:
                    return
                total_classes, done_classes, failed_classes = row
                if total_classes is None:
                    return
                if done_classes + failed_classes >= total_classes:
                    status = "FAILED" if failed_classes > 0 else "DONE"
                    cur.execute(
                        "UPDATE tile_job SET status=%s, finished_at=now() WHERE tile_job_id=%s",
                        (status, tile_job_id),
                    )
    finally:
        conn.close()


def get_ifc_classes_by_project(project_id):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ifc_class
                    FROM ifc_object
                    WHERE project_id = %s
                    ORDER BY ifc_class
                    """,
                    (project_id,),
                )
                return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def upsert_tileset_status(tile_job_id, ifc_class, tileset_url, status, error=None):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tileset
                        (tile_job_id, ifc_class, tileset_url, status, error, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (tile_job_id, ifc_class)
                    DO UPDATE SET
                        tileset_url = EXCLUDED.tileset_url,
                        status = EXCLUDED.status,
                        error = EXCLUDED.error,
                        updated_at = now()
                    """,
                    (tile_job_id, ifc_class, tileset_url, status, error),
                )
    finally:
        conn.close()
