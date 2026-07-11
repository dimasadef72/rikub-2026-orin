import shutil
import zipfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.odm_runner import run_ndvi_pipeline, run_odm_pipeline, run_rgb_pipeline
from app.projects import get_status, project_dir, set_status

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


def _run_bg(name: str, pipeline) -> None:
    try:
        pipeline(project_dir(name))
        set_status(name, "done")
    except Exception as exc:
        set_status(name, "failed", error=str(exc))


def _extract_from_zip(name: str) -> None:
    """Extract upload/{name}.zip -> rgb/images + ms/images, lalu hapus zip mentahnya."""
    pdir = project_dir(name)
    zip_path = pdir / "upload" / f"{name}.zip"
    if not zip_path.exists():
        raise HTTPException(404, f"{zip_path} ga ketemu, rsync dulu sebelum trigger process")

    shutil.rmtree(pdir / "rgb", ignore_errors=True)
    shutil.rmtree(pdir / "ms", ignore_errors=True)

    try:
        _extract_split(zip_path, pdir / "rgb" / "images", pdir / "ms" / "images")
    except zipfile.BadZipFile:
        raise HTTPException(400, "File bukan zip yang valid")

    zip_path.unlink()  # extract sukses, zip mentah ga kepake lagi


def _extract_split(zip_path: Path, rgb_images_dir: Path, ms_images_dir: Path) -> None:
    """RGB (*_D.JPG) ke rgb_images_dir, sisanya (multispektral) ke ms_images_dir."""
    rgb_images_dir.mkdir(parents=True, exist_ok=True)
    ms_images_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            fname = Path(info.filename).name
            dest_dir = rgb_images_dir if fname.endswith("_D.JPG") else ms_images_dir
            with zf.open(info) as src, open(dest_dir / fname, "wb") as dst:
                shutil.copyfileobj(src, dst)


@app.post("/projects/{name}/process", status_code=202)
async def process_project(name: str, background_tasks: BackgroundTasks):
    """Trigger full chain (RGB + NDVI kalau ada MS) setelah file di-rsync ke upload/{name}.zip."""
    _extract_from_zip(name)
    set_status(name, "processing")
    background_tasks.add_task(_run_bg, name, run_odm_pipeline)
    return {"project": name, "status": "processing"}


@app.post("/projects/{name}/process/rgb", status_code=202)
async def process_rgb(name: str, background_tasks: BackgroundTasks):
    """Trigger cuma ODM RGB, baca langsung dari rgb/images yang udah ke-extract (ga nyentuh zip)."""
    rgb_images_dir = project_dir(name) / "rgb" / "images"
    if not (rgb_images_dir.exists() and any(rgb_images_dir.iterdir())):
        raise HTTPException(404, f"{rgb_images_dir} kosong, jalanin /process dulu buat extract zip-nya")

    set_status(name, "processing")
    background_tasks.add_task(_run_bg, name, run_rgb_pipeline)
    return {"project": name, "status": "processing"}


@app.post("/projects/{name}/process/ndvi", status_code=202)
async def process_ndvi(name: str, background_tasks: BackgroundTasks):
    """Trigger cuma ODM MS + NDVI + crop + push ke alat B. Butuh /process atau /process/rgb udah selesai duluan."""
    ms_images_dir = project_dir(name) / "ms" / "images"
    if not (ms_images_dir.exists() and any(ms_images_dir.iterdir())):
        raise HTTPException(400, "Foto multispektral ga ketemu, jalanin /process/rgb dulu")

    set_status(name, "processing")
    background_tasks.add_task(_run_bg, name, run_ndvi_pipeline)
    return {"project": name, "status": "processing"}


@app.get("/projects/{name}/status")
async def project_status(name: str):
    status = get_status(name)
    if status is None:
        raise HTTPException(404, "Project ga ditemukan")
    return status
