import zipfile

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


@app.post("/projects/{name}/process", status_code=202)
async def process_project(name: str, background_tasks: BackgroundTasks):
    """Trigger setelah file di-rsync ke upload/{name}.zip di server."""
    pdir = project_dir(name)
    zip_path = pdir / "upload" / f"{name}.zip"
    images_dir = pdir / "images"

    if not zip_path.exists():
        raise HTTPException(404, f"{zip_path} ga ketemu, rsync dulu sebelum trigger process")

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(images_dir)
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
