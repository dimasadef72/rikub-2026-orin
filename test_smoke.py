import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

from app.main import _extract_split
from app import odm_runner
from app.odm_runner import _docker_cmd
from app import projects


def test_extract_split_rgb_vs_ms():
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "in.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("a_D.JPG", "x")       # RGB
            zf.writestr("a_MS_G.JPG", "x")    # multispektral

        rgb_images_dir = Path(tmp) / "rgb" / "images"
        ms_images_dir = Path(tmp) / "ms" / "images"
        _extract_split(zip_path, rgb_images_dir, ms_images_dir)

        assert (rgb_images_dir / "a_D.JPG").exists()
        assert not (rgb_images_dir / "a_MS_G.JPG").exists()
        assert (ms_images_dir / "a_MS_G.JPG").exists()


def test_docker_cmd_mounts_project_dir():
    cmd = _docker_cmd(Path("/tmp/sawah1"), "rgb")
    assert "-ti" not in cmd
    assert "/tmp/sawah1:/datasets" in cmd
    assert cmd[-1] == "rgb"


def test_docker_cmd_ms_adds_radiometric_calibration():
    cmd = _docker_cmd(Path("/tmp/sawah1"), "ms", ["--radiometric-calibration", "camera"])
    assert cmd[-1] == "ms"
    assert "--radiometric-calibration" in cmd
    assert "/datasets/ms" in cmd


def test_ndvi_extent_matches_assigned_georeference():
    with tempfile.TemporaryDirectory() as tmp:
        from PIL import Image

        raw = Path(tmp) / "raw.tif"
        Image.new("L", (2, 2)).save(raw)

        geo = Path(tmp) / "geo.tif"
        subprocess.run([
            "gdal_translate", "-a_ullr", "10", "20", "12", "18", "-a_srs", "EPSG:4326",
            str(raw), str(geo),
        ], check=True, capture_output=True)

        xmin, ymin, xmax, ymax, w, h = odm_runner._ndvi_extent(geo)
        assert (xmin, ymin, xmax, ymax, w, h) == (10, 18, 12, 20, 2, 2)


def test_push_to_portable_b_builds_paths_and_payload():
    calls = []
    orig_run, orig_urlopen = odm_runner.subprocess.run, odm_runner.urllib.request.urlopen
    odm_runner.subprocess.run = lambda cmd, **kw: calls.append(("rsync", cmd))
    odm_runner.urllib.request.urlopen = lambda req, **kw: calls.append(("http", req))
    try:
        odm_runner._push_to_portable_b(
            "sawah1", "2026-06-16T15:55:00", Path("/tmp/rgb.tif"), Path("/tmp/ndvi.tif")
        )
    finally:
        odm_runner.subprocess.run, odm_runner.urllib.request.urlopen = orig_run, orig_urlopen

    assert len(calls) == 3
    assert calls[0][0] == "rsync" and calls[1][0] == "rsync"
    payload = json.loads(calls[2][1].data)
    assert payload["field_name"] == "sawah1"
    assert payload["rgb_tif_path"] == "storage/imagery/sawah1/2026-06-16T155500/rgb.tif"


def test_status_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        projects.BASE_DIR = Path(tmp)
        assert projects.get_status("sawah1", "rgb") is None

        projects.set_status("sawah1", "processing", step="rgb")
        status = projects.get_status("sawah1", "rgb")
        assert status["state"] == "processing"
        assert status["error"] is None

        # step lain tetep independen, ga ke-timpa
        assert projects.get_status("sawah1", "ndvi") is None
        projects.set_status("sawah1", "done", step="ndvi")
        assert projects.get_status("sawah1", "rgb")["state"] == "processing"
        assert projects.get_status("sawah1", "ndvi")["state"] == "done"


if __name__ == "__main__":
    test_extract_split_rgb_vs_ms()
    test_docker_cmd_mounts_project_dir()
    test_docker_cmd_ms_adds_radiometric_calibration()
    test_ndvi_extent_matches_assigned_georeference()
    test_push_to_portable_b_builds_paths_and_payload()
    test_status_roundtrip()
    print("ok")
