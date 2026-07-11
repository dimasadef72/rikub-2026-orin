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
- `POST /projects/{name}/process` — trigger full chain. Panggil ini
  SETELAH zip-nya udah di-rsync ke `~/odm_projects/{name}/upload/{name}.zip`
  di server. Satu-satunya endpoint yang nyentuh zip: extract (split
  RGB/MS ke `rgb/images/` & `ms/images/`, lalu hapus zip mentahnya). Balas
  `202` begitu diterima; di background: ODM RGB → ODM MS (kalau ada foto
  MS) → NDVI → crop RGB ke NDVI → kirim+daftarin ke alat portable B.
- `POST /projects/{name}/process/rgb` — ODM RGB doang, baca langsung dari
  `rgb/images/` yang udah ke-extract (ga nyentuh/butuh zip). `404` kalau
  foldernya kosong (berarti belum pernah `/process`). Buat coba-coba ulang
  ODM RGB manual tanpa harus rsync+extract ulang.
- `POST /projects/{name}/process/ndvi` — ODM MS → NDVI → crop RGB-ke-NDVI →
  push ke alat B, baca langsung dari `ms/images/` yang udah ke-extract.
  Butuh `products/rgb_orthomosaic.tif` udah ada (dari `/process` atau
  `/process/rgb` sebelumnya) — `400` kalau foto MS kosong, error di
  `status` kalau `rgb_orthomosaic.tif` belum ada.
- `GET /projects/{name}/status` — status `/process` (full chain):
  `processing | done | failed` (kalau `failed`, ada field `error`).
- `GET /projects/{name}/process/rgb/status` — status `/process/rgb` doang.
- `GET /projects/{name}/process/ndvi/status` — status `/process/ndvi` doang.

Ketiganya independen, disimpen terpisah — trigger `/process/ndvi` ga
nimpa/ganggu status `/process/rgb`. `404` kalau step-nya belum pernah
di-trigger sama sekali.

## Kirim foto (dari device lain, ganti IP/nama project sesuai kebutuhan)

Sekali command, folder tujuan otomatis dibikin di Jetson (`--rsync-path`):

```bash
rsync -avP --rsync-path="mkdir -p ~/odm_projects/DJI_202510180828_001_lahan4a/upload && rsync" \
  /home/adedi/Downloads/DJI_202510180828_001_lahan4a.zip \
  jetson@192.168.1.113:~/odm_projects/DJI_202510180828_001_lahan4a/upload/
```

Lanjut trigger proses (full chain, RGB sampai push ke alat B):

```bash
curl -X POST http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/process
```

Atau jalanin per-langkah manual (mis. mau coba ulang RGB doang, atau NDVI
doang tanpa extract ulang) — panggil `/process` dulu sekali (buat extract
zip), abis itu bisa berkali-kali panggil salah satu:

```bash
curl -X POST http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/process/rgb
curl -X POST http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/process/ndvi
```

Polling status tiap beberapa menit sampai `done`/`failed` — pakai
`/status` buat full chain, atau `/process/rgb/status` /
`/process/ndvi/status` kalau trigger-nya manual per-langkah:

```bash
curl http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/status
curl http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/process/rgb/status
curl http://192.168.1.113:8000/projects/DJI_202510180828_001_lahan4a/process/ndvi/status
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
