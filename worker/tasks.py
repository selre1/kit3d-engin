import logging
import os

from celery import chord
from celery.result import allow_join_result

from worker.celery_app import celery_app
from worker.core.status import CeleryState, JobStatus
from worker.db.repository import (
    get_ifc_classes_by_project,
    set_import_job_finished,
    set_import_job_started,
    set_tile_job_finished,
    set_tile_job_started,
    upsert_tileset_status,
    upsert_tilesets_pending,
)
from worker.jobs.ifc_import import IfcImportJob
from worker.jobs.tile_generator import run_3dtiles
from worker.utils.task_utils import format_class_name

logger = logging.getLogger(__name__)


def db_call(fn, *args):
    try:
        fn(*args)
    except Exception:
        logger.exception("db_call failed: %s", getattr(fn, "__name__", str(fn)))



def _build_tile_options(
    project_id: str,
    tile_job_id: str | None,
    ifc_class: str,
    class_output: str,
    default_tileset_url: str,
    base_max_features,
    base_geometric_error,
) -> dict:
    class_query = (
        "project_id = '{project_id}' AND ifc_class = '{ifc_class}'"
    ).format(project_id=project_id, ifc_class=ifc_class)

    max_features = base_max_features
    geometric_error = base_geometric_error
    if ifc_class.lower() == "ifcbuildingelementproxy":
        geometric_error = 16
        max_features = 150

    tile_options = {
        "query": class_query,
        "output": class_output,
        "tileJobId": tile_job_id,
        "ifc_class": ifc_class,
        "tileset_url": default_tileset_url,
    }
    if max_features is not None:
        tile_options["max_features_per_tile"] = max_features
    if geometric_error is not None:
        tile_options["geometric_error"] = geometric_error

    return tile_options


@celery_app.task(name="import_ifc", queue="import_jobs", acks_late=False)
def import_ifc_task(payload):
    job_id = payload.get("jobId")

    if job_id:
        db_call(set_import_job_started, job_id)

    try:
        job = IfcImportJob(payload)
        job.run()
        if job_id:
            db_call(set_import_job_finished, job_id, JobStatus.DONE)
        return {
            "job_id": job_id,
            "status": JobStatus.DONE.value,
        }
    except Exception:
        if job_id:
            db_call(set_import_job_finished, job_id, JobStatus.FAILED)
        raise


@celery_app.task(name="run_generate_3dtiles", queue="tile_jobs", acks_late=False)
def run_generate_3dtiles(options):
    tile_job_id = options.get("tileJobId")
    ifc_class = options.get("ifc_class")
    default_tileset_url = options.get("tileset_url")

    if tile_job_id and ifc_class and default_tileset_url:
        db_call(
            upsert_tileset_status,
            tile_job_id,
            ifc_class,
            default_tileset_url,
            JobStatus.RUNNING,
            None,
        )

    try:
        generated = run_3dtiles(options)
        tileset_url = generated.get("tileset_url") or default_tileset_url
        if tile_job_id and ifc_class and tileset_url:
            db_call(
                upsert_tileset_status,
                tile_job_id,
                ifc_class,
                tileset_url,
                JobStatus.DONE,
                None,
            )
        return {
            "ifc_class": ifc_class,
            "tileset_url": tileset_url,
            "status": JobStatus.DONE.value,
            "error": None,
        }
    except Exception as exc:
        if tile_job_id and ifc_class and default_tileset_url:
            db_call(
                upsert_tileset_status,
                tile_job_id,
                ifc_class,
                default_tileset_url,
                JobStatus.FAILED,
                str(exc),
            )
        return {
            "ifc_class": ifc_class,
            "tileset_url": default_tileset_url,
            "status": JobStatus.FAILED.value,
            "error": str(exc),
        }


@celery_app.task(name="convert_3dtiles_results", queue="tile_jobs", acks_late=False)
def convert_3dtiles_results(class_results, context):
    tile_job_id = context.get("tile_job_id")
    project_id = context.get("project_id")
    output_dir = context.get("output_dir")
    total_classes = int(context.get("total_classes") or 0)

    done_classes = 0
    failed_classes = 0
    tilesets = []

    for item in class_results or []:
        payload = item if isinstance(item, dict) else {}
        status = payload.get("status")
        if status == JobStatus.DONE.value:
            done_classes += 1
        else:
            failed_classes += 1
            status = JobStatus.FAILED.value

        tilesets.append(
            {
                "ifc_class": payload.get("ifc_class"),
                "tileset_url": payload.get("tileset_url"),
                "status": status,
                "error": payload.get("error"),
            }
        )

    final_status = JobStatus.FAILED if failed_classes > 0 else JobStatus.DONE

    if tile_job_id:
        db_call(
            set_tile_job_finished,
            tile_job_id,
            final_status,
            total_classes,
            done_classes,
            failed_classes,
            output_dir,
        )

    return {
        "status": final_status.value,
        "tile_job_id": tile_job_id,
        "project_id": project_id,
        "tile_path": output_dir,
        "total_classes": total_classes,
        "done_classes": done_classes,
        "failed_classes": failed_classes,
        "tilesets": tilesets,
    }


@celery_app.task(name="run_3dtiles_by_class", queue="tile_jobs", bind=True, acks_late=False)
def run_3dtiles_by_class(self, options):
    project_id = options["projectId"]
    tile_job_id = options.get("tileJobId")
    opts = options.get("options", {})

    assets_root = os.getenv("ASSETS_DIR", "assets")
    job_folder = tile_job_id or "manual"
    output_dir = os.path.join(assets_root, "model", project_id, "tiles", job_folder)

    total_classes = 0

    if tile_job_id:
        db_call(set_tile_job_started, tile_job_id)

    try:
        classes = options.get("ifc_classes")
        if not classes:
            classes = get_ifc_classes_by_project(project_id)

        if not classes:
            if tile_job_id:
                db_call(set_tile_job_finished, tile_job_id, JobStatus.DONE, 0, 0, 0, output_dir)
            return {
                "status": JobStatus.DONE.value,
                "tile_job_id": tile_job_id,
                "project_id": project_id,
                "tile_path": output_dir,
                "total_classes": 0,
                "done_classes": 0,
                "failed_classes": 0,
                "tilesets": [],
            }

        base_max_features = opts.get("max_features_per_tile")
        base_geometric_error = opts.get("geometric_error")
        total_classes = len(classes)

        self.update_state(
            state=CeleryState.PROGRESS.value,
            meta={
                "status": JobStatus.RUNNING.value,
                "total_classes": total_classes,
                "done_classes": 0,
                "failed_classes": 0,
                "tile_path": output_dir,
                "tilesets": [],
            },
        )

        class_groups = []
        pending_tilesets: list[tuple[str, str]] = []

        for ifc_class in classes:
            class_name = format_class_name(ifc_class)
            class_output = os.path.join(output_dir, class_name)
            tileset_rel = os.path.relpath(class_output, assets_root).replace("\\", "/")
            default_tileset_url = f"/tiles/{tileset_rel}/tileset.json"

            if tile_job_id:
                pending_tilesets.append((ifc_class, default_tileset_url))

            tile_options = _build_tile_options(
                project_id=project_id,
                tile_job_id=tile_job_id,
                ifc_class=ifc_class,
                class_output=class_output,
                default_tileset_url=default_tileset_url,
                base_max_features=base_max_features,
                base_geometric_error=base_geometric_error,
            )

            class_groups.append(
                run_generate_3dtiles.s(tile_options).set(queue="tile_jobs")
            )

        if tile_job_id and pending_tilesets:
            db_call(upsert_tilesets_pending, tile_job_id, pending_tilesets)

        callback_result = convert_3dtiles_results.s(
            {
                "tile_job_id": tile_job_id,
                "project_id": project_id,
                "output_dir": output_dir,
                "total_classes": total_classes,
            }
        ).set(queue="tile_jobs")

        result = chord(class_groups)(callback_result)

        with allow_join_result():
            final_payload = result.get(propagate=True)

        if not isinstance(final_payload, dict):
            raise RuntimeError("invalid chord callback payload")

        return final_payload
    except Exception:
        if tile_job_id:
            db_call(
                set_tile_job_finished,
                tile_job_id,
                JobStatus.FAILED,
                total_classes,
                0,
                total_classes if total_classes > 0 else 0,
                output_dir,
            )
        raise
