# rikub-2026-orin

Entry point HTTP (FastAPI) yang nerima kiriman foto pemetaan drone (zip)
dari device lain, lalu otomatis jalanin OpenDroneMap (ODM) buat hasilin
orthomosaic. Jalan di Jetson Orin.

Detail desain & alur lengkap ada di [`docs/PLAN.md`](docs/PLAN.md).

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Jalanin (development)

```
fastapi dev app/main.py
```

Docs interaktif di `http://127.0.0.1:8000/docs`.

## Jalanin (production, di Jetson Orin)

```
fastapi run app/main.py --host 0.0.0.0
```

## Endpoint

- `POST /projects/{name}/upload` — upload zip foto (multipart, key `file`),
  balas `202` begitu diterima, proses ODM jalan di background.
- `GET /projects/{name}/status` — cek status: `processing | done | failed`.

## Test

```
python test_smoke.py
```

curl -X POST http://<ip-orin>:8000/projects/DJI_202510180828_001_lahan4a/upload \
 -F "file=@/home/adedi/Downloads/DJI_202510180828_001_lahan4a.zip"
