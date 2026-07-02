import tempfile
from pathlib import Path

from app.odm_runner import _docker_cmd, _filter_d_images
from app import projects


def test_filter_d_images():
    with tempfile.TemporaryDirectory() as tmp:
        images_dir = Path(tmp) / "images"
        rgb_images_dir = Path(tmp) / "rgb" / "images"
        images_dir.mkdir()
        (images_dir / "a_D.JPG").write_bytes(b"x")
        (images_dir / "a_T.JPG").write_bytes(b"x")  # thermal, must be skipped

        _filter_d_images(images_dir, rgb_images_dir)

        assert (rgb_images_dir / "a_D.JPG").exists()
        assert not (rgb_images_dir / "a_T.JPG").exists()


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
    test_filter_d_images()
    test_docker_cmd_mounts_project_dir()
    test_status_roundtrip()
    print("ok")
