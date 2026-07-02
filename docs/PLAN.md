# Plan: Drone Image Upload & ODM Processing Service

## Tujuan

Foto pemetaan (drone) dari device lain sampai ke Jetson Orin, lalu otomatis
jalanin OpenDroneMap (ODM) buat hasilin orthomosaic.

## Keputusan Desain

- **Transfer file: `rsync` lewat SSH**, bukan HTTP upload custom. Awalnya
  pakai HTTP POST (multipart lalu raw body stream), tapi ternyata:
  - FastAPI/Starlette baca SELURUH body dulu sebelum handler jalan (buat
    multipart) — progress/log ga bisa real-time, susah bedain "lagi lambat"
    vs "macet".
  - Custom retry/resume kalau WiFi putus di tengah upload gede itu masalah
    yang udah diselesaikan `rsync` (`--partial`) — daripada reinvent, pakai
    yang udah teruji.
  - Hasilnya: kode di server JUSTRU lebih sedikit (ga ada lagi byte-counting
    manual buat progress).
- **Framework API: FastAPI.** Dipakai buat trigger proses (bukan lagi buat
  terima file), plus endpoint status & health check. Ringan, async, ga
  perlu dependency tambahan.
- **Format kiriman:** Device zip semua foto (mode `store`, bukan `deflate` —
  JPEG udah kompresi sendiri) jadi 1 file per project.
- **Eksekusi ODM:** Command lama (menit-jam-an), wajib jalan sebagai
  background task/subprocess. Endpoint trigger balas cepat (202), client
  polling status terpisah.
- **Concurrency:** Satu project diproses dulu sampai selesai sebelum project
  berikutnya mulai (antrian sederhana, `threading.Lock`). ODM berat di
  CPU/RAM, jalanin paralel bisa bikin server keok. Upgrade ke job queue
  proper (mis. task queue + worker pool) kalau nanti butuh paralel.
- **Storage:** Zip mentah di `upload/` dihapus otomatis setelah extract
  sukses — begitu ke-extract ke `images/`, zip-nya ga kepake lagi buat ODM,
  cuma makan disk 2x lipat kalau dibiarin (Orin storage-nya terbatas).

## Alur

1. Device ambil 50-100 foto hasil pemetaan, zip (mode store) →
   `sawah1.zip`.
2. Device `rsync` zip itu ke `~/odm_projects/sawah1/upload/sawah1.zip` di
   Jetson Orin (lewat SSH). Resume otomatis kalau koneksi putus di tengah.
3. Device panggil `POST /projects/sawah1/process` buat trigger proses
   (rsync selesai != server tau otomatis, jadi device yang kasih sinyal).
4. Server extract zip → `images/`, lalu **hapus zip mentahnya** (udah ga
   kepake, hemat disk).
5. Server filter file `*_D.JPG` dari `images/` ke `rgb/images/`, lalu
   trigger background task: jalanin `docker run opendronemap/odm` (setara
   command manual yang udah ada). Status project → `processing`.
6. Endpoint `process` balas `202 Accepted` — server ga nunggu ODM selesai.
7. Device polling `GET /projects/sawah1/status` tiap 10-30 detik.
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
    main.py           # FastAPI app + routes (health, process, status)
    odm_runner.py     # bangun & jalanin command docker run ODM (subprocess)
    projects.py       # baca/tulis status.json, helper path per project
  docs/
    PLAN.md
  requirements.txt
```

Sengaja flat, 1 file per tanggung jawab. Belum perlu folder `routers/`,
`services/`, `models/` dst — jumlah endpoint cuma 3 (`health`, `process`,
`status`), struktur berlapis cuma nambah loncatan file tanpa manfaat di
skala ini.

### Data per project (di Jetson Orin, terpisah dari kode)

```
~/odm_projects/{nama}/
  upload/
    {nama}.zip           # zip dari rsync, dihapus otomatis setelah extract sukses
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
