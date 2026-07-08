import os
import shutil
import subprocess
import threading
from pathlib import Path

ODM_IMAGE = "opendronemap/odm:3.5.4"

# ponytail: single lock serializes ODM runs (matches "one project at a time"
# decision). Swap for a real task queue if concurrent projects are needed.
_odm_lock = threading.Lock()


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
    rgb_dir = project_dir / "rgb"

    with _odm_lock:
        subprocess.run(_docker_cmd(project_dir), check=True)

    products_dir = project_dir / "products"
    products_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        rgb_dir / "odm_orthophoto" / "odm_orthophoto.tif",
        products_dir / "rgb_orthomosaic.tif",
    )
