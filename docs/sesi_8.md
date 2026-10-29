# Sesi 8 — Arm yang bisa dikendalikan halus: slider, bukan klik berkali-kali

**Status: SELESAI untuk perubahan kode arm, BELUM TERVERIFIKASI untuk gerak arm
nyata — kendali arm sekarang slider per sendi (satu geser = satu perintah, durasi
= jarak / kecepatan) dan perintah baru dikirim setelah slider **berhenti 0,35 s**
(ronde 2, memperbaiki gerakan tersendat). Sesi ini juga membuka **kamera**: dari
"0 perangkat" menjadi **frame depth nyata tersimpan** — tetapi kamera belum masuk
dashboard, karena SDK-nya C++ tanpa binding Python dan Pi ini belum punya
compiler (lihat §11). Panel arm sudah ter-render dan tersambung ke board, jalur
perintahnya diverifikasi di browser lewat board palsu (PTY), namun **belum ada
satu perintah gerak pun yang dikirim ke arm asli**: uji gerak pertama tetap milik
operator. Tidak ada aktuasi di sesi ini.**

**Tanggal:** 2026-10-29 (WIB, UTC+07:00)
**Host:** `stematel-pi5` (Raspberry Pi 5, Ubuntu 24.04.5 LTS ARM64)
**Repo:** `/home/stematelpi5/AMRTestLander/AMR_LKS_Dashboard` (branch `main`, HEAD `2f4dd86`)
**Stash yang dipertahankan:** `stash@{0}: On main: lidar-wip-phase1` — utuh, tidak disentuh
**Python:** `~/AMRTestLander/.venv/bin/python`

Grade bukti:

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
| §2 | baseline sesi | tidak |
| §3 | temuan utama | tidak |
| §4 | uji / eksperimen | tidak |
| §5 | akar masalah & perbaikan | tidak |
| §6 | daftar file yang berubah | tidak |
| §7 | verifikasi | tidak (baca posisi saja) |
| §8 | yang BELUM terverifikasi | — |
| §9 | langkah berikutnya | — |

---

## 1. Ringkasan

1. Operator menilai panel arm versi pertama (sesi 7, §11.9) tidak bisa dipakai:
   *"itu lambat banget. Mana harus di klik2 terus biar keliatan gerak"*. Keluhan
   itu benar dan bisa dihitung dari kode sendiri: tiap tekan = 10 pulse dalam
   0,8 s, jadi memindahkan satu sendi 200 pulse = 20 klik ≈ 20 detik berdiri di
   depan layar. Kelambatan itu **pilihan desain panel**, bukan batas hardware:
   frame `set position` sudah membawa durasi dalam milidetik, jadi satu frame
   bisa membawa seluruh gerakan.
2. Perbaikan: panel arm diganti dari tombol −10/+10 menjadi **slider per sendi**
   (rentang = limit terukur servo itu) + **slider kecepatan** 40-400 pulse/s.
   Satu geser = satu perintah; durasi dihitung `jarak / kecepatan`, minimal
   0,5 s. Kecepatan default 150 pulse/s diambil dari action group pabrik sendiri
   (115-220 pulse/s, dibaca 28 Okt), jadi 200 pulse = 1,3 s dalam **satu** frame.
3. Pengiriman di-paced oleh timer 5 Hz (`flush`), supaya geseran slider yang
   memicu puluhan event tidak membanjiri board: satu sendi satu frame per flush,
   selalu nilai terakhir. Tombol −10/+10 tetap ada sebagai penyetel halus.
4. Yang **tidak** berubah: gripper (servo 10) tetap tidak ada di panel dan tetap
   ditolak lapisan transport; target tetap di-clamp ke limit terukur; servo yang
   tidak menjawab tidak digerakkan berdasarkan tebakan; STOP membatalkan
   target yang masih tertunda.
5. Tidak ada aktuasi di sesi ini. Yang dijalankan di hardware hanya **membuka
   port dan membaca posisi**; semua klaim gerak di file ini masih berupa kode +
   test, bukan gerakan yang terlihat.
6. **Ronde 2 (setelah operator melaporkan "defaultnya udah nyendet2 banget").**
   Penyebab yang paling mungkin ada di panel, bukan di servo: tiap event geseran
   slider dulu mengirim satu frame, jadi servo di-re-target ±5 kali per detik dan
   setiap frame membawa jam geraknya sendiri → profil gerak servo di-restart terus
   → terlihat tersendat. Perbaikan: slider hanya **mencatat** target; board baru
   menerima perintah setelah handle berhenti 0,35 s (`SETTLE_S`). Tombol −10/+10
   tetap dikirim seketika. Diverifikasi di browser dengan board palsu (PTY):
   satu geseran 1,5 s = **nol** frame saat digeser, **satu** frame 0,3-0,4 s
   setelah berhenti. Kandidat kedua — servo mengabaikan/menafsir lain kolom
   durasi — **belum** dikecualikan dan butuh uji `--trace` di arm asli (§8).
   Detail: §10.

## 2. Baseline

| Item | Nilai | Grade |
| --- | --- | --- |
| HEAD repo | `2f4dd86 fix: the arm panel reports an unopened port honestly, and retries rebuild it` | TERVERIFIKASI |
| Tree sebelum kerja | bersih, `main...origin/main` | TERVERIFIKASI |
| Stash | `stash@{0}: On main: lidar-wip-phase1` | TERVERIFIKASI |
| Test baseline | 446 passed | TERVERIFIKASI |
| Port board saat sesi mulai | `/dev/ttyACM0` dipegang pid 2835 (dashboard operator, `--arm-live`, port 8080, start 10:14) | TERUKUR |
| Port LiDAR | `/dev/ttyUSB0` hidup, dashboard membaca 436 paket/s | TERUKUR |

## 3. Temuan utama

### 3.1 Gejala

Kutipan operator, persis:

> "serius aja dah, itu lambat banget. Mana harus di klik2 terus biar keliatan
> gerak. Biar smooth tolong cara controlnya diapain dulu biar ga apakali itu."

### 3.2 Bukti

| Probe | Yang diukur | Hasil | Grade |
| --- | --- | --- | --- |
| Baca `robot_panel._live_arm_panel` (sesi 7) | besar langkah per klik | 10 pulse, `duration_s=0.8`, dan **satu** `read_positions` (timeout 0,2 s) sebelum tiap klik | TERVERIFIKASI |
| Hitung biaya satu reposisi | 200 pulse | 20 klik × (0,8 s + latensi baca) ≈ 20-24 s | INFERENSI (aritmetika dari kode) |
| `arm_bus.build_set_position_frame` | isi frame | payload membawa `duration_ms` (`<BHB`), jadi satu frame boleh membawa seluruh jarak | TERVERIFIKASI |
| Action group pabrik (`docs/sesi_7.md` §11.8) | kecepatan sendi versi pabrik | 500→720 dalam 1500 ms (147 pps), 125→250 dalam 1000 ms (125 pps), 165→330 dalam 1000 ms (165 pps) | SOURCE-ONLY (tabel vendor, belum dijalankan) |
| `ps -p 2835` | siapa yang memakai board | `run_dashboard.py --arm-live --chassis-port /dev/ttyACM0 --port 8080`, dijalankan operator 10:14 lewat `~/amr_arm_live.sh` | TERUKUR |

### 3.3 Kesimpulan

Yang boleh diklaim: penyebab kelambatan sudah pasti dan ada di panel, bukan di
servo atau board; dan panel baru mengirim satu frame untuk jarak berapa pun.

Yang **tidak** boleh diklaim: bahwa gerakannya benar-benar halus. Itu kontrak
vendor (kolom `Time` pada action group) dan belum dilihat di arm ini. Kalau
servo ternyata tidak menghormati durasi, gerakan besar tetap akan terasa patah —
karena itu ada slider kecepatan, dan itu alasan pertama untuk uji gerak
berikutnya.

## 4. Uji / eksperimen

Tidak ada uji gerak di sesi ini (tidak ada aktuasi). Yang dijalankan:

| Trial | Parameter | Hasil | Gerak | Catatan |
| --- | --- | --- | --- | --- |
| Pre-flight dashboard arm ke-2 | `run_dashboard.py --arm-live --port 8099 --no-lidar` | port **ditolak**: `OSError: /dev/ttyACM0 is already open in another process (pid 2835)`; halaman 8099 tetap ter-render, panel Arm berkata belum tersambung + sebabnya | tidak | Perilaku ini memang yang diminta di sesi 7 §11.9.1 — bukan bug, tapi bukti ke-2 bahwa satu port satu pemegang |
| Restart dashboard operator | `~/amr_arm_live.sh 8080` | pid 2835 dimatikan, dashboard baru `adopted open port /dev/ttyACM0 @ 1000000`, listen di 0.0.0.0:8080 | tidak | Skrip launcher mematikan pemegang port lama di port yang sama |
| Baca DOM panel (browser, sesi ini) | halaman 8080 | panel "ARM CONTROL (LIVE)" + badge `CONNECTED`; kecepatan tertulis 150 pulse/s; posisi terbaca `1:565 2:533 3:-5 4:352 5:639`; lima baris slider sendi + tombol −10/+10 + BACA POSISI + STOP | tidak (baca posisi saja) | Membuktikan panel baru benar-benar ter-render di mesin nyata dan tersambung |

## 5. Akar masalah & perbaikan

**Akar masalah 1 — langkah per klik terlalu kecil dan tiap klik membaca posisi dulu.**
Gejala: 200 pulse butuh 20 klik. Sebab: panel mengikat "satu tekan = 10 pulse",
dan sebelum tiap perintah ia melakukan `read_positions` (timeout 0,2 s) supaya
tidak bergerak dari posisi basi, sehingga tiap klik ≈ 1 s. Bukti: kode sesi 7
§11.9. Perbaikan: target absolut dari slider (bukan delta dari posisi terakhir)
— jadi membaca dulu tidak diperlukan lagi untuk keselamatan, karena targetnya
memang sudah dibatasi limit servo itu sendiri; pembacaan tetap ada untuk
menampilkan posisi nyata. Verifikasi tanpa aktuasi: `tests/test_dashboard_arm_smooth.py`
memastikan satu geser (walaupun memicu 20 event slider) mengirim **satu** frame.

**Akar masalah 2 — durasi tetap 0,8 s tanpa melihat jarak.**
Gejala: gerakan 10 pulse sama lambatnya dengan gerakan 200 pulse. Sebab: durasi
hard-code 0,8 s. Perbaikan: `plan_move()` menghitung `durasi = |Δ| / kecepatan`,
dibatasi minimal `MIN_DURATION_S` (0,5 s) dan maksimal 8 s (supaya tidak diam-diam
mempercepat permintaan operator, mis. seluruh rentang 900 pulse pada 40 pulse/s =
22 s). Kecepatan default 150 pulse/s = di dalam pita action group pabrik.

**Akar masalah 3 — slider bisa membanjiri board.**
Gejala potensial (belum terukur, dicegah): Quasar mengirim event slider tiap
gerakan jari (`throttle=0.05` di NiceGUI), jadi satu geser bisa jadi puluhan
frame. Sebab: handler langsung mengirim. Perbaikan: panel hanya **mencatat**
target (`set_target`), dan `flush()` dipanggil `ui.timer` 0,2 s → satu sendi satu
frame per flush, selalu nilai terakhir. Ini juga membuat STOP bisa mengosongkan
target yang belum sempat terkirim.

**Akar masalah 4 — `commanded` vs posisi nyata.**
Durasi frame kedua dihitung dari pulse terakhir yang **kita perintahkan**, bukan
dari posisi awal pembacaan; kalau operator menarik slider lebih jauh daripada
gerak arm, arm menjadi lambat (bukan menyentak), yang merupakan arah gagal yang
aman. Setiap pembacaan posisi yang berhasil membuang nilai `commanded` itu
(`ArmJogController.refresh`), jadi basisnya kembali ke kenyataan.

## 6. Daftar file yang berubah

| File | +/− | Isi perubahan | Mengapa |
| --- | --- | --- | --- |
| `src/amr_dashboard/arm_jog.py` (baru) | +322 / −0 | `DEFAULT_SPEED_PPS=150`, `MIN_SPEED_PPS=40`, `MAX_SPEED_PPS=400`, `MAX_DURATION_S=8.0`, `POSITION_MAX_AGE_S=2.0`, `FLUSH_INTERVAL_S=0.2`, `SETTLE_S=0.35`, `clamp_speed()`, `MovePlan`, `JogResult`, `plan_move()`, kelas `ArmJogController` (`set_target` + `immediate`, `settled`, `preview`, `plan_for`, `flush`, `stop`, `refresh`, `position`, `start_for`, `set_speed`) | memisahkan perencanaan gerak halus dari UI supaya bisa diuji tanpa NiceGUI dan tanpa hardware; kecepatannya dari action group pabrik; jendela settle adalah perbaikan gerakan tersendat (ronde 2) |
| `src/amr_dashboard/robot_panel.py` | +151 / −33 | `_live_arm_panel` ditulis ulang: slider per sendi (min/max = limit terukur), slider kecepatan, label rencana (`target (~durasi)`), label status flush, `sync_sliders()` dengan penjaga `controller.syncing`, `on_slide()` (hanya mencatat target), `nudge()` (immediate), `tick()` (timer 0,2 s), `stop()`; impor `arm_jog` + `Any` | keluhan operator: klik berkali-kali diganti satu geser; geseran yang mengirim frame tiap event diganti sekali kirim setelah slider berhenti |
| `src/amr_dashboard/chassis_transport.py` | +15 / −0 | `is_pty()`; `other_processes_holding()` melewati cek pemegang port untuk `/dev/pts/*` | harness board palsu (`tools/fake_board_pty.py`) menjawab lewat PTY, dan pemegang master PTY selalu terdeteksi; pagar tetap seketat sebelumnya untuk perangkat asli (`/dev/ttyACM0` tetap ditolak kalau ada pemegang lain) |
| `src/amr_dashboard/app.py` | +3 / −2 | teks banner `ARM LIVE` saat start: menerangkan slider dan kecepatan (sebelumnya menulis "satu tekan = 10 pulse / 0,8 s") | banner yang menyesatkan lebih buruk daripada tidak ada banner |
| `tests/test_dashboard_arm_smooth.py` (baru) | +385 / −0 | 24 test: satu geser = satu frame; 20 event slider = 1 frame (nilai terakhir); geseran yang masih berjalan = 0 frame sampai settle; tombol = immediate; dua sendi = dua frame; clamp limit; durasi proporsional & lantai 0,5 s; servo diam tidak digerakkan; gripper ditolak; sync programatik bukan perintah; STOP membuang target & tidak menyebut id 10; `flush` tidak melempar saat port mati; PTY dikecualikan dari cek pemegang port; interval flush ≤ 0,25 s | mengunci janji "halus" dengan angka, bukan dengan tangkapan layar |
| `docs/sesi_8.md` (baru) | +886 / −0 | dokumen sesi ini, termasuk §11-§19 (kamera, board, uji gerak lantai, jalur dashboard + watchdog, integrasi kamera ke panel): `wc -l` = 990 pada akhir sesi (886 saat tabel ini ditulis; §19 menyusul di ronde yang sama) | log wajib per sesi |

Total: **+169 insertions, −35 deletions** di 3 file terlacak, ditambah 3 file baru
(+1798 baris: `arm_jog.py` 322, `test_dashboard_arm_smooth.py` 385, `sesi_8.md` 886 saat itu
→ 990 setelah §19; ronde kamera di §19 menambah 5 berkas terlacak +2 berkas repo baru, lihat §19.1).
Sesi 7 tidak diubah. Berkas kerja kamera (§11-§13) semuanya di luar repo, jadi
tidak menambah baris di repo.

File bantu di luar repo (tidak ikut ter-commit; daftar lengkap di §10.5):
`~/amr_arm_live.sh` — launcher arm LIVE (mematikan dashboard lama di port yang
sama, memperingatkan kalau port board dipegang proses lain);
`~/AMRTestLander/tools/fake_board_pty.py` — board palsu pada PTY untuk menguji
panel tanpa hardware; `~/AMRTestLander/tools/arm_move_test.py` — ditambah
`--trace` untuk merekam pola gerak servo; `~/AMRTestLander/tools/ARM_TEST.txt` —
berkas instruksi operator (tidak bisa menyalin dari chat);
`~/AMRTestLander/tools/logs/arm_panel_smooth_*.log` dan
`logs/fake_board_*.txt` — log pre-flight, run panel, dan uji PTY.

## 7. Verifikasi

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **471 passed** (446 baseline + 25 test arm halus) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| Panel baru ter-render di mesin nyata | ya: badge `CONNECTED`, slider per sendi, kecepatan 150 pulse/s, posisi terbaca dari servo | TERUKUR |
| Port board | `adopted open port /dev/ttyACM0 @ 1000000`, satu pemegang | TERUKUR |
| Perintah gerak dikirim ke arm asli sesi ini | **nol** (tidak ada drag, tidak ada tombol gerak ditekan) | TERVERIFIKASI |
| Geseran slider di browser sungguhan → board palsu (PTY) | 6 event geser selama 1,5 s: **nol** frame saat handle bergerak, **satu** frame `GERAK duration=591 ms count=1 1:695` 0,3-0,4 s setelah handle berhenti; 591 ms = (695−500)/330 pps | TERUKUR |
| Klik tombol `+10` di browser → board palsu | `GERAK duration=500 ms count=1 1:705` seketika (lantai `MIN_DURATION_S`), tanpa frame lanjutan | TERUKUR |
| Slider kecepatan di browser | label server berubah `kecepatan: 330 pulse/s` — membuktikan event slider sungguhan sampai ke server | TERUKUR |
| Ambiguitas ronde 1 | percobaan pertama ronde 2 memasang handler pada event `change` Quasar (diasumsikan "saat dilepas"); event itu tidak pernah terbukti terkirim, dan desain itu **dibuang** — sekarang hanya memakai `on_change` + jeda settle, yang justru terbukti di atas | TERUKUR |

## 8. Yang BELUM terverifikasi

0. **Apakah gerakan aslinya sudah tidak tersendat.** Ronde 2 memperbaiki penyebab
   yang paling mungkin (re-targeting tiap event geseran), tetapi ia **belum**
   diuji di arm asli. Cara menutupnya: reload dashboard, geser satu sendi satu
   kali, lalu lepas; kalau masih tersendat, catat apakah tersendat **saat
   digeser** atau **setelah dilepas, pada satu perintah tunggal**.
1. **Gerakan halus yang sebenarnya.** Semua klaim durasi masih di kertas dan di
   test. Cara menutupnya: lengan diamankan/dipegang, satu sendi, satu geser
   pendek, kecepatan default; catat apakah gerakannya rata atau patah.
2. **Apakah servo menghormati durasi yang diminta.** Ini kontrak vendor
   (kolom `Time` action group), SOURCE-ONLY di unit ini. Cara menutupnya:
   `arm_move_test.py --trace` (baru, lihat §10) merekam posisi 20 kali/detik
   selama gerak dan menyimpulkan polanya: RAMP = durasi dihormati,
   BERTANGGA = interpolasi kasar, PANTUL = durasi diabaikan → perbaikannya
   menjadi streaming setpoint bertahap.
3. **`sendi 3` melaporkan `-5`** padahal limit terukurnya `0-900`, dan slider
   memaksa tampilannya ke 0. Belum jelas apakah itu toleransi encoder atau limit
   yang kurang tepat. Cara menutupnya: `tools/arm_probe.py --confirm` diulang
   pada sendi 3, bandingkan limit yang dibaca servo dengan nilai limit di
   `MEASURED_LIMITS`.
4. **Beban torsi saat gerakan besar.** Semua gerakan yang pernah terukur di arm
   ini hanya 16 pulse (sesi 7 §11.4). Gerakan 200-900 pulse pada kecepatan
   150 pulse/s belum pernah dicoba; belum ada data apakah servo kuat atau
   tersendat.
5. **`--chassis-live` + `--arm-live` bersamaan** masih tidak bisa (dua handle
   pada satu port) — keterbatasan sesi 7 §11.9.1 yang belum diperbaiki.
6. **Item sesi 6/7 yang tetap terbuka**: botol untuk uji visual plot LiDAR,
   `±99 cm` gerak dari dashboard, motor 3 & 4 di lantai, `ScanPoint.xy()`.

## 9. Langkah berikutnya

1. Operator: **reload** halaman `http://10.70.198.226:8080/` (dashboard sudah
   di-restart dengan panel ronde 2), lalu geser satu sendi satu kali dan lepas.
   Bilang apa yang terlihat — kuitkan sebagai hasil uji, dan itu menutup §8.0.
2. Kalau masih tersendat, jalankan uji terukur (butuh izin operator karena
   menggerakkan arm asli, satu sendi, 40 pulse, lengan dipegang):

       ~/AMRTestLander/.venv/bin/python ~/AMRTestLander/tools/arm_move_test.py \
           --id 5 --target <posisi_sekarang+40> --duration 1500 --max-step 40 \
           --trace --confirm

   Lalu ketik `MOVE`. Log `tools/logs/arm_move_<stamp>.txt` memuat jejak posisi
   20 kali/detik dan kesimpulan polanya (RAMP / BERTANGGA / PANTUL). Itu
   menutup §8.2 dan menentukan perbaikan berikutnya.
3. Kalau gerakan ternyata patah pada satu perintah tunggal: turunkan kecepatan
   lewat slider dulu (40 pulse/s, tanpa ubah kode) sebelum menyimpulkan soal
   servo.
4. Kalau sudah halus: putuskan commit sesi ini (tiga file kode + satu file test +
   dokumen ini belum ter-commit).

---

## 10. Ronde 2 — "defaultnya udah nyendet2 banget"

Kutipan operator, persis:

> "AKu blom test speed, tapi defaultnya udah nyendet2 banget loh itu"

### 10.1 Kandidat penyebab dan mana yang bisa dipisahkan tanpa hardware

| Kandidat | Dasar | Cara memisahkan |
| --- | --- | --- |
| Panel mengirim frame tiap event geseran, jadi servo di-re-target ±5×/detik dan profil geraknya di-restart terus | Kode ronde 1: `flush()` 5 Hz, dan tiap frame membawa `duration_ms` sendiri | **Terukur tanpa hardware**: board palsu di PTY + browser sungguhan (di bawah) |
| Servo mengabaikan/menafsir lain kolom durasi (`duration_ms`) sehingga ia bergerak secepatnya lalu memantul di target | Kontrak vendor belum pernah diuji di unit ini; `MIN_DURATION_S` 0,5 s juga hanya pagar buatan sendiri, bukan hasil ukur | Butuh aktuasi: `arm_move_test.py --trace` (§8.2) |
| Servo sengaja menginterpolasi kasar (langkah besar per tick internal) | Tidak ada bukti langsung; pembacaan sesi 7 hanya 16 pulse | Sama: jejak posisi `--trace` |

Yang **dibuang** pada ronde ini: ide pertama adalah memasang handler pada event
`change` Quasar (diasumsikan "hanya saat handle dilepas"). Event itu tidak pernah
terbukti terkirim, jadi desainnya dibuang dan diganti jeda settle — yang di bawah
ini justru terbukti.

### 10.2 Perbaikan

1. `SETTLE_S = 0.35` di `arm_jog.py`. Slider hanya **mencatat** target
   (`set_target`); `flush()` hanya mengirim sendi yang nilainya sudah berhenti
   berubah selama 0,35 s. Jadi selama handle bergerak, **nol** frame; begitu
   berhenti, **satu** frame berisi nilai akhir.
2. Tombol −10/+10 memakai `set_target(..., immediate=True)`: satu tindakan
   sengaja, dikirim pada flush berikutnya, tidak menunggu settle.
3. Jalur durasi tetap sama seperti ronde 1 (durasi = jarak / kecepatan).

### 10.3 Verifikasi tanpa menyentuh hardware

Alat baru: `~/AMRTestLander/tools/fake_board_pty.py` — board palsu pada sebuah
PTY: menjawab pembacaan posisi dengan pulse tetap dan mencatat **setiap** frame
yang diterimanya ke `tools/logs/fake_board_<stamp>.txt`. Dashboard dijalankan
dengan `--arm-live --chassis-port /dev/pts/N`, lalu panel digeser dari browser
sungguhan (event mouse tepercaya via CDP).

| Uji | Hasil | Gerak |
| --- | --- | --- |
| Geser slider sendi 1: 6 event selama 1,5 s, kecepatan 330 pulse/s | **nol** frame selama handle bergerak; setelah handle berhenti 0,3-0,4 s: `GERAK duration=591 ms count=1  1:695` (591 ms = (695−500)/330) | tidak |
| Klik tombol `+10` | `GERAK duration=500 ms count=1  1:705` seketika (lantai 0,5 s), tanpa frame lanjutan | tidak |
| Geser slider kecepatan | label server berubah menjadi `kecepatan: 330 pulse/s` | tidak |
| Test suite | **471 passed** (446 baseline + 25 test) | tidak |

Yang **tidak** dibuktikan uji ini: bahwa gerakan servo sendiri jadi rata. Board
palsu membuktikan **apa yang dikirim panel**, bukan bagaimana servo meresponsnya.

### 10.4 Konsekuensi ke `chassis_transport.py`

Harness di atas butuh dashboard mau membuka `/dev/pts/N`; cek pemegang port
selalu menolaknya, karena pemegang master PTY memang harus ada (itu board
palsunya). Ditambahkan `is_pty()` dan pengecualian `/dev/pts/*`. Pagar untuk
perangkat asli **tidak** dilonggarkan: `/dev/ttyACM0` tetap ditolak kalau ada
proses lain memegangnya (ada test-nya).

### 10.5 File bantu di luar repo (tidak ikut ter-commit)

- `~/amr_arm_live.sh` — launcher arm LIVE (mematikan dashboard lama di port yang
  sama, memperingatkan kalau port board dipegang proses lain).
- `~/AMRTestLander/tools/fake_board_pty.py` — board palsu pada PTY untuk menguji
  panel tanpa hardware.
- `~/AMRTestLander/tools/arm_move_test.py` — ditambah `--trace`, `--trace-hz`,
  `--trace-seconds`; merekam dan menganalisis jejak posisi saat gerak nyata.
- `~/AMRTestLander/tools/logs/arm_panel_smooth_*.log`,
  `logs/fake_board_*.txt` — log pre-flight, run panel, dan uji PTY.

---

## 11. Kamera Deptrum Aurora 930 — dari "0 perangkat" ke frame nyata

Operator mengerjakan langkah sudo yang tertulis di `tools/CAMERA_SUDO.txt`
bagian 1 dan 2, lalu bertanya "ini kan ya bener?". Bagian ini mencatat hasil
pemeriksaannya dan apa yang ditemukan sesudahnya. **Tidak ada aktuasi** — kamera
bukan aktuator; yang dijalankan hanya membuka perangkat, membaca frame, dan
menyimpannya.

### 11.1 Apa yang operator jalankan, dan apa buktinya

| Langkah operator | Bukti setelahnya | Grade |
| --- | --- | --- |
| `sudo cp .../scripts/99-deptrum-libusb.rules /etc/udev/rules.d/` | `/etc/udev/rules.d/99-deptrum-libusb.rules` ada, 88 B, isinya persis satu baris pabrik (`ATTRS{idVendor}=="3251", MODE:="0666"`) | TERVERIFIKASI |
| `sudo udevadm control --reload-rules && sudo udevadm trigger` | `/dev/bus/usb/002/003` berubah dari `crw-rw-r--` menjadi **`crw-rw-rw-`** | TERUKUR |
| `sudo apt-get install -y libusb-1.0-0-dev libudev-dev` + `libgl1-mesa-dev libglu1-mesa-dev libxi-dev` | terpasang (hanya perlu untuk GUI/scope; biner sample tidak memakainya) | TERVERIFIKASI |

Jadi jawaban untuk pertanyaannya: **ya, benar** — dan itu memang satu-satunya
langkah yang membuka kamera.

### 11.2 Hambatan kedua yang ternyata bisa dilewati tanpa sudo: `libgomp`

`hello_deptrum` dulu gagal sebelum menyentuh kamera:
`error while loading shared libraries: libgomp.so.1`. Paket `libgomp1` tidak
terpasang dan tidak ada salinannya di sistem. Diakali **tanpa sudo**, memakai
paket resmi Ubuntu:

```bash
cd ~/.hermes/cache/scratch/gomp
apt-get download libgomp1          # 145 kB
dpkg-deb -x libgomp1_*.deb ./root  # -> root/usr/lib/aarch64-linux-gnu/libgomp.so.1
```

`~/camera_hello.sh` memakai path itu otomatis. Kalau nanti environment-nya
di-reset, langkah 3 baris di atas yang harus diulang.

### 11.3 Perangkat sekarang: terdeteksi dan bisa dibuka

`tools/camera_usb_probe.py` (libusb langsung, tanpa SDK, read-only):

| Yang diukur | Hasil | Grade |
| --- | --- | --- |
| libusb melihat perangkat | bus 2, alamat 3, `3251:1930`, `bcdUSB 0x0200`, 480M (USB 2 high) | TERUKUR |
| `libusb_open()` | **0 SUCCESS** (sebelum udev: **-3 ACCESS**) | TERUKUR |
| Port USB | bus 2 (480M) port 2; bus 003/005 (5000M) kosong | TERUKUR |

`hello_deptrum` (biner pabrik, aarch64, tanpa build):

```
index(0):\t device_addr:3 usb_port(2-2)
ir_pid:0x1930, rgb_pid:0x0
serial number:HY400516001016707G00028
SDK version: 1.1.19
Device name: Aurora930
```

Dua hal yang perlu dibaca dari situ: **serial bisa dibaca** (bukti komunikasi dua
arah, bukan sekadar enumerasi), dan **`rgb_pid:0x0`** — unit ini tidak
melaporkan sensor RGB, jadi jangan menjanjikan gambar warna; yang pasti ada
adalah IR/depth. Grade TERUKUR.

### 11.4 Frame nyata berhasil diambil

`sample_lite` adalah menu interaktif, tetapi sumbernya ada
(`samples/src/sample_lite/sample_lite.cc`) sehingga urutan pertanyaannya bisa
dibaca dan dijawab dari pipa. `tools/camera_capture.py` melakukan itu (dengan
jeda supaya streaming benar-benar jalan sebelum permintaan simpan datang).

Hasil satu kali jalan (`--stream depth`, mode 0):

| Yang diukur | Hasil | Grade |
| --- | --- | --- |
| Berkas frame | 10 × `depth_<index>_<timestamp>.raw`, masing-masing **128000 B** | TERUKUR |
| Ukuran vs mode | 128000 = 320 × 200 × 2 → konsisten dengan uint16 320x200 | TERVERIFIKASI |
| Laju | timestamp berjarak 100 ms (index 61→70) → **~10 fps**, walau diminta 30 | TERUKUR |
| Isi frame | 31,1 % piksel 0 (invalid), nilai valid 184-303, median 231 | TERUKUR |
| Satuan depth | **uint16 dalam mm** — dari SDK User Guide: "The data type for each pixel in the depth and ir streams is uint16_t, where depth is measured in mm" | SOURCE-ONLY (dokumen) |
| Pratinjau ASCII | ada struktur nyata (gradasi jauh→dekat + siluet objek), bukan derau | TERUKUR |

**Penting soal angka itu:** 184-303 mm berarti kamera sedang melihat sesuatu
pada 18-30 cm, sedangkan *Operating Range* pabrik 30-300 cm (dan 31 % piksel
invalid). Jadi frame-nya nyata, tetapi **arah kamera terlalu dekat** — inilah
yang harus diulang setelah kamera diarahkan ke ruangan untuk melihat nilai
depth yang wajar (ratusan sampai ~3000 mm).

Jenis stream yang dilaporkan perangkat (dibaca dari daftar `GetSupportedStreamType`
oleh `sample_lite`, TERUKUR): `Rgb, Ir, Depth, Rgbd, RgbIr, DepthIr, RgbdIr,
PointCloud, RgbdPointCloud`. Mode frame yang ditawarkan: IR 8-bit 320x200 /
480x300 / 640x400, RGB YUV pada resolusi yang sama, dengan kolom `depth_mode`
tertulis **`kInvalid`** — belum jelas artinya (perlu dibaca ulang bersama
dokumentasi), jadi jangan dijadikan dasar apa pun dulu.

### 11.5 Yang menghalangi kamera masuk dashboard

Sudah dipastikan dengan membaca header dan mencari biner di sistem:

1. **SDK-nya C++ saja.** `include/deptrum/*.h` mendefinisikan kelas virtual
   (`deptrum::stream::Stream`, `DeviceManager`), **tidak ada `extern "C"`**, dan
   `.so` hanya mengekspor simbol C++ ter-mangle (4391 simbol). Jadi `ctypes` dari
   Python bukan jalan yang wajar.
2. **Tidak ada binding Python** di paket kamera (tidak ada berkas `.py`).
3. **Tidak ada compiler di Pi ini**: `gcc`, `g++`, `cc`, `clang`, `make`, `cmake`
   semuanya tidak ada (`command -v` kosong). Sumber sample-nya ada, tapi tidak
   bisa dibangun.
4. Biner `sample` (viewer) butuh layar/OpenCV highgui — headless tidak jalan;
   `sample_lite` tidak bisa dipakai sebagai streamer jangka panjang karena hanya
   menulis berkas .raw (128 KB per frame, ~1,3 MB/s ke kartu SD).

Jadi **satu langkah yang tersisa dan butuh password**:

```bash
sudo apt-get install -y g++
```

Setelah itu, tanpa sudo lagi: bangun pembaca kecil (~100 baris, mengikuti
`sample_lite.cc`) yang menulis frame depth ke pipa/berkas, lalu dashboard
membacanya — bukan ROS, bukan viewer.

### 11.6 Alat baru di luar repo (tidak ikut ter-commit)

| Berkas | Fungsi |
| --- | --- |
| `~/AMRTestLander/tools/camera_usb_probe.py` | probe libusb read-only: perangkat terlihat? bisa dibuka? (bukti `-3 ACCESS` vs `0 SUCCESS`) |
| `~/AMRTestLander/tools/camera_capture.py` | menggerakkan `sample_lite` dari pipa dan menyimpan frame |
| `~/AMRTestLander/tools/camera_frame_check.py` | statistik + pratinjau PNG satu frame .raw |
| `~/camera_hello.sh` | menjalankan `hello_deptrum` / `sample_lite` dengan `LD_LIBRARY_PATH` yang benar |
| `~/AMRTestLander/tools/CAMERA_SUDO.txt` (v3) | instruksi sudo; bagian 1 sudah dijalankan operator |
| `~/AMRTestLander/tools/logs/camera_*.txt` | log tiap percobaan |

### 11.7 Yang BELUM terverifikasi (kamera)

1. **Nilai depth yang wajar.** Semua frame sejauh ini pada 18-30 cm (di bawah
   *Operating Range* 30 cm). Cara menutupnya: arahkan kamera ke ruangan
   (0,5-3 m), jalankan `camera_capture.py` lagi, lalu `camera_frame_check.py`;
   median harus ratusan sampai ~3000 mm.
2. **Laju frame sesungguhnya.** Diminta 30 fps, terukur ~10 fps pada satu
   percobaan; belum dipisahkan apakah itu batas USB 2, batas SDK, atau efek
   jalur simpan-berkas.
3. **Stream lain** (`DepthIr`, `PointCloud`, `Rgbd`) belum pernah dicoba; RGB
   kemungkinan besar tidak ada (`rgb_pid:0x0`).
4. **Arti `depth_mode = kInvalid`** pada tabel mode frame.
5. **Akurasi depth** (pabrik: 8 mm @1 m) belum diuji dengan objek berjarak
   diketahui.

---

## 12. Ronde kamera 2 — `g++` dipasang, pipa frame ke dashboard sudah terbukti

Operator memasang `g++` dan mengarahkan ulang kamera, lalu minta diperiksa.

### 12.1 Keadaan setelah langkah operator

| Yang diperiksa | Hasil | Grade |
| --- | --- | --- |
| Compiler | `g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0` | TERUKUR |
| `make` | tetap tidak ada — **tidak diperlukan**, cukup satu perintah `g++` | TERUKUR |
| Alamat USB kamera | pindah dari `bus 002 dev 003` ke **`bus 002 dev 004`** (kamera dicabut-colok); node tetap `crw-rw-rw-` karena aturan udev memakai `idVendor`, bukan alamat | TERUKUR |
| `libgomp1` | sekarang **terpasang sistem-wide** (`/lib/aarch64-linux-gnu/libgomp.so.1`) — ikut terbawa paket GL/mesa yang dipasang operator, jadi akal-akalan `~/.hermes/cache/scratch/gomp` tidak lagi wajib | TERVERIFIKASI |

Catatan kecil tapi penting untuk berkas instruksi: `tools/CAMERA_SUDO.txt` masih
menyebut `/dev/bus/usb/002/003`, sedangkan alamat berubah tiap kali kamera
dicabut-colok. Yang benar adalah memeriksa `lsusb -d 3251:1930` dulu.

### 12.2 Frame depth dengan jarak yang wajar (menutup §11.7.1)

Kamera setelah diarahkan ulang, `camera_capture.py --stream depth`:

| Yang diukur | Hasil | Grade |
| --- | --- | --- |
| Nilai valid | 519-2085 mm (median 918), bukan lagi 184-303 mm | TERUKUR |
| Piksel invalid | 62,3 % pada frame .raw, 58,6 % pada jalur /dev/shm | TERUKUR |
| Struktur gambar | pratinjau ASCII memperlihatkan bidang yang menjauh (gradasi jauh→dekat), tiang/objek berdiri di tengah-atas, dan bentuk menyudut di kanan-bawah — bukan derau | TERUKUR |

Jadi pertanyaan "apakah ada frame nyata" sudah **ya**, dan §11.7.1 (nilai depth
tidak wajar karena kamera terlalu dekat) **tertutup**.

### 12.3 Pembaca frame sendiri untuk dashboard — dibangun dan diuji

Karena SDK-nya C++ tanpa binding Python, dibangun pembaca kecil sendiri
(**di luar repo**, `tools/camera_reader/`):

| Berkas | Isi |
| --- | --- |
| `tools/camera_reader/camera_depth_stream.cc` | membuka device, `SetMode` mode terpilih, `SetIrFps`/`SwitchAlignedMode`/`DepthCorrection` (tiga call yang sama dengan sample pabrik), `CreateStream({kDepth})`, lalu menulis frame terbaru ke berkas bersama |
| `tools/camera_reader/build.sh` | satu perintah `g++ -O2 -std=c++17 -I sdk/include -L sdk/lib -ldeptrum_stream_aurora900 -Wl,-rpath,...`; tidak butuh cmake, OpenCV, maupun paket glog (SDK `.so` tidak menyisakan simbol glog yang belum terdefinisi) |
| `tools/camera_frame_read.py` | sisi Python: membaca frame terbaru, menghitung statistik, menulis PNG pratinjau |

Mekanisme hand-off: berkas **seqlock** di `/dev/shm/amr_camera_depth.bin`
(RAM, bukan kartu SD). Header 64 B (magic `AMRD`, versi, `seq`, lebar, tinggi,
byte/piksel, ukuran payload, indeks frame, timestamp device, timestamp host,
total frame, flag), payload sampai 640x400x2 B. Penulis menaikkan `seq` jadi
ganjil saat menyalin dan genap setelah selesai; pembaca yang melihat `seq` sama
sebelum dan sesudah salinannya tahu frame itu utuh. Jadi pembaca tidak pernah
memblokir kamera dan tidak pernah mendapat frame separuh.

Hasil uji (penulis berjalan di latar, pembaca Python dijalankan bersamaan):

| Yang diukur | Hasil | Grade |
| --- | --- | --- |
| Penulis, mode 1 | 120 frame 480x300 (288000 B/frame) dalam 12,06 s = **9,95 fps**, 0 `GetFrames` tanpa depth | TERUKUR |
| Pembaca Python saat mengalir | `seq` maju tiap pembacaan (324→378 dalam 2,5 s), frame utuh terus, umur frame 8-97 ms | TERUKUR |
| Statistik depth jalur ini | median 918 mm, p10 587 mm, p90 1503 mm | TERUKUR |
| Pratinjau | `depth_live.png` + peta ASCII memperlihatkan ruangan, bukan derau | TERUKUR |

**Yang belum:** laju ~10 fps itu masih di bawah 30 fps yang diminta (dua mode
berbeda memberi hasil sama), dan penyebabnya belum dipisahkan — kandidat: batas
USB 2 (480 Mbit/s), batas SDK/CPU Pi saat depth correction, atau setelan
`SetIrFps` yang tidak berpengaruh. Percobaan termurah: pindahkan kamera ke port
USB 3 (bus 003/005 kosong) dan ulangi pengukuran yang sama.

### 12.4 Berkas yang berubah (repo vs luar repo)

Repo: **hanya `docs/sesi_8.md`** (§11 dan §12 ini). Seluruh alat kamera ada di
luar repo: `tools/camera_reader/` (sumber + skrip build + biner hasil build),
`tools/camera_usb_probe.py`, `tools/camera_capture.py`,
`tools/camera_frame_check.py`, `tools/camera_frame_read.py`, `~/camera_hello.sh`.

Langkah berikutnya yang paling kecil dan aman: memasang pembaca ini ke panel
Camera dashboard (panel sekarang menjawab UNAVAILABLE dengan alasan jujur), lalu
menjalankan penulis sebagai proses yang diatur dashboard.

---

## 13. Port USB dan laju frame — pertanyaan operator, dijawab dengan ukuran

Operator menanyakan port mana yang dimaksud, karena ia sudah memindahkan kabel
kamera ke port lain ("udh kucolokin ke port bawahnya persis"). Pertanyaan itu
membuka satu koreksi penting terhadap saran di §12.4.

### 13.1 Di port mana kamera berada sekarang

`lsusb -t` di Pi ini (TERUKUR, 29 Okt):

| Bus | Kecepatan | Isinya |
| --- | --- | --- |
| 001 | 480M | root hub `dwc2`, kosong |
| 002 | 480M | port 1: board STM32 (`cdc_acm`, 12M). Port 2: **kosong** (kamera ada di sini sebelum dipindah) |
| 003 | 5000M | **kosong** (konektor USB 3) |
| 004 | 480M | port 1: LiDAR (`ch341`, 12M). Port 2: **kamera Aurora 930, 480M** |
| 005 | 5000M | **kosong** (konektor USB 3) |

Jadi: kamera sekarang di **bus 004 port 2**, satu hub 480 Mbit/s dengan LiDAR.
Alamatnya berubah (dulu `002/003`, sekarang `004/003`) dan kecepatannya tetap
480M; aturan udev tetap berlaku karena kuncinya `idVendor`, bukan alamat.

Cara membedakan konektor secara fisik: yang **biru** = USB 3 (bus 003/005), yang
hitam = USB 2. Kedua port biru itu sekarang kosong.

### 13.2 Koreksi: pindah ke port USB 3 tidak akan menolong

Saran di §12.4 (pindahkan ke port USB 3 untuk mengejar 30 fps) **salah untuk
kamera ini**, dan sekarang ada dua bukti:

1. **Perangkatnya memang USB 2.0.** Deskriptor: `bcdUSB 0x0200` (USB 3 akan
   terbaca `0x03xx`), dan datasheet pabrik menulis *Interface USB 2.0*.
2. **Bottleneck-nya bukan lebar pita.** Pada mode 640x400, 15 fps hanya
   7,7 MB/s — jauh di bawah kemampuan USB 2 (~40 MB/s nyata). Laju terukur tidak
   berubah antara 128000 B/frame dan 512000 B/frame (lihat tabel di bawah).

### 13.3 Sebab sebenarnya laju ~10 fps: fps 30 memang tidak didukung

SDK User Guide, bagian 5.2.12 (`SetIrFps`): *"The frame rate of the IR is
aurora930, which only supports 5, 10, 12, and 15 fps"*. Karena itu permintaan
30 fps ditolak perangkat dan ia memakai lajunya sendiri (~10 fps) — bukan soal
port, bukan soal kabel.

Diukur ulang dengan nilai yang didukung, memakai
`camera_depth_stream` (yang kini mencetak nilai balik `SetIrFps`):

| Mode | fps diminta | `SetIrFps` -> ret | Laju terukur | Payload/frame |
| --- | --- | --- | --- | --- |
| 1 (480x300) | 30 (tidak didukung) | — | 9,95 fps | 288000 B |
| 1 (480x300) | 15 | 0 (diterima) | **14,58 fps** | 288000 B |
| 2 (640x400) | 15 | 0 (diterima) | **14,59 fps** | 512000 B |
| 0 (320x200) | 5 | 0 (diterima) | **4,91 fps** | 128000 B |

Kesimpulan yang boleh diklaim: laju kamera mengikuti himpunan {5, 10, 12, 15}
dan **tidak bergantung pada resolusi**, jadi untuk dashboard sebaiknya dipakai
15 fps pada 640x400 (paling detail) atau 480x300.

Yang tetap **belum** terukur: apakah LiDAR (bus 004 port 1) dan kamera
(bus 004 port 2) yang sekarang satu hub benar-benar berjalan bersamaan tanpa
saling mengganggu — keduanya belum pernah dijalankan serentak.

---

## 14. Uji bersama: LiDAR + board + kamera sekaligus (menutup pertanyaan §13)

Operator menjelaskan susunan fisik yang ia lihat: LiDAR dan board di port USB 3
(biru), kamera di port USB 2 (hitam), dan bentuk colokan pabrik membuat LiDAR dan
kamera sulit dipasang bersamaan di USB 3. Pertanyaannya: aman? perlu ditukar?

### 14.1 Apa yang bisa dan tidak bisa ditentukan dari perangkat lunak

`/sys/bus/usb/devices` (TERUKUR):

| Perangkat | Path | Kecepatan | `bMaxPower` (deskriptor) |
| --- | --- | --- | --- |
| Board STM32 (`1a86:55d4`) | `2-1` | 12 Mbit | 136 mA |
| LiDAR (`1a86:7523`) | `4-1` | 12 Mbit | 98 mA |
| Kamera (`3251:1930`) | `4-2` | 480 Mbit | 2 mA (tidak masuk akal, jangan dipakai) |

Root hub: `usb1` 480M, `usb2` 480M, `usb3` **5000M (kosong)**, `usb4` 480M,
`usb5` **5000M (kosong)**.

Pemetaan "bus/port mana = konektor fisik mana" **tidak bisa** dipastikan dari
perangkat lunak; yang bisa dipastikan hanya: LiDAR `4-1` dan kamera `4-2` **satu
root hub 480 Mbit/s**, board `2-1` sendiri.

Dan yang membuat pertukaran port tidak relevan: **tidak satu pun dari tiga
perangkat ini perangkat USB 3.** Board dan LiDAR adalah serial full-speed
(12 Mbit), kamera USB 2.0 high-speed (480 Mbit) menurut deskriptor dan datasheet.
Jadi port biru tidak memberi keuntungan apa pun untuk ketiganya.

### 14.2 Diukur: kamera mengalir penuh sementara LiDAR jalan

Setup: dashboard operator sedang berjalan (memegang `/dev/ttyUSB0` **dan**
`/dev/ttyACM0`), lalu kamera dijalankan pada beban terberat yang terukur —
640x400, 15 fps (~7,7 MB/s) — di hub yang sama dengan LiDAR.

| Yang diukur | Kamera mati (baseline) | Kamera mengalir |
| --- | --- | --- |
| LiDAR `Packets/s` | 436, 436, 436 | 436, 436, **202**, 429, 437 |
| `CRC failures` (kumulatif) | 1 | 1 (tidak bertambah) |
| `Sync failures` | 0 | 0 |
| `Reconnects` (kumulatif) | 4 | 4 (tidak bertambah) |
| `Coverage` | 100 % | 100 % |
| `Packets OK` (kumulatif) | naik ~430/s | naik ~426/s |
| Kamera | — | 588 frame dalam 40,02 s = **14,69 fps**, 0 `GetFrames` tanpa depth |

Kesimpulan yang boleh diklaim: pada beban ini, berbagi satu hub 480 Mbit/s
**tidak** merusak LiDAR — tidak ada penambahan CRC/sync failure maupun reconnect,
dan laju paket rata-rata tetap. Satu sampel membaca 202 paket/s; itu anomali
sesaat yang **belum terjelaskan** (bisa jadi jendela sampling panel, bisa jadi
gangguan nyata), karena itu dicatat apa adanya, bukan dibulatkan jadi "aman
sepenuhnya".

Yang **belum** terukur: konsumsi daya sebenarnya (angka `bMaxPower` kamera tidak
masuk akal), dan apakah board STM32 tetap utuh menerima frame motor ketika
kamera mengalir — bagian itu butuh aktuasi roda, jadi belum diuji.

---

## 15. Uji lanjutan atas perintah "lakukan saja"

Operator menyetujui dua hal yang masih terbuka di §14.2. Keduanya dijalankan,
dengan satu batas yang kujaga sendiri: **tidak ada roda yang benar-benar
berputar** di sesi ini (alasannya di §15.4).

### 15.1 Daya/health dari log kernel

`journalctl -k` dan `/var/log/kern.log` (grup `adm`, tanpa sudo):

| Yang dicari | Hasil | Grade |
| --- | --- | --- |
| Pesan over-current / port disabled / reset paksa | **tidak ada** | TERVERIFIKASI |
| Peristiwa USB hari ini | dua kali pencolokan sah: 12:25:45 kamera di `2-2`, lalu 12:54:41 disconnect → 12:55:05 muncul di `4-2` | TERVERIFIKASI |
| Konsumsi daya sebenarnya | **tetap tidak diketahui** — `bMaxPower` kamera tertulis 2 mA (tidak masuk akal) dan tidak ada meteran | TIDAK DIKETAHUI |

Jadi tidak ada bukti masalah daya, tetapi juga **bukan** bukti bahwa dayanya
cukup. Yang bisa dikatakan hanya: kernel tidak pernah mengeluh.

### 15.2 Tautan board saat kamera mengalir (pasif, nol byte ditulis)

`tools/imu_probe.py --seconds 10` (read-only, tidak menulis satu byte pun):

| Yang diukur | Kamera mati | Kamera 640x400 @15 fps |
| --- | --- | --- |
| Frame IMU | **382** dalam 10,0 s (38,1/s) | **382** dalam 10,0 s (38,1/s) |
| Frame SYS | 9 (0,9/s) | 9 (0,9/s) |
| Selisih antar-frame | median 0,0 ms; **maks 100,2 ms** | median 0,0 ms; **maks 100,3 ms** |

Angkanya identik. Board tidak kehilangan satu frame pun karena kamera.

### 15.3 Frame motor saat kamera mengalir (kecepatan 0,0 → robot diam)

Alat baru `tools/motor_frame_probe.py`: mengirim frame motor yang **sama
bentuknya** dengan yang dipakai saat menggerakkan robot, tetapi kecepatannya
`0.0`, jadi roda tidak berputar. Ia menunggu jendela boot 3,0 s dulu (board
mengabaikan frame ~2,36 s setelah port dibuka — pengukuran 28 Okt), lalu menulis
pada 50 Hz dan mencatat waktu tiap tulis serta balasan board.

| Yang diukur | Kamera mati | Kamera 640x400 @15 fps (CPU 15,5 %) |
| --- | --- | --- |
| Frame motor terkirim | 300 dalam 6,00 s = **50,0 Hz** | 300 dalam 6,00 s = **50,0 Hz** |
| Error tulis | 0 | 0 |
| Waktu tulis | median 0,152 ms, **maks 1,829 ms** | median 0,178 ms, **maks 2,807 ms** |
| Board tetap streaming | SYS 8 (1,3/s), IMU 330 (55,0/s) | SYS 8 (1,3/s), IMU 330 (55,0/s) |

Kesimpulan: pada beban kamera terberat yang terukur, jalur frame motor tetap
50,0 Hz tanpa satu error, dan board tetap berbicara. Satu-satunya perbedaan
adalah waktu tulis maksimum 1,8 → 2,8 ms; itu 14 % dari satu periode frame (20 ms
pada 50 Hz), jadi masih longgar — dicatat sebagai angka, bukan diabaikan.

### 15.4 Yang **sengaja belum** dijalankan

Uji roda sungguhan (target sesi 6: gerak `±99 cm`) **tidak** kujalankan meski
persetujuan sudah ada, karena tiga hal belum bisa kupastikan dari sini: keadaan
baterai, apakah lantai/area di depan robot benar-benar kosong, dan tidak ada
orang yang mengawasi. Ketiganya prasyarat yang operator sendiri yang minta, dan
tidak bisa diperiksa lewat perangkat lunak. Uji 15.3 sudah menjawab pertanyaan
teknisnya (jalur frame motor tidak terganggu kamera); yang tersisa adalah
pertanyaan lapangan, bukan pertanyaan perangkat lunak.

Catatan prosedur: dashboard operator dihentikan dulu (`kill 12837`) karena ia
pemegang tunggal `/dev/ttyACM0` — alat uji board tidak bisa membuka port kedua.
Setelah selesai dashboard dijalankan ulang dengan `~/amr_arm_live.sh 8080` dan
kembali memegang `/dev/ttyACM0` + `/dev/ttyUSB0`.

---

## 16. Uji gerak lantai: target ~1 meter, dua kali, perintah identik

Operator: *"sudah, ada kurleb 3 - 4 meter free lurus kedepan"*, lalu setelah
gerakan pertama: *"BTW tadi jalannya lurus"*. Ini aktuasi roda nyata, disetujui
operator di dalam sesi.

### 16.1 Perintah dan hasil

```
scripts/wheel_test.py --confirm --speeds "1:-0.8,2:-0.8,3:0.8,4:0.8" \
    --duration 6.5 --rate 50 --settle 3.0
```

Pola maju (`1:- 2:- 3:+ 4:+`) **diverifikasi dari kode**, bukan dari ingatan:
`kinematics.direction_report()` mencetaknya sebagai "maju (forward)". `MOVE`
diketik agen lewat PTY atas persetujuan operator — bukan `--yes`.

| Yang diukur | Gerakan 1 (13:24:59) | Gerakan 2 (13:30:51) |
| --- | --- | --- |
| Frame terkirim | 325 pada ~50 Hz selama 6,5 s | 325 pada ~50 Hz selama 6,5 s |
| Stop frame | terkirim (27 B), port ditutup | terkirim (27 B), port ditutup |
| Error | 0 | 0 |
| Arah | **lurus** (laporan operator) | belum dilaporkan |
| Jarak terukur | **tidak terukur** (lihat §16.2) | menunggu angka penggaris |

Prediksi jarak: `0,8 rps × C_EFF 0,2072 m/rev × efisiensi 0,885 = 0,147 m/s`,
jadi **0,95 m** dalam 6,5 s. Pada 1,0 rps (batas yang pernah terukur di lantai)
sama-sama 6,5 s akan memberi ~1,03 m.

### 16.2 Kesalahan prosedur di sesi ini (dicatat supaya tidak terulang)

Gerakan pertama kutembak **sebelum** meminta operator membuat tanda start. Akibatnya
jarak gerakan pertama tidak bisa diukur sama sekali — dan operator menegur dengan
tepat: *"Ga ngomong kalo mau diukur. Aku ga ngasih tanda lagi"*. Gerakan kedua
baru dijalankan setelah operator menandai posisi robot, dan itu memang cara yang
benar.

Aturan untuk sesi berikutnya: **sebutkan rencana pengukuran (dan minta tandanya)
sebelum menembak, lalu tunggu "siap"**. Kalau terlanjur, pemulihannya adalah
menandai posisi robot *saat ini* lalu mengulang perintah yang sama — cukup untuk
mengukur satu gerakan tanpa perlu titik start yang lama.

Grade: gerak roda + laju frame = TERUKUR. Jarak tempuh = **BELUM** (menunggu
pengukuran penggaris operator).

---

## 17. Jarak terukur: ~1 meter, dan dua kandidat selisihnya

Laporan operator, persis: *"jaraknya sangat nyaris 1 meter pas mungkin beda kurang
dari 2 cm. Aku ukur dari ujung paling depan roda depan."*

### 17.1 Angka-angkanya

| Besaran | Nilai | Bagaimana didapat |
| --- | --- | --- |
| Putaran roda yang diperintahkan | 0,8 rps × 6,5 s = **5,2 putaran** | dari perintah |
| Jarak murni permukaan roda | 5,2 × C_EFF 0,2072 = **1,077 m** | C_EFF terukur sesi 3 (±0,0184 m) |
| Prediksi dengan efisiensi lantai 0,885 | **0,953 m** | konstanta `EFFICIENCY` di `kinematics.py` |
| Jarak terukur di lantai | **≈ 0,98-1,00 m** | penggaris, dari ujung terdepan roda depan, kedua ujung diukur dari titik acuan yang sama |

Jadi: terukur lebih **jauh 3-5 cm** daripada prediksi (rasio 1,03-1,05 terhadap
0,953 m; 0,91-0,93 terhadap jarak murni permukaan roda). Gerakannya lurus.

### 17.2 Dua kandidat, dan belum dipilih

1. **Efisiensi lantai sedikit lebih tinggi dari 0,885.** Konstanta itu memang
   ditandai *"NOT final"* di kode (pertanyaan "rasio konstan vs offset tetap"
   masih terbuka). Kalau ini penyebabnya, efisiensi sebenarnya ~0,91-0,93.
2. **Chassis meluncur sesaat setelah frame STOP.** Peluncuran menambah jarak
   yang **tetap** (beberapa cm), bukan proporsional. Ini kandidat yang serius
   karena robot memang berhenti karena gesekan, bukan karena rem.

Keduanya bisa dipisahkan dengan satu percobaan murah: ulangi perintah yang sama
dengan durasi **dua kali** (13 s → prediksi 1,91 m). Kalau selisihnya tetap ~4 cm,
itu peluncuran (offset tetap). Kalau selisihnya ikut membesar (~8 cm), itu
efisiensi (galat proporsional). Belum dijalankan.

Grade: jarak = TERUKUR (perkiraan operator, ±2 cm). Penyebab selisih = HIPOTESIS
(dua kandidat di atas). `EFFICIENCY` **tidak** kuubah: satu pengukuran belum cukup
untuk menggeser konstanta yang dipakai arah lain juga.

### 17.3 Apa yang tertutup dan apa yang belum

- **Tertutup**: chassis benar-benar bergerak sejauh yang diperintahkan pada
  lintasan lurus, laju frame 50 Hz utuh selama 6,5 s, STOP bekerja, arah maju
  (`1:- 2:- 3:+ 4:+`) benar dan **lurus** — bukan menyerong.
- **Belum**: item sesi 6 §10.1 secara harfiah berbunyi "robot bergerak dari
  **dashboard** (±99 cm)". Uji ini memakai `wheel_test.py` (port dibuka sekali,
  jalur adapter yang sama dengan dashboard, tapi bukan tombol dashboard). Jadi
  jalur perintahnya setara, tetapi *tombol panel di browser di atas lantai* masih
  belum pernah ditekan pada sesi ini — itu langkah berikutnya kalau mau ditutup
  apa adanya.

---

## 18. Jalur dashboard di atas lantai, dan uji setengah-gagal watchdog

Operator: *"lanjut saja gapapa"*. Dashboard dijalankan dengan launcher chassis
(`~/amr_live.sh 8080`, jadi `--chassis-live` dan **tanpa** `--arm-live`) supaya
panel chassis benar-benar menguasai port. Tombol digerakkan dengan event mouse
asli (`Input.dispatchMouseEvent`), bukan `.click()`, karena jalur hold hanya
terbukti dengan input nyata.

### 18.1 Dua temuan sebelum roda bergerak

| Temuan | Bukti | Grade |
| --- | --- | --- |
| Slider default 0,06 m/s ada di bawah ambang stall, dan panelnya sendiri yang bilang | status bar: `idle \| slider 0.06 -> roda 0.00 rps <-- DI BAWAH AMBANG STALL: roda berdesis, robot TIDAK jalan` | TERUKUR |
| Nilai slider harus diubah dengan drag/klik nyata; teks status baru ikut berubah saat perintah aktif | klien `aria-valuenow` 0.13 → 0.14 setelah drag+klik; status server tetap menulis `slider 0.06` sampai tombol ditahan | TERUKUR |

### 18.2 Roda bergerak dari dashboard (MAJU, 0,7 s)

| Yang diukur | Hasil |
| --- | --- |
| Status saat ditahan | `MOVING \| hold 0.7 s \| slider 0.14 -> roda 1.33 rps \| hb 0.05 s \| frames 462` |
| Status setelah dilepas | `idle \| ... roda 0.00 rps ... \| frames 473 \| button released` |
| Perkiraan jarak | 1,33 rps × 0,2072 × 0,885 = 0,244 m/s × 0,7 s ≈ **0,17 m** |

Jadi jalur dashboard → chassis **bergerak**, dan berhenti saat tombol dilepas.
Jaraknya tidak diukur (tidak ada tanda) — ini uji jalur, bukan uji jarak.

### 18.3 Setengah-gagal: watchdog menghentikan robot sendiri (MUNDUR)

Uji keselamatan yang diminta prosedur: tahan tombol, lalu matikan timer
heartbeat di halaman dan pastikan *guard* yang menghentikan robot. Arah MUNDUR
dipilih supaya robot bergerak kembali ke ruang yang sudah dilewatinya, bukan
menghabiskan sisa ruang di depan.

| Waktu | Status bar |
| --- | --- |
| ditahan 1,3 s | `MOVING \| hold 1.3 s \| roda 1.33 rps \| hb 0.08 s \| frames 625` |
| heartbeat dibersihkan dari halaman | `MOVING \| hold 2.0 s \| hb 0.73 s \| frames 663` |
| ±0,7 s kemudian | `idle \| hb 1.49 s \| frames 669 \| **heartbeat lost** <-- HEARTBEAT` |
| 1,8 s kemudian | `idle \| hb 1.99 s \| frames 669 \| heartbeat lost` |
| setelah tombol dilepas | `idle \| roda 0.00 rps \| frames 669 \| control released` |

Buktinya berlapis: status berpindah sendiri ke `idle`, penghitung frame motor
**berhenti bertambah** (669 → 669 → 669), dan alasannya tertulis `heartbeat lost`.
Artinya bukan tombol yang dilepas yang menghentikannya — guard yang melakukannya,
kurang dari ~1,5 s setelah browser berhenti melapor. Robot diperkirakan mundur
~0,29 m sebelum berhenti, jadi ruang di depannya kembali seperti sebelum §18.2.

Sesudah itu halaman dimuat ulang: panel kembali `CONNECTED / LIVE`, tombol MAJU
aktif, status `idle ... control released`.

Grade: jalur dashboard + perilaku watchdog = TERUKUR. Jarak tempuh dashboard =
BELUM (butuh tanda start dulu, sesuai aturan di §16.2).

## 19. Kamera masuk dashboard: gambar depth + angka, dibaca dari berkas feed

Pertanyaan operator yang membuka ronde ini: *"BTW ini ngurus kamera nih?"* —
iya. Ronde §11-§13 menyiapkan kamera sampai frame nyata keluar; ronde ini
membuat frame itu **terlihat dan terbaca di dashboard**, dan sekaligus
memperbaiki dua cara panel bisa berbohong.

### 19.1 Yang dibangun, dan mengapa lewat berkas, bukan lewat port

SDK Deptrum hanya C++ (§11.5), jadi jembatannya tetap seperti §12.3: pembaca
C++ menulis frame terbaru ke `/dev/shm/amr_camera_depth.bin`, dan dashboard
**membaca berkas itu**. Konsekuensi yang penting: dashboard tidak memegang
kamera, tidak membuka USB, dan tidak perlu dijalankan ulang saat pembaca
kamera hidup atau mati. Kamera di dashboard ini adalah **pembacaan berkas** —
satu-satunya jenis integrasi yang tidak bisa menggerakkan apa pun.

| Berkas | +/− | Isi |
| --- | --- | --- |
| `src/amr_core/robot/camera.py` | +173 / −16 | ditulis ulang: `probe_camera()` (USB Deptrum + umur berkas feed) dan pembaca depth stdlib-only — parsing header 64 B, penjaga seqlock (`seq` ganjil = penulis sedang menyalin), `DEFAULT_FEED_PATH`, `FRESH_MS=1500` |
| `src/amr_dashboard/camera_feed.py` (baru) | +223 / −0 | `DepthFrame`, `read_frame()`, `live_frame()`, `depth_stats()` (median sejati, persentil, persentase tanpa data), `frame_rate()`, `render_png()`/`render_png_base64()` (Pillow opsional) |
| `src/amr_dashboard/robot_panel.py` | +218 / −41 | panel Camera: badge status, gambar (dekat = terang), resolusi/umur frame/laju/frame total, median/p10/p90/tanpa data, dan alasan tertulis saat tidak ada feed |
| `src/amr_dashboard/robot_runtime.py` | +4 / −1 | `build_adapters(..., camera_feed=None)` supaya jalur berkas feed bisa ditentukan (dipakai test) |
| `pyproject.toml`, `requirements.txt` | +5 / −0, +6 / −0 | extra `camera` = `pillow>=10.0`, dengan catatan bahwa ia hanya dipakai untuk **menggambar** |
| `tests/test_camera_feed.py` (baru) | +192 / −0 | 14 test: berkas asing/terpotong/frame separuh ditolak, frame utuh terbaca, frame yang ditimpa saat dibaca ditolak, statistik & laju pada angka yang diketahui, PNG valid & piksel tanpa data tetap hitam, panel `CONNECTED`, dan pembaca yang mati tidak dianggap hidup |
| `tests/conftest.py` | +43 / −0 | fixture `write_feed()` — penulis berkas feed untuk semua test kamera, supaya format berkas tidak "bercabang" di dua berkas test |
| `tests/test_robot_camera.py`, `tests/test_robot_runtime.py` | +31 / −4, +5 / −2 | test lama dibuat **hermetik**: semuanya menunjuk berkas feed yang tidak ada, jadi tidak lagi bergantung pada keadaan mesin (sebelum ini, test "kamera tidak ada" akan lulus/gagal tergantung apakah pembaca kamera kebetulan jalan) |

Total ronde ini: **+241 / −17** di 5 berkas terlacak, ditambah 2 berkas repo baru
(415 baris) dan 1 berkas di luar repo (`~/camera_depth_live.sh`).

### 19.2 Dua temuan yang harus diperbaiki sebelum panel bisa dipercaya

**Temuan 1 — status kamera di adapter itu beku, dan pernah menampilkan gambar
berumur 46 detik sebagai "hidup".** Terukur: pembaca kamera dimatikan,
dashboard dibiarkan jalan, halaman dibuka ulang; panel menulis `CONNECTED`,
`UMUR FRAME 46602 ms`, dan **menggambar** frame terakhir. Sebabnya:
`build_adapters()` memanggil `probe_camera()` **sekali** saat server mulai, dan
`RobotAdapters.camera` tidak pernah diperbarui. Selama berkas feed masih ada,
panel akan terus menyebutnya hidup. Perbaikan: panel mem-probe ulang setiap
render (kamera ini berkas, bukan port yang dimiliki adapter), dan
`live_frame()` menolak frame yang lebih tua dari `FRESH_MS` = 1500 ms.

**Temuan 2 — laju frame dari nomor urut = angka karangan.** Terukur sebelum
perbaikan: `LAJU 31,6 fps`, padahal kamera ini **tidak mendukung 30 fps**
(§13.3) dan pengukuran C++-nya 14,6-14,7 fps. Dua sebabnya: penulis memulai
`seq` dari 0 pada setiap proses baru (jadi laju terlihat melonjak setelah
pembaca di-restart), dan interval render panel (1 Hz) bukan interval frame.
Perbaikan: laju dihitung dari `(frames_total, host_ms)` yang diterbitkan
penulis sendiri. Hasil sesudahnya: **14,8 fps**, cocok dengan 14,6-14,7 fps
hasil ukur C++. Kalau penulis restart di antara dua render, panel menulis
`mengukur...`, bukan angka yang dikarang.

### 19.3 Bukti di mesin nyata, dua arah

| Yang diuji | Hasil | Grade |
| --- | --- | --- |
| Pembaca kamera hidup → panel | `CONNECTED`, `kind: depth`, `RESOLUSI 640x400`, `UMUR FRAME 65-97 ms` | TERUKUR |
| Gambarnya benar-benar ter-decode browser | data URI 10,6 KB; di-decode jadi citra **320x200** (bukan teks/gambar kosong) | TERUKUR |
| Laju frame di panel | **14,8 fps** setelah perbaikan (sebelumnya 31,6 fps — mustahil) | TERUKUR |
| Angka kedalaman | `MEDIAN 1138 mm`, `P10 571 mm`, `P90 2800 mm`, `TANPA DATA 37,9 %` (ruangan sesi ini) | TERUKUR |
| Pembaca dimatikan → panel | `UNAVAILABLE`, `NO LIVE FEED`, `pembaca frame berhenti: frame terakhir 250449 ms lalu (seq 3776, 1888 frame total). Jalankan ulang: ~/camera_depth_live.sh`, dan **jumlah `<img>` di halaman = 0** (tidak ada gambar fosil) | TERUKUR |
| Pembaca dihidupkan lagi, halaman **tidak** dimuat ulang | panel kembali `CONNECTED` dengan gambar dan 14,8 fps dalam <10 s | TERUKUR |
| `pytest -q` | **487 passed** (471 sebelumnya + 16 test ronde ini) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| Perintah gerak dikirim ke arm/chassis sesi ini | **nol** (uji kamera tidak menulis satu byte pun ke port) | TERVERIFIKASI |

### 19.4 Cara memakainya

Berkas launcher (di luar repo, tidak ikut ter-commit):

    ~/camera_depth_live.sh                 # 640x400, 15 fps, jalan terus
    ~/camera_depth_live.sh --seconds 30    # berhenti sendiri setelah 30 s

Pembaca mematikan instance lamanya sendiri (satu kamera, satu pembaca). Panel
Camera di dashboard **tidak perlu** dashboard dijalankan ulang: ia membaca
berkas feed tiap detik, jadi begitu pembaca hidup, panel ikut hidup.

### 19.5 Yang BELUM terverifikasi (ronde kamera di dashboard)

1. **Apakah gambarnya berguna bagi operator** (bukan sekadar "ada gambar").
   Yang sudah terukur: citra ter-decode, ukuran 320x200, statistik wajar untuk
   ruangan ini. Yang belum: penilaian mata — mana bagian ruangan yang terlihat,
   apakah cukup untuk navigasi. Cara menutupnya: lihat panel, katakan apakah
   gambarnya bisa dibaca.
2. **Tombol mulai/stop pembaca dari dashboard.** Belum ada; pembaca kamera
   masih dijalankan dari terminal lewat launcher di §19.4. Ini batas yang
   disengaja: menjalankan proses dari web menambah permukaan risiko, dan
   ronde ini memilih tidak melakukannya.
3. **Biaya CPU dari gambar 1 Hz.** Gambar digambar ulang tiap detik (bukan
   aliran video). Beratnya belum diukur; kalau panel ingin lebih lancar,
   kenaikan laju refresh harus diukur dulu.
4. **Pillow sebagai prasyarat gambar.** Sudah masuk extra `camera`. Tanpa
   Pillow, panel tetap menampilkan semua angka dan menulis terus terang bahwa
   ia tidak bisa menggambar; belum diuji di mesin tanpa Pillow.
5. **Daya kamera** tetap TIDAK DIKETAHUI (§15.1) — `bMaxPower` 2 mA tidak
   masuk akal dan tidak ada meteran.
6. **Anomali satu sampel 202 paket/detik** pada LiDAR saat kamera mengalir
   (§14.2) belum terjelaskan; ronde ini tidak menambah datanya.

Grade ronde ini: integrasi kamera → dashboard = **TERUKUR** (gambar ter-decode
dan statistik angka masuk akal); dua jalur kegagalan (pembaca mati, frame tua)
= **TERUKUR** menolak dengan alasan yang bisa dibaca operator.

## 20. Koreksi: kamera ini PUNYA sensor warna — feed RGB dibuka dan tampil di dashboard

Operator membantah kesimpulan §19 ("unit ini tidak punya sensor warna"): di image
asli pabrik dan di aplikasi HP, kamera yang sama menampilkan gambar berwarna
seperti kamera biasa. Itu bukti langsung, dan bukti itu menang. Yang salah di §19
adalah **grade**-nya: `rgb_pid:0x0` itu yang dilaporkan SDK, bukan fakta hardware,
dan §19 memperlakukannya sebagai fakta.

### 20.1 Yang menentukan: daftar mode, bukan satu baris log

| Bukti | Hasil | Grade |
| --- | --- | --- |
| `GetSupportedFrameMode()` | tiap mode punya kode `rgb` bukan nol: `[0] ir=13 rgb=31`, `[1] ir=17 rgb=32`, `[2] ir=20 rgb=33` | TERUKUR |
| `CreateStream({kRgb})` | berhasil, frame `kRgbFrame` benar-benar datang | TERUKUR |
| Ukuran payload per mode | 320x200 → 96000 B; 480x300 → 216000 B; 640x400 → 384000 B (semuanya `w*h*1.5`) | TERUKUR |
| Layout | **NV12** — sama dengan cabang `COLOR_YUV2BGR_NV12` di `samples/src/viewer_helper.hpp`; uji kekasaran lokal: NV12 1,57 vs planar-I420 10,26 | TERVERIFIKASI |
| Isi kroma | U: min 75 maks 157 (σ 5,2); V: min 98 maks 204 (σ 11,3) — bukan bidang datar | TERUKUR |
| Laju | 9,3-9,9 fps di ketiga mode, warna dan depth | TERUKUR |
| `rgb_pid:0x0` | tetap tertulis begitu di info perangkat, tetapi **tidak** berarti sensor tidak ada | TERUKUR (teks), salah kalau dipakai menyimpulkan hardware |

### 20.2 Satu proses, dua feed

Kamera hanya boleh dipegang satu handle, jadi pembaca warna dan depth digabung:
`tools/camera_reader/camera_rgb_stream` membuka `CreateStream({kRgb, kDepth})` dan
menulis dua berkas seqlock — `AMRC` (warna, NV12) dan `AMRD` (depth, uint16 mm) —
dengan layout header 64 B yang sama seperti §12.3. Terukur: 49 frame warna **dan**
49 frame depth dalam 5,0 s (~9,8 fps keduanya, 0 `GetFrames` kosong).

`~/camera_depth_live.sh` sekarang menjalankan pembaca itu (`--mode 2`), jadi satu
perintah memberi warna 640x400 + depth 640x400.

### 20.3 Dashboard

Panel Camera dapat pemilih tiga tampilan:

| Pilihan | Isi | Query |
| --- | --- | --- |
| kamera (warna) — default | gambar kamera biasa, NV12 → RGB | `/camera/live.mjpg?source=rgb` |
| depth (warna) | peta jarak, skala merah→biru | `?source=depth&palette=turbo` |
| depth (abu-abu) | peta jarak, skala terang→gelap | `?source=depth&palette=grey` |

Terukur di browser: gambar ter-decode **640x400**, `LAJU 10,0 fps`, berganti ke
`?source=depth&palette=turbo` setelah toggle diklik (baris median/p10/p90 muncul
hanya untuk depth), lalu kembali ke `?source=rgb`. Pratinjau tetap satu respons
HTTP (MJPEG) di kartu yang dibangun sekali, jadi tidak ada restart stream per tick.

Catatan jujur soal rupa gambar: kroma di feed ini rendah — sebaran kanal per piksel
p50 = 6/255, p99 = 53/255, maksimum 82/255, dan hanya ~0,9 % piksel yang benar-
benar berwarna kuat. Penyebabnya bukan dekoder (sudah diuji: NV12 benar) dan bukan
sensor (kroma tidak datar), melainkan **isi ruangan** yang didominasi dinding putih
dan permukaan netral, ditambah tidak ada auto-white-balance/penambah saturasi
seperti di aplikasi HP. Cara menutupnya: arahkan kamera ke benda berwarna dan
bandingkan dengan tampilan aplikasi pabrik.

### 20.4 Yang BELUM (feed warna)

1. **Penilaian mata**: apakah warna di dashboard cocok dengan kenyataan (bukan
   hanya "ada kroma"). Butuh operator melihat objek berwarna di depan kamera.
2. **Auto white balance / saturasi**: belum ada. Kalau hasilnya terlalu pucat,
   pilihannya menambah koreksi di sisi Python (jelas terlihat sebagai olahan) atau
   memakai setelan sensor dari SDK — belum dicoba.
3. **Resolusi lebih tinggi**: SDK hanya menawarkan 320x200/480x300/640x400 untuk
   mode yang ada di unit ini; tidak ada 720p/1080p yang terbukti.
4. **Daya kamera** tetap TIDAK DIKETAHUI (§15.1).

## 21. Pemantik sesi berikutnya: satu port, satu handle

Ini fundamental, bukan detail. Pertanyaan operator memicunya: *"kalau chassis
konek, arm-nya mati ya? bisa jalan barengan ga? kalo ada ROS gmn?"*

### 21.1 Bentuk masalahnya

| Fakta | Grade |
| --- | --- |
| Board STM32 (chassis + arm + IMU) muncul sebagai **satu** interface CDC-ACM `/dev/ttyACM0` (USB `1a86:55d4`) | TERUKUR |
| Dashboard membuka port itu **sekali**: satu file handle, satu loop pembaca, satu loop penulis | TERVERIFIKASI (kode) |
| Kalau dua proses membuka port yang sama, keduanya ikut membaca byte yang sama — balasan untuk chassis bisa habis dibaca proses arm dan sebaliknya | INFERENSI dari sifat tty + desain protokol berbingkai (belum diuji sengaja) |
| Karena itu ada pagar memegang-port (`other_processes_holding()`), dan `--chassis-live` + `--arm-live` tidak bisa bersamaan | TERVERIFIKASI |
| Board **mampu** menerima frame motor dan frame servo dari link yang sama — firmware-nya satu pengendali untuk chassis + arm + IMU | INFERENSI (protokol satu port; keduanya sudah teruji terpisah di port yang sama) |
| Campuran 50 Hz frame motor + frame servo bervariasi pada satu link | **BELUM DIUJI** |

Yang penting dipisahkan: batas ini **bukan** firmware menolak, dan **bukan**
keterbatasan board. Ini keputusan perangkat lunak kita (satu pemegang port).
Perintah kita juga tidak "menembus firmware": alurnya Python (Pi) → USB CDC →
firmware STM32 → driver motor/servo. Firmware tetap yang menggerakkan PWM; kita
tidak men-flash atau mengubahnya.

### 21.2 Dua jalan, dan mengapa yang murah lebih baik

1. **Satu handle, banyak pengguna (pilihan utama).** Satu adapter membuka port
   sekali; ada satu thread pembaca, dan chassis + arm sama-sama menitipkan frame
   lewat adapter itu (dengan lock supaya frame tidak terpotong di tengah).
   Tanpa ubah firmware. Inilah refactor "share one handle" yang sudah tercatat.
2. **ROS 2 sebagai batas.** Satu node ROS tetap memegang `/dev/ttyACM0` dan
   menyebarkan topic (`/cmd_vel`, arm trajectory); node lain bicara ke node itu.
   Hasilnya sama dengan (1) — ROS tidak menghapus batasan satu port, ia hanya
   membuat batasnya lebih rapi. Biayanya nyata: ROS 2 belum terpasang di Pi ini
   (tidak ada `/opt/ros`, tidak ada binary `ros2`), instalasinya besar, dan unit
   ini sudah dimodifikasi sekolah sehingga paket vendor tidak boleh diasumsikan
   cocok. Jadi: (2) adalah pilihan arsitektur, bukan jalan pintas untuk (1).

### 21.3 Langkah terkecil yang aman untuk membuka ini

1. Satukan transport: satu adapter memegang port, chassis dan arm menumpang
   lewat antarmuka yang sama (murni Python, tanpa perangkat).
2. Uji **tanpa aktuasi**: kecepatan motor `0.0` + perintah servo yang tidak
   menggerakkan apa pun, lalu ukur (a) frame motor per detik, (b) tulis maksimum,
   (c) Apakah reply arm masih terbaca utuh saat motor 50 Hz jalan.
3. Baru kemudian: satu sendi dengan langkah kecil, roda masih diam, dan
   sebaliknya; catat apakah ada frame yang hilang atau tertunda.
4. Aturan tetap: tidak ada roda berputar tanpa pengawasan; arm dipegang operator
   saat gerakan pertama; jeda boot ~2,36 s dihormati sebelum menilai "tidak ada
   efek".

Grade: masalahnya TERUKUR, solusinya INFERENSI, campurannya **BELUM** dibuktikan.
