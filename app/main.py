import zipfile

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile

from app.odm_runner import run_odm_pipeline
from app.projects import get_status, project_dir, set_status

app = FastAPI()


def _process(name: str) -> None:
    try:
        run_odm_pipeline(project_dir(name))
        set_status(name, "done")
    except Exception as exc:
        set_status(name, "failed", error=str(exc))


@app.post("/projects/{name}/upload", status_code=202)
async def upload_project(name: str, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    pdir = project_dir(name)
    upload_dir = pdir / "upload"
    images_dir = pdir / "images"
    upload_dir.mkdir(parents=True, exist_ok=True)

    zip_path = upload_dir / f"{name}.zip"
    with zip_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(images_dir)
    except zipfile.BadZipFile:
        raise HTTPException(400, "File bukan zip yang valid")

    set_status(name, "processing")
    background_tasks.add_task(_process, name)
    return {"project": name, "status": "processing"}


@app.get("/projects/{name}/status")
async def project_status(name: str):
    status = get_status(name)
    if status is None:
        raise HTTPException(404, "Project ga ditemukan")
    return status
