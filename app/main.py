import zipfile

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

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


@app.post("/projects/{name}/upload", status_code=202)
async def upload_project(name: str, request: Request, background_tasks: BackgroundTasks):
    print(f"[upload] menerima upload buat project '{name}'...", flush=True)
    # ponytail: raw body stream (bukan multipart/UploadFile) supaya chunk yang
    # kebaca itu beneran chunk yang baru nyampe dari socket, bukan hasil baca
    # dari file sementara yang FastAPI udah buffer penuh duluan sebelum handler
    # ini jalan (itu yang bikin progress log lama percuma).
    total_size = int(request.headers.get("content-length") or 0)

    pdir = project_dir(name)
    upload_dir = pdir / "upload"
    images_dir = pdir / "images"
    upload_dir.mkdir(parents=True, exist_ok=True)

    zip_path = upload_dir / f"{name}.zip"
    bytes_received = 0
    log_every = 10 * 1024 * 1024
    next_log_at = log_every
    with zip_path.open("wb") as out:
        async for chunk in request.stream():
            out.write(chunk)
            bytes_received += len(chunk)
            if bytes_received >= next_log_at:
                mb = bytes_received // (1024 * 1024)
                if total_size:
                    pct = bytes_received / total_size * 100
                    print(f"[upload] '{name}': {mb} MB / {total_size / (1024 * 1024):.0f} MB ({pct:.0f}%)", flush=True)
                else:
                    print(f"[upload] '{name}': {mb} MB diterima...", flush=True)
                next_log_at += log_every
    print(f"[upload] '{name}': upload selesai, total {bytes_received / (1024 * 1024):.1f} MB", flush=True)

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
