"""Simulates the device: uploads a zip of drone photos to the FastAPI server.

Zip path is set below in ZIP_PATH. Project name is derived from the zip
filename (without extension), e.g.
DJI_202510180828_001_lahan4a.zip -> project "DJI_202510180828_001_lahan4a".

Usage:
    python scripts/upload_test.py <server_url> [project_name]
"""
import sys
from pathlib import Path

import httpx

ZIP_PATH = "/home/adedi/Downloads/DJI_202510180828_001_lahan4a.zip"


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <server_url> [project_name]")
        print(f"Example: python {sys.argv[0]} http://192.168.1.50:8000")
        sys.exit(1)

    server_url = sys.argv[1].rstrip("/")
    zip_path = ZIP_PATH
    project_name = sys.argv[2] if len(sys.argv) > 2 else Path(zip_path).stem

    url = f"{server_url}/projects/{project_name}/upload"
    print(f"Uploading {zip_path} -> {url} (project: {project_name})")

    with open(zip_path, "rb") as f:
        resp = httpx.post(url, content=f, timeout=None)

    resp.raise_for_status()
    print(resp.json())


if __name__ == "__main__":
    main()
