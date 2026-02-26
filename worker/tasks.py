import os
import subprocess
from worker.celery_app import celery_app
from worker.jobs.ifc_import import IfcImportJob
from worker.db.repository import (
    get_ifc_classes_by_project,
    init_tile_job_counts,
    update_job_status,
    update_tile_job_progress,
    upsert_tileset_status,
)
from worker.utils.task_utils import (
    format_class_name, 
    draco_compress_glb,
    update_tileset_asset
)

@celery_app.task(name="import_ifc", queue="import_jobs", acks_late=False)
def import_ifc_task(payload):
    job_id = payload.get("jobId")
    if job_id:
        update_job_status(job_id, "RUNNING")
    job = IfcImportJob(payload)
    try:
        job.run()
        if job_id:
            update_job_status(job_id, "DONE")
    except Exception:
        if job_id:
            update_job_status(job_id, "FAILED")
        raise


@celery_app.task(name="run_generate_3dtiles", queue="tile_jobs", acks_late=False)
def run_generate_3dtiles(options):
    tile_job_id = options.get("tileJobId")
    ifc_class = options.get("ifc_class")
    tileset_url = options.get("tileset_url")
    db_host = os.getenv("DB_HOST", "localhost")
    db_user = os.getenv("DB_USER", "postgres")
    db_name = os.getenv("DB_NAME", "tile_worker")
    db_port = os.getenv("DB_PORT", "5432")

    env = os.environ.copy()
    if os.getenv("PGPASSWORD"):
        env["PGPASSWORD"] = os.getenv("PGPASSWORD")
    elif os.getenv("DB_PASSWORD"):
        env["PGPASSWORD"] = os.getenv("DB_PASSWORD")

    max_features_per_tile = options.get("max_features_per_tile")
    if max_features_per_tile is None:
        max_features_per_tile = 500
    geometric_error = options.get("geometric_error")
    if geometric_error is None:
        geometric_error = 50

    if not tileset_url:
        output_hint = options.get("output")
        if output_hint:
            assets_root = os.getenv("ASSETS_DIR", "assets")
            try:
                tileset_rel = os.path.relpath(output_hint, assets_root).replace("\\", "/")
                tileset_url = f"/tiles/{tileset_rel}/tileset.json"
            except ValueError:
                tileset_url = None

    if tile_job_id and ifc_class and tileset_url:
        upsert_tileset_status(tile_job_id, ifc_class, tileset_url, "RUNNING", None)

    cmd = [
        os.getenv("PG2B3DM_BIN", "pg2b3dm"),
        "-h",
        db_host,
        "-U",
        db_user,
        "-p",
        str(db_port),
        "-c",
        options.get("geom_column", "geom"),
        "-d",
        db_name,
        "-t",
        options.get("table", "view_3dtiles"),
        "-a",
        options.get("attrs", "guid,ifc_class,color,props"),
        "--shaderscolumn",
        options.get("shaders_column", "shaders"),
        "-r",
        options.get("replace", "REPLACE"),
        "--use_implicit_tiling",
        str(options.get("use_implicit_tiling", "true")).lower(),
        "--max_features_per_tile",
        str(max_features_per_tile),
        "-g",
        str(geometric_error),
        "-o",
        options.get("output", "output"),
    ]
    extra_query = options.get("query")
    
    if extra_query:
        cmd.extend(["-q", extra_query])
        
    try:
        subprocess.run(cmd, check=True, env=env)

        output_path = options.get("output", "output")
        if output_path.lower().endswith(".json"):
            tileset_path = output_path
            tileset_dir = os.path.dirname(output_path)
        else:
            tileset_path = os.path.join(output_path, "tileset.json")
            tileset_dir = output_path

        draco_compress_glb(tileset_dir, env=env)
        update_tileset_asset(tileset_path)
    except Exception as exc:
        if tile_job_id:
            update_tile_job_progress(tile_job_id, success=False)
        if tile_job_id and ifc_class and tileset_url:
            upsert_tileset_status(tile_job_id, ifc_class, tileset_url, "FAILED", str(exc))
        raise
    
    if tile_job_id:
        update_tile_job_progress(tile_job_id, success=True)
    if tile_job_id and ifc_class and tileset_url:
        upsert_tileset_status(tile_job_id, ifc_class, tileset_url, "DONE", None)
        
    return output_path


@celery_app.task(name="run_3dtiles_by_class", queue="tile_jobs", acks_late=False)
def run_3dtiles_by_class(options):
    project_id = options["projectId"]
    tile_job_id = options.get("tileJobId")
    opts = options.get("options", {})
    

    assets_root = os.getenv("ASSETS_DIR", "assets")
    output_dir = os.path.join(assets_root, project_id, "tiles", tile_job_id)

    classes = options.get("ifc_classes")
    if not classes:
        classes = get_ifc_classes_by_project(project_id)

    if not classes:
        if tile_job_id:
            init_tile_job_counts(tile_job_id, 0, output_dir)
        return
    
    if tile_job_id:
        init_tile_job_counts(tile_job_id, len(classes), output_dir)

    base_max_features = opts.get("max_features_per_tile")
    base_geometric_error = opts.get("geometric_error")

    for ifc_class in classes:
        class_name = format_class_name(ifc_class)
        class_output = os.path.join(output_dir, class_name)
        tileset_rel = os.path.relpath(class_output, assets_root).replace("\\", "/")
        tileset_url = f"/tiles/{tileset_rel}/tileset.json"
        class_query = (
            "project_id = '{project_id}' AND ifc_class = '{ifc_class}'"
        ).format(project_id=project_id,ifc_class=ifc_class)

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
            "tileset_url": tileset_url,
        }
        if max_features is not None:
            tile_options["max_features_per_tile"] = max_features
        if geometric_error is not None:
            tile_options["geometric_error"] = geometric_error
        if tile_job_id:
            upsert_tileset_status(tile_job_id, ifc_class, tileset_url, "PENDING", None)
        run_generate_3dtiles.delay(tile_options)
