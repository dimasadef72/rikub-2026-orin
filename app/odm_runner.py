import os
import shutil
import subprocess
import threading
from pathlib import Path

ODM_IMAGE = "opendronemap/odm:3.5.4"

# ponytail: single lock serializes ODM runs (matches "one project at a time"
# decision). Swap for a real task queue if concurrent projects are needed.
_odm_lock = threading.Lock()


def _filter_d_images(images_dir: Path, rgb_images_dir: Path) -> None:
    rgb_images_dir.mkdir(parents=True, exist_ok=True)
    for f in images_dir.glob("*_D.JPG"):
        shutil.copy(f, rgb_images_dir / f.name)


def _docker_cmd(project_dir: Path) -> list:
    # -ti dropped from the original manual command: no tty available when
    # run from a background thread.
    return [
        "docker", "run", "--rm",
        "-u", f"{os.getuid()}:{os.getgid()}",
        "-w", "/datasets/rgb",
        "-v", f"{project_dir}:/datasets",
        ODM_IMAGE,
        "--project-path", "/datasets",
        "--max-concurrency", "2",
        "--fast-orthophoto",
        "rgb",
    ]


def run_odm_pipeline(project_dir: Path) -> None:
    images_dir = project_dir / "images"
    rgb_dir = project_dir / "rgb"
    rgb_images_dir = rgb_dir / "images"

    shutil.rmtree(rgb_dir, ignore_errors=True)
    _filter_d_images(images_dir, rgb_images_dir)

    with _odm_lock:
        subprocess.run(_docker_cmd(project_dir), check=True)

    products_dir = project_dir / "products"
    products_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        rgb_dir / "odm_orthophoto" / "odm_orthophoto.tif",
        products_dir / "rgb_orthomosaic.tif",
    )
