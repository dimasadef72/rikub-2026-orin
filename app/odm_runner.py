import json
import os
import shutil
import subprocess
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ODM_IMAGE = "opendronemap/odm:3.5.4"

# alamat alat portable B (tujuan rsync + register hasil akhir), diisi di .env
PORTABLE_B_HOST = os.environ.get("PORTABLE_B_HOST", "portable-b.local")
PORTABLE_B_USER = os.environ.get("PORTABLE_B_USER", "portable")
PORTABLE_B_REGISTER_URL = f"http://{PORTABLE_B_HOST}:8000/imagery/register"

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


def _ndvi_extent(ndvi_tif: Path) -> tuple:
    """(xmin, ymin, xmax, ymax, width, height) dari geoTransform NDVI."""
    info = json.loads(subprocess.run(
        ["gdalinfo", "-json", str(ndvi_tif)],
        capture_output=True, check=True, text=True,
    ).stdout)
    gt = info["geoTransform"]
    w, h = info["size"]
    xmin, ymax = gt[0], gt[3]
    xmax = xmin + gt[1] * w
    ymin = ymax + gt[5] * h
    return xmin, ymin, xmax, ymax, w, h


def _crop_rgb_to_ndvi(rgb_tif: Path, ndvi_tif: Path, out_tif: Path) -> None:
    """Align rgb_tif ke grid NDVI, lalu mask ke area valid NDVI (jadi alpha channel)."""
    tmp = out_tif.parent / "rgb_mask_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)

    xmin, ymin, xmax, ymax, w, h = _ndvi_extent(ndvi_tif)

    rgb_aligned = tmp / "rgb_aligned.tif"
    subprocess.run([
        "gdalwarp", "-overwrite", "-r", "bilinear",
        "-te", str(xmin), str(ymin), str(xmax), str(ymax),
        "-ts", str(w), str(h),
        "-dstnodata", "0", "-co", "COMPRESS=DEFLATE",
        str(rgb_tif), str(rgb_aligned),
    ], check=True)

    band_tifs = []
    for band in (1, 2, 3):
        band_tif = tmp / f"band{band}.tif"
        subprocess.run([
            "gdal_calc.py",
            "-A", str(rgb_aligned), f"--A_band={band}",
            "-M", str(ndvi_tif),
            f"--outfile={band_tif}",
            "--calc=where((M!=-9999)&(M==M),A,0)",
            "--type=Byte", "--NoDataValue=0", "--overwrite",
        ], check=True)
        band_tifs.append(band_tif)

    alpha_tif = tmp / "alpha.tif"
    subprocess.run([
        "gdal_calc.py",
        "-M", str(ndvi_tif),
        f"--outfile={alpha_tif}",
        "--calc=where((M!=-9999)&(M==M),255,0)",
        "--type=Byte", "--NoDataValue=0", "--overwrite",
    ], check=True)

    vrt = tmp / "rgb_masked.vrt"
    subprocess.run(
        ["gdalbuildvrt", "-separate", str(vrt), *map(str, band_tifs), str(alpha_tif)],
        check=True,
    )
    subprocess.run(
        ["gdal_translate", "-co", "COMPRESS=DEFLATE", str(vrt), str(out_tif)],
        check=True,
    )

    shutil.rmtree(tmp, ignore_errors=True)


def _capture_at_from_exif(rgb_images_dir: Path) -> str:
    """DateTime EXIF dari foto RGB pertama; fallback ke waktu sekarang kalau ga ada."""
    from PIL import ExifTags, Image

    for jpg in sorted(rgb_images_dir.glob("*.JPG")):
        exif = Image.open(jpg).getexif()
        raw = exif.get(306) or exif.get_ifd(ExifTags.IFD.Exif).get(36867)
        if raw:
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").isoformat()
    return datetime.now().isoformat()


def _push_to_portable_b(field_name: str, capture_at: str, rgb_tif: Path, ndvi_tif: Path) -> None:
    """Rsync hasil akhir ke alat portable B, lalu daftarin ke DB-nya."""
    remote_dir = f"storage/imagery/{field_name}/{capture_at.replace(':', '')}"
    for local, remote_name in ((rgb_tif, "rgb.tif"), (ndvi_tif, "ndvi.tif")):
        subprocess.run([
            "rsync", "-avP",
            "--rsync-path", f"mkdir -p {remote_dir} && rsync",
            str(local),
            f"{PORTABLE_B_USER}@{PORTABLE_B_HOST}:{remote_dir}/{remote_name}",
        ], check=True)

    payload = json.dumps({
        "field_name": field_name,
        "capture_at": capture_at,
        "rgb_tif_path": f"{remote_dir}/rgb.tif",
        "ndvi_tif_path": f"{remote_dir}/ndvi.tif",
    }).encode()
    req = urllib.request.Request(
        PORTABLE_B_REGISTER_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    urllib.request.urlopen(req, timeout=10)


def run_odm_pipeline(project_dir: Path) -> None:
    rgb_dir = project_dir / "rgb"
    ms_dir = project_dir / "ms"
    products_dir = project_dir / "products"
    products_dir.mkdir(parents=True, exist_ok=True)

    with _odm_lock:
        subprocess.run(_docker_cmd(project_dir, "rgb"), check=True)
    rgb_tif = products_dir / "rgb_orthomosaic.tif"
    shutil.copy(rgb_dir / "odm_orthophoto" / "odm_orthophoto.tif", rgb_tif)

    ms_images_dir = ms_dir / "images"
    if ms_images_dir.exists() and any(ms_images_dir.iterdir()):
        with _odm_lock:
            subprocess.run(
                _docker_cmd(project_dir, "ms", ["--radiometric-calibration", "camera"]),
                check=True,
            )
        ms_tif = products_dir / "ms_orthomosaic.tif"
        shutil.copy(ms_dir / "odm_orthophoto" / "odm_orthophoto.tif", ms_tif)

        ndvi_tif = products_dir / "ndvi.tif"
        _run_ndvi(ms_tif, ndvi_tif)

        rgb_masked_tif = products_dir / "rgb_masked_to_ndvi.tif"
        _crop_rgb_to_ndvi(rgb_tif, ndvi_tif, rgb_masked_tif)

        capture_at = _capture_at_from_exif(rgb_dir / "images")
        _push_to_portable_b(project_dir.name, capture_at, rgb_masked_tif, ndvi_tif)
