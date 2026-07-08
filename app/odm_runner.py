import os
import shutil
import subprocess
import threading
from pathlib import Path

ODM_IMAGE = "opendronemap/odm:3.5.4"

# ponytail: single lock serializes ODM runs (matches "one project at a time"
# decision). Swap for a real task queue if concurrent projects are needed.
_odm_lock = threading.Lock()


def _docker_cmd(project_dir: Path, dataset: str, extra_args: list = []) -> list:
    # -ti dropped from the original manual command: no tty available when
    # run from a background thread.
    return [
        "docker", "run", "--rm",
        "-u", f"{os.getuid()}:{os.getgid()}",
        "-w", f"/datasets/{dataset}",
        "-v", f"{project_dir}:/datasets",
        ODM_IMAGE,
        "--project-path", "/datasets",
        "--max-concurrency", "2",
        "--fast-orthophoto",
        *extra_args,
        dataset,
    ]


def _run_ndvi(ms_tif: Path, out_tif: Path) -> None:
    subprocess.run([
        "gdal_calc.py",
        "-A", str(ms_tif), "--A_band=3",
        "-B", str(ms_tif), "--B_band=1",
        "-C", str(ms_tif), "--C_band=5",
        f"--outfile={out_tif}",
        "--calc=where((C>0)&(A>0)&(B>0)&((A+B)>0.0001),"
        "clip((A.astype(float)-B)/maximum(A+B,0.0001),-1,1),-9999)",
        "--type=Float32",
        "--NoDataValue=-9999",
        "--overwrite",
    ], check=True)


def run_odm_pipeline(project_dir: Path) -> None:
    rgb_dir = project_dir / "rgb"
    ms_dir = project_dir / "ms"
    products_dir = project_dir / "products"
    products_dir.mkdir(parents=True, exist_ok=True)

    with _odm_lock:
        subprocess.run(_docker_cmd(project_dir, "rgb"), check=True)
    shutil.copy(
        rgb_dir / "odm_orthophoto" / "odm_orthophoto.tif",
        products_dir / "rgb_orthomosaic.tif",
    )

    ms_images_dir = ms_dir / "images"
    if ms_images_dir.exists() and any(ms_images_dir.iterdir()):
        with _odm_lock:
            subprocess.run(
                _docker_cmd(project_dir, "ms", ["--radiometric-calibration", "camera"]),
                check=True,
            )
        ms_tif = products_dir / "ms_orthomosaic.tif"
        shutil.copy(ms_dir / "odm_orthophoto" / "odm_orthophoto.tif", ms_tif)
        _run_ndvi(ms_tif, products_dir / "ndvi.tif")
