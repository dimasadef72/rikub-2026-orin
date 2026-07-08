# Setup SSH Key ke Jetson Orin

Biar `rsync`/`ssh` ke Jetson ga minta password tiap kali (perlu buat device
ngirim foto otomatis tanpa interaksi manual).

**Semua command di bawah dijalanin di CLIENT** (laptop/NUC — device yang
ngirim foto ke Jetson), **bukan di Jetson**. Jetson (server) ga perlu
disentuh manual, cukup nerima public key lewat `ssh-copy-id`.

## 1. Generate SSH key (di client, kalau belum punya)

```bash
ssh-keygen -t ed25519
```

Enter aja terus (default path `~/.ssh/id_ed25519`, passphrase boleh
dikosongin biar bener-bener otomatis tanpa prompt apapun).

Cek dulu, kalau file `~/.ssh/id_ed25519` udah ada, skip step ini — pakai
yang udah ada.

## 2. Copy public key ke Jetson (dijalanin dari client)

```bash
ssh-copy-id jetson@192.168.1.113
```

Command ini dijalanin **dari client**, tapi efeknya naro public key **ke**
Jetson (`~/.ssh/authorized_keys` di server). Bakal nanya password Jetson
**sekali ini aja** (`jetson`).

## 3. Test (dari client)

```bash
ssh jetson@192.168.1.113 "echo ok"
```

Kalau langsung keluar `ok` tanpa nanya password → key auth udah jalan.

## Setelah ini

`rsync` dan `ssh` ke `192.168.1.113` ga perlu password lagi, jadi command
kayak:

```bash
rsync -avP --rsync-path="mkdir -p ~/odm_projects/{nama}/upload && rsync" \
  {file}.zip jetson@192.168.1.113:~/odm_projects/{nama}/upload/
```

bisa dijalanin device secara otomatis (misal dari script) tanpa nunggu orang
ngetik password.

## Kalau IP Jetson ganti-ganti (DHCP)

Kalau IP Jetson berubah tiap reconnect (kayak sempet kejadian `192.168.1.109`
→ `192.168.1.113`), pertimbangkan set IP static di Jetson atau reservation di
router — biar command di atas ga perlu diubah tiap kali IP berganti.
