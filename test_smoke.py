import tempfile
import zipfile
from pathlib import Path

from app.main import _extract_split
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
    cmd = _docker_cmd(Path("/tmp/sawah1"))
    assert "-ti" not in cmd
    assert "/tmp/sawah1:/datasets" in cmd
    assert cmd[-1] == "rgb"


def test_status_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        projects.BASE_DIR = Path(tmp)
        assert projects.get_status("sawah1") is None

        projects.set_status("sawah1", "processing")
        status = projects.get_status("sawah1")
        assert status["state"] == "processing"
        assert status["error"] is None


if __name__ == "__main__":
    test_extract_split_rgb_vs_ms()
    test_docker_cmd_mounts_project_dir()
    test_status_roundtrip()
    print("ok")
