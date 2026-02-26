import json
import os
import re
import shutil
import subprocess


def format_class_name(value):
    if not value:
        return "class"
    stripped = re.sub(r"^Ifc", "", value)
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stripped)
    cleaned = cleaned.strip("_")
    return cleaned.lower() or "class"


def update_tileset_asset(tileset_path):
    with open(tileset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    asset = data.get("asset")
    if not isinstance(asset, dict):
        asset = {}
        data["asset"] = asset

    asset.pop("generator", None)
    asset["author"] = "BHB"

    with open(tileset_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def draco_compress_glb(tileset_dir, env=None):
    content_dir = os.path.join(tileset_dir, "content")
    if not os.path.isdir(content_dir):
        return

    gltf_bin = os.getenv("GLTF_PIPELINE_BIN")
    if gltf_bin:
        cmd_base = [gltf_bin]
    else:
        cmd_base = ["pnpm", "exec", "gltf-pipeline"]
    for root, _, files in os.walk(content_dir):
        for name in files:
            if name.lower().endswith(".glb"):
                in_path = os.path.join(root, name)
                subprocess.run(
                    cmd_base + [
                        "-i",
                        in_path,
                        "-o",
                        in_path,
                        "-d",
                        "--draco.compressionLevel",
                        "10",
                        "--draco.quantizePositionBits",
                        "18",
                        "--draco.quantizeGenericBits",
                        "12",
                        "--draco.quantizeNormalBits",
                        "10",
                    ],
                    check=True,
                    env=env,
                )