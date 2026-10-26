# Sesi 5 — Dead window STM32, dashboard yang tidak mengirim, dan kecepatan maju

**Status: SELESAI — semua perbaikan terverifikasi tanpa aktuasi hardware.**
Sesi ini tidak punya rangkaian uji aktuasi yang rumit: satu-satunya gerakan
nyata adalah TUGAS 1A dan TUGAS 1C yang dijalankan operator. Seluruh pekerjaan
sesudahnya — dua akar masalah dashboard, kecepatan maju/mundur, dan tata letak
UI — dibuktikan lewat pembacaan kode, test, dan port perekam, **bukan** dengan
menggerakkan robot.

**Tanggal:** 2026-10-22 (WIB, UTC+07:00)
**Host:** `stematel-pi5` (Raspberry Pi 5, Ubuntu 24.04.5 LTS ARM64), sesi lewat SSH
**Repo:** `/home/stematelpi5/AMRTestLander/AMR_LKS_Dashboard` (branch `main`, HEAD `b0e0214`)
**Stash yang dipertahankan:** `stash@{0}: On main: lidar-wip-phase1` — utuh, tidak disentuh
**Python:** `~/AMRTestLander/.venv/bin/python` (3.12.3, pyserial 3.5, nicegui 3.18.0)

Grade bukti yang dipakai sama seperti sesi 3 dan 4:

| Grade | Arti |
| --- | --- |
| **TERUKUR** | diukur di robot ini, alat dan prosedurnya dicatat |
| **TERVERIFIKASI** | dikonfirmasi lewat pembacaan langsung (protokol, port, berkas) |
| **INFERENSI** | diturunkan dari dokumen, bukan dibaca di sumber primer |
| **SOURCE-ONLY** | hanya dari dokumentasi pabrik, belum dicek di robot ini |
| **HIPOTESIS** | kandidat penjelasan, belum terpisah dari kandidat lain |
| **TIDAK DIKETAHUI** | belum ada bukti apa pun |

Peta dokumen:

| Bagian | Isi | Aktuasi? |
| --- | --- | --- |
| §1 | ringkasan | tidak |
| §2 | baseline sesi 5 | tidak |
| §3 | temuan utama: dead window 2,359 s | tidak |
| §4 | TUGAS 1A / 1B / 1C | **ya** (1A, 1C) |
| §5 | akar masalah dashboard: mode OFFLINE | tidak |
| §6 | akar masalah dashboard: clamp yang membisukan gerak | tidak |
| §7 | perbaikan kecepatan maju/mundur | tidak |
| §8 | perbaikan tata letak UI | tidak |
| §9 | daftar file yang berubah | tidak |
| §10 | verifikasi | tidak |
| §11 | yang BELUM terverifikasi | — |
| §12 | langkah berikutnya | — |

---

## 1. Ringkasan

Tiga hal selesai di sesi ini.

1. **Penyebab "TUGAS 1A tidak menggerakkan robot" ditemukan dan diukur:** setiap
   `open()` pada `/dev/ttyACM0` membuat board diam **2,359 s** sebelum menerima
   frame motor. `wheel_test.py` menunggu 0,3 s, jadi seluruh jendela perintah
   habis saat board masih bisu. Dengan `--settle 3.0` robot bergerak normal.
2. **Dashboard ternyata bisa menggerakkan robot — tapi dua bug membuatnya
   mustahil.** Pertama, dashboard dijalankan tanpa `--chassis-live`, sehingga
   halaman berada di mode OFFLINE dan tombol arah tidak punya handler. Kedua,
   limit keselamatan (`max_linear_y = 0,05`) lebih kecil dari slider minimum
   (0,06), dan sumbu putar memakai nilai m/s sebagai rad/s, sehingga strafe dan
   putar selalu berada di bawah ambang stall 0,3 rps.
3. **Kecepatan maju/mundur dinaikkan dua kali** (1,0 → 1,3 → 1,8 rps) sebagai
   gain longitudinal saja, tanpa mengubah samping dan putar yang sudah dinilai
   benar oleh operator. Tata letak panel kontrol juga diperbaiki: kartu tidak
   lagi melebar mengikuti teks status, yang sebelumnya membuat tombol bergeser
   di bawah jari dan menghentikan gerakan sendiri.

Yang **tidak** selesai: TUGAS 1C (motor 3 & 4), 1D, TUGAS 2, 3, 4, dan laporan
§7 final. Alasannya di §11.

---

## 2. Baseline sesi 5

| Item | Nilai | Grade |
| --- | --- | --- |
| HEAD repo | `b0e0214 docs: correct the sign-convention status after the floor test` | TERVERIFIKASI |
| `git pull --ff-only` | `Already up to date.` | TERVERIFIKASI |
| Tree sebelum kerja | bersih | TERVERIFIKASI |
| Stash | `stash@{0}: On main: lidar-wip-phase1` | TERVERIFIKASI |
| Test baseline | **379 passed** | TERVERIFIKASI |
| LiDAR | `/dev/ttyUSB0` (CH340 `1a86:7523`, 230400) | TERVERIFIKASI |
| STM32 | `/dev/ttyACM0` (CDC-ACM `1a86:55d4`) | TERVERIFIKASI |
| ModemManager menyentuh ttyACM0? | tidak | TERVERIFIKASI |

---

## 3. Temuan utama — dead window 2,359 s

### 3.1 Gejala

TUGAS 1A dijalankan **persis seperti brief**, dua kali:

```
scripts/wheel_test.py --confirm --port /dev/ttyACM0 --rate 50 --duration 3 \
  --speeds "1:-0.6,2:-0.6,3:+0.6,4:+0.6"
```

Hasil: **150 frame terkirim @ 50 Hz pada kedua trial, robot tidak bergerak
sama sekali.** Laporan operator: *"belum gerak"*, *"Tidak pernah jalan"*.

Perintah dilaporkan sukses oleh alat — frame benar-benar ditulis ke port. Yang
salah bukan pengiriman, tetapi **kapan** pengiriman itu terjadi.

### 3.2 Bukti pengukuran

| Probe | Yang diukur | Hasil | Grade |
| --- | --- | --- | --- |
| `boot_delay.py` | waktu dari `open()` sampai board menerima frame motor | **2,360 / 2,359 / 2,359 / 2,359 s** (4× identik) | TERUKUR |
| `boot_delay.py` | kontrol tanpa urutan open kedua | 2,403 s | TERUKUR |
| `first_frame.py` | frame pertama apa pun | byte pada 1,109 s | TERUKUR |
| `first_frame.py` | frame SYS | 1,109 s | TERUKUR |
| `first_frame.py` | frame IMU pertama | 2,333 s | TERUKUR |
| `usb_id.py` | `1a86:55d4`, nomor device | tetap — **bukan** re-enumeration USB | TERVERIFIKASI |
| `read_vs_open.py` | apakah stall disebabkan `open` atau `read` | **`open`** (write-only pun kena) | TERUKUR |
| `boot_window_probe.py` | stream saat handle kedua dibuka | stall tepat di titik itu | TERUKUR |
| `concurrent_test.py` | dua handle bersamaan | bisa dibuka, 190 frame / 6 s | TERUKUR |
| `motor_probe.py --settle 3.0` | jarak antar frame setelah settle | max gap **20,9 ms** | TERUKUR |

### 3.3 Kesimpulan

Setiap `open()` pada `/dev/ttyACM0` menunda board **±2,36 s**. Bukan
ModemManager, bukan reset USB, bukan `read` — murni `open`.

Konsekuensi operasional: **`wheel_test.py --settle 0.3` (nilai default) tidak
pernah bisa menggerakkan robot.** Jendela perintah 3 s hanya menyisakan 0,64 s
efektif, dan pada `--settle 0.3` bahkan seluruh durasi habis sebelum board siap.

Uji isolasi membuktikannya: perintah 1A yang sama dengan **hanya** tambahan
`--settle 3.0` membuat robot **maju normal, lurus, ±1 m, dengan jeda ±1 detik**
sebelum bergerak. Grade: **TERUKUR**.

Dashboard tidak pernah kena masalah ini karena ia **membuka port satu kali saat
start-up** dan mempertahankan handle itu. Itu sebabnya TUGAS 1B terlihat mulus
sementara 1A tidak bergerak.

---

## 4. TUGAS 1A / 1B / 1C

### 4.1 TUGAS 1A — GAGAL, lalu terjelaskan

| Trial | Frame | Rate | Gerak | Catatan |
| --- | --- | --- | --- | --- |
| 1 | 150 | 50 Hz | **tidak bergerak** | `--settle 0,3`; operator: "belum gerak" |
| 2 | 150 | 50 Hz | **tidak bergerak** | `--settle 0,3`; operator: "Tidak pernah jalan" |
| isolasi | 150 | 50 Hz | **maju ±1 m, lurus** | `settle 3.0`; operator: "Jeda ~1 detik lalu jalan" |

Sesuai aturan brief, hasil 1A ditulis **GAGAL** untuk dua trial pertama.
Penyebabnya prosedur alat, bukan robot.

### 4.2 TUGAS 1B — dashboard, stream sehat

Server dijalankan `--chassis-live --host 0.0.0.0 --port 8080`, slider 0,06 m/s,
tombol MAJU ditahan 3 detik lewat browser.

| Trial | Stream | Max gap | Frames | Heartbeat |
| --- | --- | --- | --- | --- |
| 1 (server lama) | 50,0 Hz | 52 ms | 238 | — |
| 1 (server fresh) | 50,0 Hz | **37 ms** | 202 | — |
| 2 (server fresh) | 50,0 Hz | **41 ms** | 264 | 0,02–0,07 s |

Max gap 13 226 ms pada satu percobaan adalah **artefak idle** (tidak ada tombol
ditekan), bukan macet — dibuktikan dengan membandingkan sampel waktu.

Grade: **TERUKUR**. Kesimpulan: server tidak nyendet. Kalau 1A juga mulus,
maka nyendet berasal dari robot/board; 1D tidak sempat disimpulkan karena 1A
awalnya gagal.

### 4.3 TUGAS 1C — SEBAGIAN

Roda terangkat, motor satu per satu, `--settle 3.0 --duration 2 --speed 0.3`:

| Motor | Frame terkirim | Rate | Observasi roda |
| --- | --- | --- | --- |
| 1 | 100 | 50 Hz | **tidak tercatat** (operator meleng) |
| 2 | 100 | 50 Hz | **tidak tercatat** (operator meleng) |
| 3 | — | — | **tidak dijalankan** |
| 4 | — | — | **tidak dijalankan** |

Pass kedua dihentikan operator (*"stop, jangan test. lanjut nanti"* lalu
*"BATERE HABIS"*) saat berada di prompt MOTOR 3, sehingga MOVE tidak pernah
dikirim untuk motor 3 dan 4. Grade: **GAGAL — alasan: baterai habis, observasi
tidak terlihat.**

Catatan penting: temuan lama "motor 3 (depan kanan) tidak berputar di lantai"
masih **belum diuji ulang**, dan sekarang ada kandidat penjelasan baru — roda
depan kanan bisa jadi korban dead window 2,36 s saat diuji dengan `--settle`
default. Jangan dianggap kerusakan mekanis sampai diuji dengan `settle 3.0`.

---

## 5. Akar masalah dashboard #1 — mode OFFLINE

**Gejala operator:** *"kok dashboard nya ga berfungsi. Ga bisa maju mundur kanan
kiri"*, lalu *"masih gabisa, masih offline"*.

**Sebab:** dashboard dijalankan sebagai `python run_dashboard.py` **tanpa**
`--chassis-live`. Pada PID yang diperiksa (25890), file descriptor hanya memegang
`ttyUSB0` (LiDAR) — `ttyACM0` tidak pernah dibuka.

Halaman mengonfirmasi dirinya sendiri:

```
OFFLINE: commands are validated and clamped, but NOT transmitted.
badge chassis: DISABLED
```

Tombol arah tetap terlihat normal tetapi **dibangun tanpa event handler sama
sekali** — ditekan tidak menghasilkan apa pun: tidak gerak, tidak error, tidak
notifikasi. Itu cara paling efektif membuat operator menyimpulkan "dashboard
rusak" padahal dashboard sehat.

`fuser` tidak rusak; setelah Ctrl+C memang tidak ada proses yang menempati port
8080, jadi `fuser -k` tidak menemukan apa pun untuk dimatikan.

**Perbaikan:**

- Mode OFFLINE sekarang menampilkan tombol **disabled** plus label merah
  *"Tombol arah DINONAKTIFKAN: mode OFFLINE tidak mengirim perintah."*
- Dibuat launcher `~/amr_live.sh` (di luar repo, agar tree tetap bersih) yang
  mematikan dashboard lama, memeriksa `/dev/ttyACM0`, lalu menjalankan
  `--chassis-live --chassis-port /dev/ttyACM0`. Flag-nya tidak bisa lupa lagi.

Grade: **TERVERIFIKASI** — halaman setelah perbaikan menunjukkan `CONNECTED` +
badge `LIVE`, tombol MAJU aktif.

---

## 6. Akar masalah dashboard #2 — clamp yang membisukan gerak

Dashboard sudah mengirim, tetapi strafe dan putar tetap mustahil. Diukur dengan
`scratch/verify_fix.py` pada slider minimum 0,06 m/s:

| Arah | rps diminta | rps setelah clamp | vs ambang stall (0,3 rps) |
| --- | --- | --- | --- |
| Maju / Mundur | 0,327 | 0,327 | lewat (marginal) |
| **Kiri / Kanan** | 0,327 | **0,273** | **di bawah → roda diam** |
| **Putar L / R** | 0,327 | **0,046** | **jauh di bawah → roda diam** |

Dua bug terpisah:

1. `LIVE_LIMITS.max_linear_y = 0,05` **lebih kecil dari slider minimum 0,06**,
   sehingga strafe selalu ter-clamp ke 0,05 m/s → 0,273 rps. Bahkan slider
   maksimum tidak bisa melewatinya; strafe tidak akan pernah jalan.
2. Sumbu putar memakai nilai **m/s dipakai langsung sebagai rad/s**. Pada 0,06
   hasilnya setara 0,046 rps — praktis nol.

**Perbaikan:**

- `LIVE_LIMITS`: `max_linear_y` 0,05 → **0,19**, `max_angular_z` 0,20 → **1,20**.
- Fungsi baru `yaw_rate_for_wheel_rate(rate_rps)` di `kinematics.py`, dengan
  `HALF_DIAGONAL_M = (TRACK_WIDTH_M + WHEELBASE_M) / 2 = 0,140 m`, sehingga yaw
  sekarang diturunkan dari laju roda, bukan dari angka m/s mentah.
- Status bar kini melaporkan laju yang **benar-benar dikirim** (`drive_command`,
  termasuk clamp dan cap), bukan yang diminta — supaya tidak pernah lagi
  menampilkan "MOVING" padahal roda diam.

Verifikasi jalur kabel memakai `RecordingPort` in-process (bukan PTY, karena PTY
mati saat dashboard menutupnya): keenam arah terkirim **50,0 Hz** dengan pola
tanda yang benar. Contoh frame maju:

```
aa55 03 16 | 01 04 | 00 3f87a7be | 01 3f87a7be | 02 3f87a73e | 03 3f87a73e | 86
```

Grade: **TERVERIFIKASI**.

---

## 7. Perbaikan kecepatan maju/mundur

Operator melaporkan dua kali bahwa maju/mundur terlalu lambat pada slider penuh,
sementara samping dan putar sudah pas.

**Akar masalah:** pada 1,0 rps, pemetaan m/s memberi maju dan samping laju roda
yang **sama**, sehingga 0,19 m/s mengunci semua sumbu. Tidak ada cara
mempercepat maju tanpa menaikkan batas — tetapi menaikkan batas global ikut
mempercepat samping dan putar, yang justru sudah dinilai benar.

**Perbaikan:** batas dinaikkan **hanya untuk komando longitudinal murni**.

| Konstanta | Nilai | Berlaku untuk |
| --- | --- | --- |
| `MAX_TESTED_RPS` | 1,00 | samping, putar, dan semua komando campuran |
| `MAX_FORWARD_RPS` | **1,80** | maju/mundur murni saja |

| Tahap | `MAX_FORWARD_RPS` | Kecepatan lantai | Perubahan |
| --- | --- | --- | --- |
| awal | 1,00 | 0,190 m/s | — |
| langkah 1 | 1,30 | 0,238 m/s | +25 % |
| **langkah 2** | **1,80** | **0,330 m/s** | **+38 %** |

Laju roda per arah (hasil hitung `drive_command`, sesudah clamp):

| Arah | slider min | slider tengah | slider penuh |
| --- | --- | --- | --- |
| Maju / Mundur | 0,568 | 1,184 | **1,800** rps |
| Kiri / Kanan | 0,327 | 0,682 | 1,000 rps |
| Putar L / R | 0,327 | 0,682 | 0,916 rps |

`LONGITUDINAL_GAIN = 1,7372`; `LIVE_LIMITS.max_linear_x` dinaikkan ke 0,34 m/s
karena `speed_for_rate(1,80) = 0,330` — kalau limit ini tertinggal, clamp akan
memotong gain dan gejalanya hanya "kok masih lambat" tanpa error apa pun. Itu
sekarang dijaga oleh test.

Grade kecepatan: **BELUM TERVERIFIKASI DI LANTAI.** 1,80 rps adalah 80 % di atas
kecepatan tertinggi yang pernah diukur (1,0 rps). 1,80 rps ≈ 108 rpm di roda dan
mekanis tampak ringan, tetapi apakah robot masih **lurus** pada laju itu belum
ada buktinya.

---

## 8. Perbaikan tata letak UI

**Gejala operator:** *"kalo button ditekan Area remote nya mengecil, layout
tombol jadi berubah dan jadinya ga ter pencet"*, plus *"user harus scroll untuk
melihat tombol sementara di kanan area tombol ada area kosong yang lumayan"*.

**Sebab:** label status di-refresh tiap 250 ms dan memanjang saat ditahan
(`hold 12.3 s`, counter stream). Kartunya `flex-1 min-w-[360px]` — lebarnya ikut
isi — sehingga kartu melebar, pad tombol bergeser ke samping di bawah jari,
browser mengirim `pointerleave`, dan `pointerleave` **memang perintah stop**.
Tombol berhenti sendiri karena bergeser, bukan karena tidak terklik.

Panelnya juga berada di bawah monitor, mission, LiDAR, dan robot panel — di bawah
lipatan layar, jadi mengemudikan robot berarti scroll dulu.

**Perbaikan:**

- Kartu `w-full`; lebarnya tidak lagi ditentukan teks.
- Status dipatok `h-12` + `overflow-hidden`, jadi teks boleh berubah tiap tick
  tanpa mengubah geometri.
- Tombol disusun `ui.grid(columns=3)` dengan ukuran tetap `112×44 px`, sel kosong
  diisi spacer agar tidak mengalir ke kolom lain.
- Susunan jadi D-pad: MAJU di atas, KIRI–STOP–KANAN di tengah, PUTAR L–MUNDUR–
  PUTAR R di bawah.
- Panel dipindah ke **paling atas** `_render_structure`, sebelum baris monitor.
- Dua kolom: slider + status + E-stop di kiri, pad di kanan — mengisi ruang yang
  tadinya kosong.

Diukur di browser **tanpa menekan tombol**: teks status diganti paksa menjadi
versi `MOVING` yang panjang, lalu rect diukur ulang.

| Ukuran | Sebelum teks panjang | Sesudah teks panjang |
| --- | --- | --- |
| Tombol MAJU | (949, 276, 112×44) | (949, 276, 112×44) |
| Kartu | 1128×324 | 1128×324 |
| Teks terpotong? | — | tidak (`scrollHeight` 48 = `clientHeight` 48) |
| MAJU terlihat tanpa scroll? | — | ya (top 276 px dari viewport 633 px) |

Grade: **TERUKUR**.

---

## 9. Daftar file yang berubah

Semua perubahan **belum di-commit**. Tidak ada file di luar repo yang perlu
di-commit; launcher dan alat ukur sengaja ditaruh di luar.

| File | +/− | Isi perubahan | Mengapa |
| --- | --- | --- | --- |
| `src/amr_core/robot/kinematics.py` | +110 / −2 | `HALF_DIAGONAL_M`, `MAX_FORWARD_RPS = 1,80`, `speed_for_rate()`, `rate_cap_for()`, `drive_command()`, `yaw_rate_for_wheel_rate()` | sumbu putar memakai m/s sebagai rad/s; maju butuh batas sendiri |
| `src/amr_dashboard/robot_runtime.py` | +22 / −7 | `LIVE_LIMITS`: `max_linear_y` 0,05→0,19, `max_angular_z` 0,20→1,20, `max_linear_x` 0,24→**0,34** | limit lebih kecil dari slider = bug yang membisukan gerak |
| `src/amr_dashboard/chassis_panel.py` | +196 / −63 | `_PAD`, `_PAD_BUTTON_CLASSES`, `_install_hold_buttons()` jadi grid 3×3 + STOP di tengah, `_offline_pad()`, `LONGITUDINAL_GAIN`, `_transmitted_rate()`, `_rate_note()`, `_refresh_status()` | layout bergeser saat ditahan; status harus melaporkan laju terkirim |
| `src/amr_core/robot/serial_chassis.py` | +2 / −2 | `_frame_for` memakai `drive_command` | agar cap longitudinal ikut terpakai di jalur kabel |
| `src/amr_dashboard/app.py` | +6 / −1 | panel chassis dipindah ke awal `_render_structure` | tombol harus terlihat tanpa scroll |
| `tests/test_dashboard_chassis_panel.py` | +133 / −1 | +12 test: pemetaan sumbu, invers yaw, regresi ambang stall, laju terkirim, cap maju vs samping, penjaga `LIVE_LIMITS` | mengunci semua bug di atas agar tidak kembali |
| `docs/sesi_5.md` (baru) | +451 / −0 | dokumen sesi ini: §1–§12 + lampiran | rekap perubahan per sesi, permintaan operator |

Total file ter-track: **469 insertions, 76 deletions** di 6 file
(`git diff --numstat`), ditambah **satu file baru yang belum di-track**:
`docs/sesi_5.md`, 451 baris.

Perubahan **kode** yang tidak di-commit di luar tabel di atas: tidak ada.
File bantu di luar repo: `~/amr_live.sh` (launcher LIVE) dan
`~/.hermes/cache/scratch/*.py` (alat ukur: `wire_harness.py`, `verify_fix.py`,
`passive_port_check.py`, `boot_delay.py`, `first_frame.py`, `read_vs_open.py`,
`motor_probe.py`, dan lain-lain).

---

## 10. Verifikasi

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **391 passed** (baseline sesi 379, +12) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| Pola kabel 6 arah | benar semua, **50,0 Hz** | TERUKUR |
| Frame maju penuh | `motor 1 −1.800`, `2 −1.800`, `3 +1.800`, `4 +1.800` rps | TERUKUR (in-process) |
| Dashboard LIVE | `CONNECTED` + badge `LIVE`, `http 200` | TERVERIFIKASI |
| Label UI | "MAJU/MUNDUR SAMPAI ~0.33 M/S", batas `x 0.34` | TERVERIFIKASI |
| Kestabilan layout | rect tombol identik sebelum/sesudah teks panjang | TERUKUR |
| Stash `lidar-wip-phase1` | utuh | TERVERIFIKASI |

Tidak ada tombol arah yang ditekan di hardware selama perbaikan §5–§8. Robot
tidak bergerak sekali pun karena perubahan ini.

---

## 11. Yang BELUM terverifikasi

1. **Kecepatan 1,80 rps di lantai.** Belum ada pengukuran. Yang harus diukur:
   slider penuh + tahan 3 detik → seharusnya **±99 cm** (0,330 m/s × 3 s). Kalau
   hasilnya jauh lebih pendek, motor tidak mencapai laju yang diminta dan
   menaikkan rps lagi hanya menambah arus tanpa menambah kecepatan.
2. **Lurus atau melengkung pada 1,80 rps.** Roller mecanum bisa mulai selip.
3. **Motor 3 di lantai** dengan `--settle 3.0`. Temuan lama "depan kanan tidak
   berputar" belum diuji ulang dan bisa jadi artefak dead window.
4. **TUGAS 1C motor 3 & 4, 1D, TUGAS 2, TUGAS 3 (sampling kiri/kanan + 2
   diagonal), TUGAS 4 (fail-safe A–D).** Semua ini butuh gerakan nyata.
5. **Laporan §7 final** untuk brief awal — belum bisa ditulis karena item 4
   belum ada datanya.

Catatan metode: brief awal menetapkan aturan *"tanpa u>1,0"*. Perubahan
`MAX_FORWARD_RPS` ke 1,80 **melampaui aturan itu**, atas permintaan eksplisit
operator untuk mempercepat maju/mundur. Ini deviasi yang disadari, dan
konsekuensinya adalah item 1 dan 2 di atas.

---

## 12. Langkah berikutnya

1. Cas baterai sampai penuh.
2. Ukur kecepatan maju/mundur di lantai: slider penuh, tahan 3 detik, ukur jarak
   dengan penggaris. Target ±99 cm. Kalau melengkung atau roda selip, turunkan
   `MAX_FORWARD_RPS` (1,60 → 0,29 m/s; 1,40 → 0,26 m/s).
3. Uji motor 3 di lantai dengan `--settle 3.0` sebelum menyimpulkan kerusakan
   mekanis.
4. Lanjutkan TUGAS 1C (motor 3 & 4) dengan roda terangkat dan banner jeda 8 detik,
   karena observasi roda butuh mata operator di titik yang tepat.
5. Setelah gerak terbukti: TUGAS 1D, 2, 3, 4, lalu laporan §7 final.

---

## Lampiran — cara menjalankan

```bash
# launcher LIVE (di luar repo): mematikan dashboard lama, cek /dev/ttyACM0,
# lalu menjalankan dengan --chassis-live
~/amr_live.sh 8080

# kalau perlu manual
fuser -k 8080/tcp
cd ~/AMRTestLander/AMR_LKS_Dashboard
../.venv/bin/python run_dashboard.py --chassis-live --chassis-port /dev/ttyACM0 \
  --host 0.0.0.0 --port 8080

# uji roda: WAJIB --settle 3.0, dan MOVE diketik manual (tanpa --yes)
../.venv/bin/python scripts/wheel_test.py --confirm --port /dev/ttyACM0 \
  --rate 50 --duration 3 --settle 3.0 --speeds "1:-0.6,2:-0.6,3:+0.6,4:+0.6"

# test & lint
../.venv/bin/python -m pytest -q
../.venv/bin/ruff check .
```
