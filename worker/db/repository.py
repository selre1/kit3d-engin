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


def mark_import_job_finished(job_id, status: JobStatus):
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


def mark_tile_job_finished(
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