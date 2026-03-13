import os
import subprocess

from worker.utils.task_utils import draco_compress_glb, update_tileset_asset


def _resolve_tileset_paths(output_path: str) -> tuple[str, str]:
    if output_path.lower().endswith(".json"):
        tileset_path = output_path
        tileset_dir = os.path.dirname(output_path)
    else:
        tileset_path = os.path.join(output_path, "tileset.json")
        tileset_dir = output_path
    return tileset_path, tileset_dir


def _compute_tileset_url(output_path: str, assets_root: str) -> str:
    if output_path.lower().endswith(".json"):
        rel = os.path.relpath(output_path, assets_root).replace("\\", "/")
        return f"/tiles/{rel}"
    rel = os.path.relpath(output_path, assets_root).replace("\\", "/")
    return f"/tiles/{rel}/tileset.json"


def run_3dtiles(options: dict) -> dict:
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

    output_path = options.get("output", "output")

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
        output_path,
    ]

    extra_query = options.get("query")
    if extra_query:
        cmd.extend(["-q", extra_query])

    subprocess.run(cmd, check=True, env=env)

    tileset_path, tileset_dir = _resolve_tileset_paths(output_path)
    draco_compress_glb(tileset_dir, env=env)
    update_tileset_asset(tileset_path)

    assets_root = os.getenv("ASSETS_DIR", "assets")
    tileset_url = options.get("tileset_url")
    if not tileset_url:
        try:
            tileset_url = _compute_tileset_url(output_path, assets_root)
        except ValueError:
            tileset_url = None

    return {
        "output_path": output_path,
        "tileset_url": tileset_url,
    }