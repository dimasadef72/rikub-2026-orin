# rikub-2026-orin

Foto pemetaan drone (zip, isinya RGB + multispektral) di-`rsync` dari device
lain ke Jetson Orin, lalu lewat 1 panggilan API (FastAPI) trigger
OpenDroneMap (ODM) buat hasilin orthomosaic RGB, orthomosaic multispektral,
dan NDVI. Kalau ada NDVI, RGB di-crop/align ke area NDVI, lalu hasilnya
di-`rsync` + didaftarin (`POST /imagery/register`) ke alat portable B. Jalan
di Jetson Orin.

Detail desain & alur lengkap ada di [`docs/PLAN.md`](docs/PLAN.md). Setup
SSH key (biar rsync ga minta password tiap kali) ada di
[`docs/SETUP_SSH.md`](docs/SETUP_SSH.md).

## Prasyarat di Jetson

- Docker (image `opendronemap/odm:3.5.4` bakal ke-pull otomatis pas pertama
  jalan).
- GDAL (`gdalinfo`, `gdalwarp`, `gdal_translate`, `gdalbuildvrt`,
  `gdal_calc.py` di PATH) — dipakai buat NDVI + crop RGB-ke-NDVI, jalan di
  host langsung (bukan di dalam container ODM).
- File `.env` di root repo (copy dari `.env.example`), isi alamat alat
  portable B (`PORTABLE_B_HOST`, `PORTABLE_B_USER`) — tujuan kirim hasil
  akhir RGB+NDVI. `.env` di-gitignore, jangan di-commit.

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
- `POST /projects/{name}/process` — trigger pipeline. Panggil ini SETELAH
  zip-nya udah di-rsync ke `~/odm_projects/{name}/upload/{name}.zip` di
  server. Balas `202` begitu diterima; di background: extract (split
  RGB/MS) → ODM RGB → ODM MS (kalau ada) → NDVI (kalau ada MS) → crop RGB
  ke NDVI (kalau ada NDVI) → kirim+daftarin ke alat portable B (kalau ada
  NDVI).
- `GET /projects/{name}/status` — cek status: `processing | done | failed`
  (kalau `failed`, ada field `error` isinya pesan errornya).

## Kirim foto (dari device lain, ganti IP/nama project sesuai kebutuhan)

Sekali command, folder tujuan otomatis dibikin di Jetson (`--rsync-path`):

```bash
rsync -avP --rsync-path="mkdir -p ~/odm_projects/DJI_202510180828_001_lahan4a/upload && rsync" \
  /home/adedi/Downloads/DJI_202510180828_001_lahan4a.zip \
  jetson@192.168.1.113:~/odm_projects/DJI_202510180828_001_lahan4a/upload/
```

Lanjut trigger proses:

```bash
curl -X POST http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/process
```

Polling status tiap beberapa menit sampai `done`/`failed`:

```bash
curl http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/status
```

Hasil akhir ada di Jetson, `~/odm_projects/DJI_202510180828_001_lahan4a/products/`:
- `rgb_orthomosaic.tif` — selalu ada.
- `ms_orthomosaic.tif`, `ndvi.tif`, `rgb_masked_to_ndvi.tif` — cuma ada
  kalau zip-nya ngandung foto multispektral (`*_MS_G.TIF` dkk).

Kalau ada MS/NDVI, `rgb_masked_to_ndvi.tif` + `ndvi.tif` otomatis ke-`rsync`
dan ke-daftarin (`POST /imagery/register`) ke alat portable B — ga perlu
langkah manual tambahan.

## Test

```
python test_smoke.py
```
