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


def set_status(name: str, state: str, error: Optional[str] = None) -> None:
    path = status_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }))


def get_status(name: str) -> Optional[dict]:
    path = status_path(name)
    if not path.exists():
        return None
    return json.loads(path.read_text())
