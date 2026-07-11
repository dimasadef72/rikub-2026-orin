import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(os.environ.get("ODM_PROJECTS_DIR", str(Path.home() / "odm_projects")))


def project_dir(name: str) -> Path:
    return BASE_DIR / name


def status_path(name: str) -> Path:
    return project_dir(name) / "status.json"


def _read_all(name: str) -> dict:
    path = status_path(name)
    return json.loads(path.read_text()) if path.exists() else {}


def set_status(name: str, state: str, step: str, error: Optional[str] = None) -> None:
    """step: "full" | "rgb" | "ndvi" — tiap step nyimpen entry sendiri, ga saling timpa."""
    path = status_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _read_all(name)
    data[step] = {
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
    path.write_text(json.dumps(data))


def get_status(name: str, step: str) -> Optional[dict]:
    return _read_all(name).get(step)
