# Plan: Drone Image Upload & ODM Processing Service

## Tujuan

Entry point HTTP yang nerima kiriman foto pemetaan (drone) dari device lain,
lalu otomatis jalanin OpenDroneMap (ODM) buat hasilin orthomosaic.

## Keputusan Desain

- **Framework:** FastAPI. Native multipart upload, async, ringan, ga perlu
  dependency tambahan.
- **Format upload:** Device zip semua foto (mode `store`, bukan `deflate` —
  JPEG udah kompresi sendiri) jadi 1 file, upload sekali per project.
  Ini sekaligus jadi sinyal "upload selesai, siap diproses" — ga perlu
  tracking sesi/expected-count/timeout.
- **Eksekusi ODM:** Command lama (menit-jam-an), wajib jalan sebagai
  background task/subprocess. Endpoint upload balas cepat (202), client
  polling status terpisah.
- **Concurrency:** Satu project diproses dulu sampai selesai sebelum project
  berikutnya mulai (antrian sederhana). ODM berat di CPU/RAM, jalanin
  paralel bisa bikin server keok. Upgrade ke job queue proper (mis. task
  queue + worker pool) kalau nanti butuh paralel.
- **Jaringan:** WiFi lokal (bukan long-range/flaky), jadi cukup retry
  manual dari device kalau upload gagal. Ga perlu resumable/chunked upload
  (tus.io dkk) — over-engineering buat kasus ini.

## Alur

1. Device ambil 50-100 foto hasil pemetaan, zip (mode store) →
   `sawah1.zip`.
2. Device `POST /projects/{nama}/upload` (multipart, 1 file zip).
3. Server terima file lewat `UploadFile` (Starlette stream ke disk,
   `SpooledTemporaryFile`, RAM aman meski file besar).
4. Server extract zip, filter file `*_D.JPG`, taro ke
   `~/odm_projects/{nama}/rgb/images/`.
5. Server trigger background task: jalanin `docker run opendronemap/odm`
   (setara command manual yang udah ada). Status project → `processing`.
6. Endpoint upload balas `202 Accepted` — server ga nunggu ODM selesai.
7. Device polling `GET /projects/{nama}/status` tiap 10-30 detik.
8. Setelah ODM selesai, background task copy
   `odm_orthophoto.tif` → `products/rgb_orthomosaic.tif`, status → `done`
   (atau `failed` kalau ODM error, simpan log/error message).
9. Hasil akhir cukup disimpan di filesystem Jetson Orin (server-nya
   sendiri) — ga perlu endpoint download. Device cuma perlu tau lewat
   `status` bahwa prosesnya udah `done`.

## Struktur Folder

### Kode aplikasi (repo ini)

```
rikub-2026/
  app/
    main.py           # FastAPI app + routes (upload, status)
    odm_runner.py     # bangun & jalanin command docker run ODM (subprocess)
    projects.py       # baca/tulis status.json, helper path per project
  docs/
    PLAN.md
  requirements.txt
```

Sengaja flat, 1 file per tanggung jawab. Belum perlu folder `routers/`,
`services/`, `models/` dst — jumlah endpoint cuma 2 (`upload`, `status`),
struktur berlapis cuma nambah loncatan file tanpa manfaat di skala ini.

### Data per project (di Jetson Orin, terpisah dari kode)

```
~/odm_projects/{nama}/
  upload/
    {nama}.zip           # zip mentah dari device, disimpan (buat re-run/debug kalau ODM gagal)
  rgb/
    images/               # hasil extract zip, filtered *_D.JPG
    odm_orthophoto/        # output mentah ODM, isinya odm_orthophoto.tif dkk (auto dibikin ODM)
    ...                    # folder2 lain bikinan ODM (opensfm, odm_texturing, dll) — ga disentuh manual
  products/
    rgb_orthomosaic.tif    # hasil akhir, ini yang dipakai/diambil
  status.json               # { "state": "uploading|processing|done|failed", "updated_at": ..., "error": null }
```

Kenapa `status.json` per-project (bukan database): cuma 1 server, project
diproses satu-satu (bukan concurrent), jadi baca/tulis file kecil ini cukup
— ga perlu SQLite/Postgres buat nyimpen 4 field. Upgrade ke DB kalau nanti
butuh query lintas-project (dashboard riwayat, dsb).

## Belum Diputuskan / Perlu Dibahas Selanjutnya

- Auth/keamanan endpoint upload (siapa aja yang boleh kirim).
- Format nama project — device yang tentuin, atau server generate?
- Retensi data: kapan raw images / zip lama dihapus.
- Konfigurasi ODM (`--max-concurrency`, `--fast-orthophoto`, dsb) — fixed
  atau bisa diatur per-request?

## Next Step

Scaffold FastAPI project: endpoint upload, background task ODM, endpoint
status.
