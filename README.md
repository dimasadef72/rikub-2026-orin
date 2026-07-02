# rikub-2026-orin

Foto pemetaan drone (zip) di-`rsync` dari device lain ke Jetson Orin, lalu
lewat 1 panggilan API (FastAPI) trigger OpenDroneMap (ODM) buat hasilin
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

- `GET /health` — cek server hidup.
- `POST /projects/{name}/process` — trigger ODM. Panggil ini SETELAH zip-nya
  udah di-rsync ke `~/odm_projects/{name}/upload/{name}.zip` di server.
  Balas `202` begitu diterima, extract + ODM jalan di background.
- `GET /projects/{name}/status` — cek status: `processing | done | failed`.

## Kirim foto (dari device lain, ganti IP/path sesuai kebutuhan)

```bash
ssh jetson@192.168.1.109 "mkdir -p ~/odm_projects/DJI_202510180828_001_lahan4a/upload"
rsync -avP /home/adedi/Downloads/DJI_202510180828_001_lahan4a.zip \
  jetson@192.168.1.109:~/odm_projects/DJI_202510180828_001_lahan4a/upload/

curl -X POST http://192.168.1.109:8000/projects/DJI_202510180828_001_lahan4a/process
```

## Test

```
python test_smoke.py
```
