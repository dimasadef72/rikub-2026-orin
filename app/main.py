import shutil
import zipfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException

from app.odm_runner import run_odm_pipeline
from app.projects import get_status, project_dir, set_status

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


def _process(name: str) -> None:
    try:
        run_odm_pipeline(project_dir(name))
        set_status(name, "done")
    except Exception as exc:
        set_status(name, "failed", error=str(exc))


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
    """Trigger setelah file di-rsync ke upload/{name}.zip di server."""
    pdir = project_dir(name)
    zip_path = pdir / "upload" / f"{name}.zip"
    rgb_images_dir = pdir / "rgb" / "images"
    ms_images_dir = pdir / "ms" / "images"

    if not zip_path.exists():
        raise HTTPException(404, f"{zip_path} ga ketemu, rsync dulu sebelum trigger process")

    shutil.rmtree(pdir / "rgb", ignore_errors=True)
    shutil.rmtree(pdir / "ms", ignore_errors=True)

    try:
        _extract_split(zip_path, rgb_images_dir, ms_images_dir)
    except zipfile.BadZipFile:
        raise HTTPException(400, "File bukan zip yang valid")

    zip_path.unlink()  # extract sukses, zip mentah ga kepake lagi

    set_status(name, "processing")
    background_tasks.add_task(_process, name)
    return {"project": name, "status": "processing"}


@app.get("/projects/{name}/status")
async def project_status(name: str):
    status = get_status(name)
    if status is None:
        raise HTTPException(404, "Project ga ditemukan")
    return status
