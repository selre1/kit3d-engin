import os

from worker.celery_app import celery_app
from worker.core.status import CeleryState, JobStatus
from worker.db.repository import (
    get_ifc_classes_by_project,
    mark_import_job_finished,
    mark_tile_job_finished,
)
from worker.jobs.ifc_import import IfcImportJob
from worker.jobs.tile_generator import run_generate_3dtiles
from worker.utils.task_utils import format_class_name


def db_call(fn, *args):
    try:
        fn(*args)
    except Exception:
        pass


@celery_app.task(name="import_ifc", queue="import_jobs", acks_late=False)
def import_ifc_task(payload):
    job_id = payload.get("jobId")

    try:
        job = IfcImportJob(payload)
        job.run()
        if job_id:
            db_call(mark_import_job_finished, job_id, JobStatus.DONE)
        return {
            "job_id": job_id,
            "status": JobStatus.DONE.value,
        }
    except Exception:
        if job_id:
            db_call(mark_import_job_finished, job_id, JobStatus.FAILED)
        raise


@celery_app.task(name="run_3dtiles_by_class", queue="tile_jobs", bind=True, acks_late=False)
def run_3dtiles_by_class(self, options):
    project_id = options["projectId"]
    tile_job_id = options.get("tileJobId")
    opts = options.get("options", {})

    assets_root = os.getenv("ASSETS_DIR", "assets")
    job_folder = tile_job_id or "manual"
    output_dir = os.path.join(assets_root, project_id, "tiles", job_folder)

    total_classes = 0
    done_classes = 0
    failed_classes = 0
    tilesets = []

    try:
        classes = options.get("ifc_classes")
        if not classes:
            classes = get_ifc_classes_by_project(project_id)

        if not classes:
            if tile_job_id:
                db_call(mark_tile_job_finished, tile_job_id, JobStatus.DONE, 0, 0, 0, output_dir)
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
                "done_classes": done_classes,
                "failed_classes": failed_classes,
                "tile_path": output_dir,
                "tilesets": tilesets,
            },
        )

        for ifc_class in classes:
            class_name = format_class_name(ifc_class)
            class_output = os.path.join(output_dir, class_name)
            tileset_rel = os.path.relpath(class_output, assets_root).replace("\\", "/")
            default_tileset_url = f"/tiles/{tileset_rel}/tileset.json"

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

            try:
                generated = run_generate_3dtiles(tile_options)
                tilesets.append(
                    {
                        "ifc_class": ifc_class,
                        "tileset_url": generated.get("tileset_url") or default_tileset_url,
                        "status": JobStatus.DONE.value,
                        "error": None,
                    }
                )
                done_classes += 1
            except Exception as exc:
                tilesets.append(
                    {
                        "ifc_class": ifc_class,
                        "tileset_url": default_tileset_url,
                        "status": JobStatus.FAILED.value,
                        "error": str(exc),
                    }
                )
                failed_classes += 1

            self.update_state(
                state=CeleryState.PROGRESS.value,
                meta={
                    "status": JobStatus.RUNNING.value,
                    "total_classes": total_classes,
                    "done_classes": done_classes,
                    "failed_classes": failed_classes,
                    "tile_path": output_dir,
                    "tilesets": tilesets,
                },
            )

        final_status = JobStatus.FAILED if failed_classes > 0 else JobStatus.DONE
        if tile_job_id:
            db_call(
                mark_tile_job_finished,
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
    except Exception:
        if tile_job_id:
            db_call(
                mark_tile_job_finished,
                tile_job_id,
                JobStatus.FAILED,
                total_classes,
                done_classes,
                failed_classes,
                output_dir,
            )
        raise