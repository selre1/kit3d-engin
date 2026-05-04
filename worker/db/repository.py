from psycopg2.extras import execute_values

from worker.core.status import JobStatus
from worker.db.connection import get_db_connection


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


def set_import_job_started(job_id):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE import_job
                    SET status = %s,
                        started_at = COALESCE(started_at, NOW())
                    WHERE job_id = %s
                    """,
                    (JobStatus.RUNNING.value, job_id),
                )
    finally:
        conn.close()


def set_import_job_finished(job_id, status: JobStatus):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE import_job
                    SET status = %s, finished_at = NOW()
                    WHERE job_id = %s
                    """,
                    (status.value, job_id),
                )
    finally:
        conn.close()


def set_tile_job_started(tile_job_id):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tile_job
                    SET status = %s,
                        started_at = COALESCE(started_at, NOW())
                    WHERE tile_job_id = %s
                    """,
                    (JobStatus.RUNNING.value, tile_job_id),
                )
    finally:
        conn.close()


def upsert_tilesets_pending(tile_job_id, tilesets: list[tuple[str, str]]):
    if not tilesets:
        return

    rows = [
        (tile_job_id, ifc_class, tileset_url, JobStatus.PENDING.value, None)
        for ifc_class, tileset_url in tilesets
    ]

    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO tileset (tile_job_id, ifc_class, tileset_url, status, error)
                    VALUES %s
                    ON CONFLICT (tile_job_id, ifc_class)
                    DO UPDATE SET
                        tileset_url = EXCLUDED.tileset_url,
                        status = EXCLUDED.status,
                        error = EXCLUDED.error,
                        updated_at = NOW()
                    WHERE
                        tileset.tileset_url IS DISTINCT FROM EXCLUDED.tileset_url
                        OR tileset.status IS DISTINCT FROM EXCLUDED.status
                        OR tileset.error IS DISTINCT FROM EXCLUDED.error
                    """,
                    rows,
                    page_size=500,
                )
    finally:
        conn.close()


def upsert_tileset_status(
    tile_job_id,
    ifc_class,
    tileset_url,
    status: JobStatus,
    error,
):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tileset (tile_job_id, ifc_class, tileset_url, status, error)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (tile_job_id, ifc_class)
                    DO UPDATE SET
                        tileset_url = EXCLUDED.tileset_url,
                        status = EXCLUDED.status,
                        error = EXCLUDED.error,
                        updated_at = NOW()
                    WHERE
                        tileset.tileset_url IS DISTINCT FROM EXCLUDED.tileset_url
                        OR tileset.status IS DISTINCT FROM EXCLUDED.status
                        OR tileset.error IS DISTINCT FROM EXCLUDED.error
                    """,
                    (
                        tile_job_id,
                        ifc_class,
                        tileset_url,
                        status.value,
                        error,
                    ),
                )
    finally:
        conn.close()


def set_tile_job_finished(
    tile_job_id,
    status: JobStatus,
    total_classes,
    done_classes,
    failed_classes,
    tile_path,
):
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tile_job
                    SET status = %s,
                        total_classes = %s,
                        done_classes = %s,
                        failed_classes = %s,
                        tile_path = %s,
                        finished_at = NOW()
                    WHERE tile_job_id = %s
                    """,
                    (
                        status.value,
                        total_classes,
                        done_classes,
                        failed_classes,
                        tile_path,
                        tile_job_id,
                    ),
                )
    finally:
        conn.close()
