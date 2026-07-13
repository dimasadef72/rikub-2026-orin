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

Copy env contoh lalu isi alamat alat portable B:

```bash
cp .env.example .env
```

```env
PORTABLE_B_HOST=192.168.1.200
PORTABLE_B_USER=portable
```

- `PORTABLE_B_HOST` dipakai buat tujuan `rsync` dan URL register:
  `http://{PORTABLE_B_HOST}:8000/imagery/register`.
- `PORTABLE_B_USER` dipakai buat login SSH/rsync:
  `{PORTABLE_B_USER}@{PORTABLE_B_HOST}`.

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

## Detail `/process/ndvi`

Endpoint:

```bash
curl -X POST http://192.168.1.113:8000/projects/{name}/process/ndvi
```

Yang dicek saat request masuk:

- `~/odm_projects/{name}/ms/images/` harus ada dan berisi foto MS.
- Kalau kosong, API langsung balas `400`.
- `products/rgb_orthomosaic.tif` dicek di background task. Kalau belum ada,
  status NDVI jadi `failed` dengan pesan `rgb_orthomosaic.tif belum ada,
  jalanin /process/rgb dulu`.

Yang dijalankan di background:

1. ODM multispektral dari `ms/images/`.
2. Copy hasil ODM MS ke `products/ms_orthomosaic.tif`.
3. Hitung NDVI dari band MS ke `products/ndvi.tif`.
4. Align + crop RGB ke grid NDVI, hasilnya
   `products/rgb_masked_to_ndvi.tif`.
5. Ambil `capture_at` dari EXIF foto RGB pertama. Kalau EXIF tidak ada,
   fallback ke waktu server.
6. `rsync` dua file ke alat portable B:
   - `products/rgb_masked_to_ndvi.tif` -> `storage/imagery/{name}/{capture_at_path}/rgb.tif`
   - `products/ndvi.tif` -> `storage/imagery/{name}/{capture_at_path}/ndvi.tif`
7. Trigger API portable B:

```http
POST http://{PORTABLE_B_HOST}:8000/imagery/register
Content-Type: application/json
```

Payload yang dikirim:

```json
{
  "field_name": "{name}",
  "capture_at": "2026-06-16T15:55:00",
  "rgb_tif_path": "storage/imagery/{name}/{capture_at_path}/rgb.tif",
  "ndvi_tif_path": "storage/imagery/{name}/{capture_at_path}/ndvi.tif"
}
```

Catatan: `capture_at_path` adalah `capture_at` yang karakter `:`-nya dihapus
supaya aman buat path. Nilai `capture_at` di payload tetap ISO asli.

Command manual yang ekuivalen dengan langkah kirim ke portable B:

```bash
PROJECT=DJI_202510180828_001_lahan4a
CAPTURE_AT=2026-06-16T15:55:00
CAPTURE_AT_PATH=${CAPTURE_AT//:/}
REMOTE_DIR=storage/imagery/$PROJECT/$CAPTURE_AT_PATH
PORTABLE_B_HOST=192.168.1.200
PORTABLE_B_USER=portable

rsync -avP --rsync-path="mkdir -p $REMOTE_DIR && rsync" \
  ~/odm_projects/$PROJECT/products/rgb_masked_to_ndvi.tif \
  $PORTABLE_B_USER@$PORTABLE_B_HOST:$REMOTE_DIR/rgb.tif

rsync -avP --rsync-path="mkdir -p $REMOTE_DIR && rsync" \
  ~/odm_projects/$PROJECT/products/ndvi.tif \
  $PORTABLE_B_USER@$PORTABLE_B_HOST:$REMOTE_DIR/ndvi.tif

curl -X POST http://$PORTABLE_B_HOST:8000/imagery/register \
  -H 'Content-Type: application/json' \
  -d "{\"field_name\":\"$PROJECT\",\"capture_at\":\"$CAPTURE_AT\",\"rgb_tif_path\":\"$REMOTE_DIR/rgb.tif\",\"ndvi_tif_path\":\"$REMOTE_DIR/ndvi.tif\"}"
```

Biasanya command manual ini tidak perlu dijalankan, karena `/process` dan
`/process/ndvi` sudah menjalankan `rsync` + register API otomatis.

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

## Struktur Folder Project

Di Jetson, satu project disimpan di:

```text
~/odm_projects/{name}/
  upload/{name}.zip              # file awal dari rsync, dihapus setelah extract sukses
  rgb/images/                    # foto RGB hasil extract
  ms/images/                     # foto multispektral hasil extract
  rgb/odm_orthophoto/            # output ODM RGB
  ms/odm_orthophoto/             # output ODM MS
  products/
    rgb_orthomosaic.tif
    ms_orthomosaic.tif
    ndvi.tif
    rgb_masked_to_ndvi.tif
```

## Troubleshooting

- `404 ... upload/{name}.zip ga ketemu` — file zip belum di-`rsync` ke path
  yang benar, atau nama project beda.
- `400 Foto multispektral ga ketemu` — project belum pernah diextract lewat
  `/process`, atau zip tidak berisi foto MS.
- `failed: rgb_orthomosaic.tif belum ada` — jalankan `/process/rgb` dulu,
  tunggu `done`, baru trigger `/process/ndvi`.
- `failed` saat `rsync` — cek `.env`, SSH key, user/host portable B, dan
  apakah `rsync` tersedia di kedua device.
- `failed` saat register — cek API portable B hidup di
  `http://{PORTABLE_B_HOST}:8000/imagery/register`.

## Test

```
python test_smoke.py
```
