# Sesi 6 — Dashboard OFFLINE yang hilang, tombol arah yang bisu, dan jalur kembali ONLINE

**Status: SELESAI (dua ronde) — jalur gerak dipulihkan, jalur ONLINE baru terbukti,
dan fault A4/F8 ("heartbeat lost") diperbaiki setelah ronde kedua. Tanpa satu pun
aktuasi hardware:** tidak ada tombol arah yang ditekan di robot, tidak ada frame
motor non-nol yang ditulis ke `/dev/ttyACM0` oleh alat ukur, dan seluruh
pembuktian memakai port perekam in-process atau pembacaan kode. Ronde 2 ada di §12.

**Tanggal:** 2026-10-26 (WIB, UTC+07:00)
**Host:** `stematel-pi5` (Raspberry Pi 5, Ubuntu 24.04.5 LTS ARM64)
**Repo:** `/home/stematelpi5/AMRTestLander/AMR_LKS_Dashboard` (branch `main`, HEAD `b0e0214`)
**Stash yang dipertahankan:** `stash@{0}: On main: lidar-wip-phase1` — utuh, tidak disentuh
**Python:** `~/AMRTestLander/.venv/bin/python` (3.12.3, nicegui 3.18.0, pyserial 3.5)

Grade bukti yang dipakai sama seperti sesi 3–5:

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
| §2 | baseline sesi 6 | tidak |
| §3 | temuan utama: berkas yang hilang & jalur pagi ini | tidak |
| §4 | pemulihan `chassis_panel.py` dari riwayat sesi 5 | tidak |
| §5 | akar masalah pagi ini: LIVE tanpa port | tidak |
| §6 | perbaikan: jalur ONLINE + settle 2,5 s | tidak |
| §7 | uji end-to-end (browser, port nyata, port sibuk, harness) | tidak |
| §8 | daftar file yang berubah | tidak |
| §9 | verifikasi | tidak |
| §10 | yang BELUM terverifikasi | — |
| §11 | langkah berikutnya | — |

---

## 1. Ringkasan

1. **Berkas yang dipulihkan.** `src/amr_dashboard/chassis_panel.py` di working
   tree pagi ini adalah versi HEAD + 9 baris, bukan versi sesi 5 (+196/−63).
   Seluruh perbaikan sesi 5 pada berkas itu — pad 3×3, kartu `w-full`, status
   tetap `h-12`, `_transmitted_rate`, `_rate_note`, `_offline_pad` — **hilang**,
   dan itulah sebab 7 test sesi 5 gagal. Berkasnya direkonstruksi ulang dari
   riwayat sesi Hermes 5 (`20261022_112842_cbc809`) dan hasilnya cocok dengan
   catatan sesi 5 (§4).
2. **Akar masalah "OFFLINE sudah hilang tapi tetap tidak ada respons".**
   Tombol pagi ini memanggil `configure(live=True)`: adapter live dibuat, tetapi
   portnya **tidak pernah dibuka**. Adapter lalu melaporkan
   `submit() -> accepted=True, transmitted=False`, sehingga panel menganggap
   hold-nya berhasil: status bar bisa bilang MOVING sementara 0 frame ada di
   kabel. Gejala "offline hilang, tombol tetap bisu" adalah
   `accepted=True` + `transmitted=False` (§5).
3. **Permintaan operator dijalankan.** Mode OFFLINE sekarang tidak bisa lagi
   memerangkap operator: label merah + pad disabled tetap tampil, dan ada tombol
   **AKTIFKAN LIVE** yang membuka port chassis nyata dari dalam dashboard yang
   sedang jalan — tanpa restart server. Gagal buka tidak pernah sunyi: alasan
   sebenarnya (termasuk PID yang memegang port) muncul di notifikasi dan
   dashboard tetap OFFLINE dengan jujur (§6).

Yang **tidak** disentuh: `kinematics.py`, `serial_chassis.py`,
`tests/test_dashboard_chassis_panel.py` (pekerjaan sesi 5 apa adanya), dan
seluruh angka hasil tuning sesi 5 (gain longitudinal, `LIVE_LIMITS`, cap 1,80 rps).

---

## 2. Baseline sesi 6

| Item | Nilai | Grade |
| --- | --- | --- |
| HEAD repo | `b0e0214 docs: correct the sign-convention status after the floor test` | TERVERIFIKASI |
| Tree sebelum kerja | **kotor**: 6 berkas termodifikasi + `docs/sesi_5.md` belum di-track | TERVERIFIKASI |
| Stash | `stash@{0}: On main: lidar-wip-phase1` | TERVERIFIKASI |
| Test saat sesi mulai | **8 failed, 383 passed** (391) | TERVERIFIKASI |
| `/dev/ttyACM0` | ada, `166,0`, root:dialout | TERVERIFIKASI |
| `/dev/ttyUSB0` | ada, `188,0`, root:dialout | TERVERIFIKASI |
| Dashboard yang jalan | tidak ada; tidak ada proses yang memegang port serial | TERVERIFIKASI |

Berkas-berkas yang termodifikasi saat sesi dimulai, dengan mtime:

| Berkas | mtime | Isi |
| --- | --- | --- |
| `src/amr_core/robot/kinematics.py` | 2026-10-22 17:43 | pekerjaan sesi 5 (+110/−2) |
| `src/amr_core/robot/serial_chassis.py` | 2026-10-22 17:22 | pekerjaan sesi 5 (+2/−2) |
| `src/amr_dashboard/robot_runtime.py` | 2026-10-22 17:45 | pekerjaan sesi 5 (+22/−7) |
| `tests/test_dashboard_chassis_panel.py` | 2026-10-22 17:46 | pekerjaan sesi 5 (+133/−1) |
| `src/amr_dashboard/app.py` | **2026-10-26 08:56** | sesi 5 (+6/−1) + tambahan pagi ini |
| `src/amr_dashboard/chassis_panel.py` | **2026-10-26 09:05** | **bukan** sesi 5: HEAD + 9 baris |

---

## 3. Temuan utama

### 3.1 Gejala

Kata-kata operator: *"saat pagi tadi aku buka dashboard penyakit lama terulang
lagi, dashboard nya offline dan tombol movement nya gamau respon karena
offline"*, lalu setelah dikerjakan dengan model lain: *"offline nya udah ngga,
tapi tetep aja ga ngasih response"*.

### 3.2 Bukti

| Probe | Yang diukur | Hasil | Grade |
| --- | --- | --- | --- |
| `git diff --numstat` awal sesi | `chassis_panel.py` +9/−1 | sesi 5 mencatat +196/−63 untuk berkas yang sama | TERVERIFIKASI |
| `pytest -q` awal sesi | 7 test `chassis_panel` + 1 test `layout_signature` gagal | fungsi sesi 5 (`_transmitted_rate`, `_rate_note`, `_offline_pad`) tidak ada di berkas | TERVERIFIKASI |
| `probe_morning_and_busy.py` §1 | `configure(live=True)` lalu `chassis.submit()` | `adapters.live=True`, `state=DISABLED`, `_port=None`, `accepted=True transmitted=False` | **TERUKUR** |
| `grep DEFAULT_SETTLE_S` | settle adapter | **0,3 s** vs dead window terukur 2,359 s | TERVERIFIKASI |

### 3.3 Kesimpulan

Dua kerusakan terpisah, dan keduanya menghasilkan gejala yang sama ("tombol
diam"):

1. berkas panel sesi 5 hilang dari working tree, sehingga perbaikan tata letak
   dan pelaporan laju ikut hilang;
2. jalur "aktifkan live" pagi ini membuka **mode** live tanpa membuka **port**,
   dan adapter melaporkan `accepted=True` untuk perintah yang tidak dikirim.

Yang **tidak** boleh diklaim: bahwa robot bisa digerakkan dari lantai. Sesi ini
tidak mengaktuasikan apa pun.

---

## 4. Pemulihan `chassis_panel.py` (acuan: pekerjaan sesi 5, bukan pagi ini)

Berkas versi sesi 5 tidak ada di commit mana pun (`git fsck --lost-found` hanya
menemukan satu dangling commit dan satu dangling tree dari rebase 22 Oktober),
tidak ada di stash, dan `.pyc` di `__pycache__` sudah tertimpa berkas pagi ini
(09:05). Sumber pemulihan yang dipakai: **riwayat sesi Hermes 5**
(`20261022_112842_cbc809`, pesan 2299–2557).

| Langkah | Hasil | Grade |
| --- | --- | --- |
| Kumpulkan semua `patch`/`write_file` ke `chassis_panel.py` dari sesi itu | 26 panggilan; 15 unik untuk berkas ini (11 sisanya untuk `test_dashboard_chassis_panel.py` atau duplikat replay) | TERVERIFIKASI |
| Terapkan berurutan pada `b0e0214:src/amr_dashboard/chassis_panel.py` | 15/15 cocok **persis** (`old_string` ditemukan tepat satu kali); nol tebakan | TERUKUR |
| Hitung ulang diff terhadap HEAD | **+197/−64 baris** vs catatan sesi 5 **+196/−63** (selisih 1 baris = newline akhir berkas, bukan isi) | TERUKUR |
| Periksa penanda sesi 5 ada semua | `_PAD`, `_PAD_BUTTON_CLASSES`, `_offline_pad`, `_transmitted_rate`, `_rate_note` (`AMBANG STALL`), `LONGITUDINAL_GAIN`, `yaw_rate_for_wheel_rate` | TERVERIFIKASI |
| `pytest` | 7 test `chassis_panel` hijau kembali tanpa diubah | TERVERIFIKASI |

Versi pagi ini **tidak dibuang**: disalin ke luar repo sebagai
`~/AMRTestLander/backup-20261026-morning/chassis_panel.py.morning`
(md5 `71de71a646db0fd162b4edc5a47479e0`) dan `app.py.morning`
(md5 `3c5aafdfd936b4bd6bac2bbfbe563cc2`).

Catatan metode: isi berkas direkonstruksi, bukan disalin dari salinan; yang
membuat rekonstruksi ini bisa dipercaya adalah test sesi 5 sendiri — ia menuntut
`_transmitted_rate`, `_rate_note` dengan teks `AMBANG STALL`, dan pemetaan yaw
yang benar, dan semuanya lulus begitu berkas dipasang kembali.

---

## 5. Akar masalah pagi ini: LIVE tanpa port, dan kegagalannya tidak bersuara

**Gejala operator:** *"offline nya udah ngga, tapi tetep aja ga ngasih response"*.

**Sebab, diukur** dengan `probe_morning_and_busy.py` §1 (tanpa aktuasi, tanpa
membuka port):

```
configure(live=True, port='/dev/ttyACM0')
  adapters.live          : True
  chassis.state()        : DISABLED
  port benar-benar dibuka: None
  submit() -> accepted=True transmitted=False
             reason  = validated; the chassis port is not connected
```

Rantainya: `configure()` hanya **membangun** adapter, sementara
`SerialChassisAdapter.open()` adalah satu-satunya yang membuka port dan memulai
thread stream. Tanpa `open()`, `submit()` mengembalikan `accepted=True`.
`chassis_panel._install_hold_buttons` hanya menampilkan notifikasi bila
`accepted` False — jadi hold dianggap berhasil, `hold.active` diset, dan status
bar bisa menulis MOVING sementara kabel membawa nol frame.

Ini kelas kesalahan yang sama dengan bug pagi sesi 5 (`max_linear_y` di bawah
slider): **UI melaporkan sesuatu yang tidak terjadi di kabel.** Bedanya, kali ini
penyebabnya bukan clamp melainkan port yang tidak pernah dibuka.

**Perbaikan:** jalur ONLINE mengganti port dan mengembalikan status sebenarnya
(§6). Tombol lama diganti, bukan ditambah, supaya tidak ada dua tombol dengan
arti berbeda.

---

## 6. Perbaikan: jalur kembali ONLINE + jendela boot 2,5 s

### 6.1 Tombol AKTIFKAN LIVE (permintaan operator)

`robot_runtime.activate_live_chassis()` + `chassis_panel._online_controls()`:

| Aspek | Perilaku | Bukti |
| --- | --- | --- |
| Membuka port nyata | `open_serial_port` (DTR/RTS rendah sebelum `open`, cek pemegang port lewat `/proc`) | TERVERIFIKASI |
| Tidak menggerakkan apa pun | tidak ada frame motor ditulis selama idle: `frames_sent = 0` setelah 1,5 s hidup, dan `0` di probe browser | **TERUKUR** |
| Gagal = bersuara | `ok=False`, pesan memuat port, state, dan PID pemegang port; adapter offline tetap terpasang | **TERUKUR** (§7.3) |
| Idempoten | klik kedua menjawab "chassis sudah LIVE …; tidak ada port kedua yang dibuka" | TERUKUR |
| Halaman berubah sendiri | `app.layout_signature` (mode + live/offline) → tick membangun ulang panel; pad disabled → pad aktif | **TERUKUR** (§7.1) |
| Pintu masuk aman | checkbox "Area robot aman dan E-stop fisik terjangkau" wajib; klik tanpa centang hanya memberi peringatan | TERVERIFIKASI |
| Port mengikuti CLI | `run()` memanggil `robot_runtime.set_default_port(chassis_port)` walau offline, jadi `--chassis-port` tidak diabaikan | TERVERIFIKASI |

Mode OFFLINE kini menampilkan: label merah "Tombol arah DINONAKTIFKAN", pad
disabled yang sama persis dengan pad live, tombol AKTIFKAN LIVE, dan baris "Port
yang dipakai: …". Offline tetap terlihat sebagai keadaan, bukan sebagai
dashboard yang rusak — itu pelajaran sesi 5 yang pagi ini terhapus.

### 6.2 Jendela boot 2,359 s kini dipakai jalur live

`serial_chassis.DEFAULT_SETTLE_S = 0,3` — angka yang sama yang membuat
`wheel_test.py` gagal di sesi 5. Aman untuk port yang dibuka saat start-up
(operator baru menekan tombol beberapa menit kemudian), **tidak** aman untuk
port yang dibuka dari UI: hold pertama kehilangan ~2,4 s frames pertama, dan
hold yang hilang tidak bisa dibedakan dari tombol rusak.

Perbaikan: `robot_runtime.BOOT_WINDOW_S = 2.5` (di atas 2,360/2,359/2,359/2,359 s
yang diukur 4× di sesi 5) dan `build_adapters(live=True)` membangun adapter
dengan `settle_s=BOOT_WINDOW_S`. Adapter sesi 5 tidak diubah; nilai defaultnya
hanya tidak dipakai lagi di jalur live.

Konsekuensi yang harus dikatakan apa adanya: perintah pertama setelah ONLINE
baru dikirim ke kabel ~2,5 s setelah port dibuka. Panel dan notifikasi
mengatakannya terus terang ("tahan tombol agak lama pada hold pertama"),
alih-alih menampilkan MOVING sementara papan masih bisu.

---

## 7. Uji / eksperimen (semua tanpa aktuasi)

### 7.1 Browser end-to-end: server OFFLINE, lalu tombol ditekan

Server dijalankan **tanpa** `--chassis-live` di port 8099
(`run_dashboard.py --host 127.0.0.1 --port 8099 --no-lidar`), `http 200`, dan
`/proc/<pid>/fd` tidak memegang `ttyACM0` — persis keadaan yang dikeluhkan
operator. Halaman dibuka dengan Chromium headless, checkbox dicentang, lalu
tombol AKTIFKAN LIVE diklik.

| Objek yang dibaca | Sebelum klik | Sesudah klik |
| --- | --- | --- |
| badge chassis | `DISABLED` | **`CONNECTED`** |
| teks "DINONAKTIFKAN" | ada | **hilang** |
| tombol MAJU / KIRI / STOP / PUTAR L | `disabled` | **aktif** |
| tombol AKTIFKAN LIVE | ada | hilang (diganti pad live) |
| checkbox safety | `aria-checked=true` | — |
| notifikasi | — | `LIVE: /dev/ttyACM0 terbuka (CONNECTED). Board menerima perintah ~2.5 s setelah port dibuka …` |

Grade: **TERUKUR**. Tidak ada tombol arah yang diklik; robot tidak bergerak.

Kestabilan tata letak diukur ulang di halaman live dengan mengganti teks status
menjadi versi panjang (130 karakter) dan mengukur ulang rect: tombol MAJU tetap
`(949, 276, 112×44)`, kartu tetap `1128×324`, teks tidak terpotong
(`scrollHeight == clientHeight`) — identik dengan angka sesi 5 §8. Grade:
**TERUKUR**. Status bar sendiri melaporkan `stream 0.0 Hz … frames 0` setelah
ONLINE, bukti tambahan bahwa membuka port tidak menulis satu frame pun.

### 7.2 Port nyata: jalur ONLINE terhadap board sungguhan

`probe_online_path.py` (buka port, tanpa menulis frame motor):

```
activate          : ok=True state=CONNECTED (0.03 s)
chassis.settle_s  : 2.5
frames while idle : 0 (must be 0)
second activate   : ok=True  msg=chassis sudah LIVE di /dev/ttyACM0; tidak ada port kedua yang dibuka.
after close       : DISABLED
```

Grade: **TERUKUR**. Setelah selesai, tidak ada proses yang memegang
`/dev/ttyACM0` (diperiksa lewat `/proc/*/fd`).

### 7.3 Port yang sedang dipegang proses lain

Proses terpisah (pid 9645) memegang `/dev/ttyACM0`, lalu jalur ONLINE diminta:

```
holders visible to this process: [9645]
ok=False state=UNAVAILABLE
message: GAGAL LIVE: /dev/ttyACM0 -> UNAVAILABLE (OSError: /dev/ttyACM0 is already
         open in another process (pid 9645). Stop that process first: two writers on
         the same port would interleave motor frames.). Dashboard tetap OFFLINE …
dashboard offline? live=False state=DISABLED
```

Grade: **TERUKUR**. Percobaan pertama probe ini **GAGAL sebagai uji** karena
pemegang portnya adalah proses yang sama (pemeriksaan pemegang sengaja melewati
PID sendiri); diulang dengan proses kedua yang nyata. Proses pemegang kemudian
dimatikan dan port diverifikasi bebas.

### 7.4 Jalur hold → kabel (port perekam, tanpa hardware)

`record_wire_harness.py` (adapter + guard sungguhan, port perekam
in-process), hold 1,0 s per arah, slider minimum:

| Arah | Frame | Rate | Peak | Pola (rps) | Verdict |
| --- | --- | --- | --- | --- | --- |
| Maju | 25 | 50,0 Hz | 0,568 | 1:−0,57 2:−0,57 3:+0,57 4:+0,57 | ok |
| Mundur | 41 | 50,1 Hz | 0,568 | 1:+0,57 2:+0,57 3:−0,57 4:−0,57 | ok |
| Kiri | 40 | 50,0 Hz | 0,327 | 1:+0,33 2:−0,33 3:+0,33 4:−0,33 | ok |
| Kanan | 40 | 50,1 Hz | 0,327 | 1:−0,33 2:+0,33 3:−0,33 4:+0,33 | ok |
| Putar L | 40 | 50,1 Hz | 0,327 | 1:+0,33 2:+0,33 3:+0,33 4:+0,33 | ok |
| Putar R | 40 | 50,1 Hz | 0,327 | 1:−0,33 2:−0,33 3:−0,33 4:−0,33 | ok |

Grade: **TERUKUR (in-process)**. Enam arah melewati ambang stall 0,3 rps dengan
pola tanda yang benar. Tidak ada byte yang menyentuh board.

Catatan: jumlah frame Maju (25) lebih kecil dari arah lain (40–41) karena
kegagalan probe pertama sesi ini — proses dijalankan ulang dengan `--seconds 1.0`
setelah stream arah pertama terpotong; polanya sendiri benar dan rate-nya 50,0 Hz.

### 7.5 Ringkas: apa yang TIDAK dijalankan

| Item | Status | Alasan |
| --- | --- | --- |
| Tombol arah ditekan di hardware | **tidak dijalankan** | butuh aktuasi + persetujuan operator |
| Motor 3/4, TUGAS 1C/1D/2/3/4 | **tidak dijalankan** | sama seperti sesi 5 |
| Ukur kecepatan 1,80 rps di lantai | **tidak dijalankan** | sama seperti sesi 5 |

---

## 8. Daftar file yang berubah

`git diff --numstat` per akhir sesi:

| File | +/− | Isi perubahan (nama fungsi/konstanta) | Mengapa |
| --- | --- | --- | --- |
| `src/amr_dashboard/chassis_panel.py` | +303 / −66 | **pemulihan** `_PAD`, `_PAD_BUTTON_CLASSES`, `_offline_pad()`, `_transmitted_rate()`, `_rate_note()`, `COMFORTABLE_RATE_RPS`, `LONGITUDINAL_GAIN`, `_command_for()` dengan yaw sungguhan, kartu `w-full`, status `h-12`; **baru** `_online_controls()`, `_reason_note()`, `RECENT_STALL_S`; status bar melaporkan `hb`, `loop`, dan alasan berhenti yang menjelaskan siapa yang hilang | kembalikan kerja sesi 5 yang hilang; tambahkan jalan keluar OFFLINE; hentikan kebohongan "MOVING" saat guard sudah menarik perintah |
| `src/amr_dashboard/robot_runtime.py` | +240 / −17 | **baru** `BOOT_WINDOW_S=2.5`, `PortFactory`, `default_port()`, `set_default_port()`, `LiveActivation`, `activate_live_chassis()`, `_close_chassis()`, `LOOP_WATCH_INTERVAL_S`, `LOOP_DELAY_ALARM_S`, `LoopDiagnostics`, `loop_diagnostics()`, `reset_loop_diagnostics()`, `record_loop_delay()`, `note_loop_tick()`; `build_adapters()` menerima `port_factory`/`settle_s` | jalan ONLINE tidak boleh sunyi; hold pertama tidak boleh dimakan dead window; guard butuh bukti "loop kami hidup" |
| `src/amr_dashboard/app.py` | +56 / −8 | `_watch_loop()`, `_start_loop_watch()` (timer 50 ms satu proses), `run()` memanggil `set_default_port`, docstring `chassis_live`, `layout_signature()` = (mode, live/offline), panel chassis di awal `_render_structure` | heartbeat yang tidak bisa diproses bukan salah browser; tombol ONLINE harus mengubah halaman |
| `src/amr_core/robot/motion_guard.py` | +100 / −2 | **baru** `DEFAULT_BUSY_ALLOWANCE_CAP_S`, `DEFAULT_LOOP_STALL_S`, `DEFAULT_LOOP_STALL_STOP_S`, `GuardState.busy_s`, `GuardState.last_loop_tick`, `note_busy()`, `note_loop_tick()`, `loop_age()`, `heartbeat_fresh()` tiga kasus | akar fault A4/F8: stall loop sendiri tidak bisa dibedakan dari browser mati |
| `src/amr_dashboard/__main__.py` | +8 / −5 | komentar grup `--chassis-port`, `--chassis-live`, dan teks `--help` | help tidak boleh lagi berbohong bahwa flag itu satu-satunya jalan |
| `tests/test_ux_traceability.py` | +5 / −2 | `test_layout_signature_is_hashable_and_small` mengharapkan `("competition", "offline")`; nama test mode diperjelas | tanda tangan layout sekarang punya dua entri |
| `src/amr_core/robot/kinematics.py` | +110 / −2 | — (pekerjaan sesi 5, **tidak disentuh**) | — |
| `src/amr_core/robot/serial_chassis.py` | +2 / −2 | — (pekerjaan sesi 5, **tidak disentuh**) | — |
| `tests/test_dashboard_chassis_panel.py` | +133 / −1 | — (pekerjaan sesi 5, **tidak disentuh**; jadi acuan kebenaran) | — |
| `docs/sesi_5.md` (baru, belum di-track) | +454 / −0 | dokumen sesi 5 | rekap sesi, permintaan operator |
| `docs/sesi_6.md` (baru) | +586 / −0 | dokumen sesi ini (ronde 1 + ronde 2) | rekap per sesi |
| `tests/test_dashboard_chassis_online.py` (baru) | +188 / −0 | 7 test jalur ONLINE: buka tanpa gerak, tolak port sibuk, idempoten, `BOOT_WINDOW_S ≥ 2,36`, tanda tangan layout berubah, panel OFFLINE tetap sunyi, port ikut CLI | mengunci perilaku ini agar tidak hilang seperti sesi 5 |
| `tests/test_motion_guard_loop_delay.py` (baru) | +264 / −0 | 11 test fault A4/F8: hold selamat dari stall loop sendiri, stall terlalu lama tetap STOP, klien bisu tetap STOP, kelonggaran dibatasi & di-reset tiap heartbeat, plumbing watchdog, teks atribusi panel | mengunci perbaikan ronde 2 |

Total berkas ter-track: **957 insertions, 105 deletions** di 9 file
(`git diff --numstat`), ditambah **empat berkas baru belum di-track**:
`docs/sesi_5.md` (454 baris), `tests/test_dashboard_chassis_online.py` (188),
`tests/test_motion_guard_loop_delay.py` (264), dan `docs/sesi_6.md` (dokumen ini).

Perubahan **belum di-commit** — sama seperti sesi 5, keputusan commit ada pada
operator.

File bantu di luar repo (tidak ikut di-commit):

| Path | Fungsi |
| --- | --- |
| `~/AMRTestLander/backup-20261026-morning/chassis_panel.py.morning`, `app.py.morning` | salinan versi pagi ini, sebelum dipulihkan |
| `~/.hermes/cache/scratch/panel_rebuild/chassis_panel.rebuilt.py` | hasil rekonstruksi sebelum dipasang |
| `~/.hermes/cache/scratch/panel_patches.json` | 26 patch sesi 5 yang dipakai untuk rekonstruksi |
| `~/.hermes/cache/scratch/probe_online_path.py` | jalur ONLINE terhadap port nyata, tanpa frame motor |
| `~/.hermes/cache/scratch/probe_morning_and_busy.py` | reproduksi jalur pagi ini + uji pemegang port (versi pertama) |
| `~/.hermes/cache/scratch/probe_busy_port.py` | uji port sibuk dengan proses kedua yang nyata |
| `~/.hermes/tools/chromedeps/` | 24+ pustaka headless Chromium + `fakeetc/fonts/fonts.conf` (dipasang tanpa root dengan `apt-get download` + `dpkg-deb -x`) |
| `~/.hermes/tools/chromium-1208/chrome-linux/chrome` | wrapper diarahkan ke `~/.hermes/tools/chromedeps` (sebelumnya ke `scratch/`, yang terhapus prune 24 jam) |

---

## 9. Verifikasi

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **398 passed** (baseline sesi ini 391: 383 lulus + 8 gagal; +7 test baru) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| 7 test sesi 5 di `test_dashboard_chassis_panel.py` | hijau kembali **tanpa diubah** | TERVERIFIKASI |
| Rekonstruksi vs catatan sesi 5 | +197/−64 vs +196/−63 (selisih newline) | TERUKUR |
| Tombol ONLINE di halaman OFFLINE | `DISABLED` → `CONNECTED`, pad aktif, notifikasi benar | TERUKUR |
| Membuka port tidak menulis frame | `frames 0` di status bar; `frames while idle: 0` di probe | TERUKUR |
| Port sibuk | ditolak dengan PID pemegang; dashboard tetap OFFLINE | TERUKUR |
| Enam arah di port perekam | 50,0 Hz, peak ≥ 0,327 rps, pola tanda benar | TERUKUR |
| Kestabilan layout | rect tombol identik sebelum/sesudah teks panjang | TERUKUR |
| Port setelah sesi | tidak ada proses memegang `ttyACM0`/`ttyUSB0` | TERVERIFIKASI |
| Stash `lidar-wip-phase1` | utuh | TERVERIFIKASI |
| Aktuasi hardware | **tidak ada sama sekali** | TERVERIFIKASI |

---

## 10. Yang BELUM terverifikasi

1. **Robot benar-benar bergerak dari dashboard.** Yang terbukti hanya bahwa
   frame yang benar sampai ke kabel pada 50 Hz. Yang harus dilakukan operator:
   jalankan `~/amr_live.sh 8080` (atau tanpa flag, lalu tekan AKTIFKAN LIVE),
   tutup satu tombol arah, tahan 3 detik, ukur jaraknya dengan penggaris.
   Perkiraan sesi 5: ±99 cm pada slider penuh (0,330 m/s × 3 s).
2. **Hold pertama setelah ONLINE tanpa menunggu.** Kode menunggu 2,5 s sebelum
   frame pertama (dead window board). Yang belum diukur: apakah operator bisa
   merasakan jeda itu sebagai "tidak respons" kalau ia menekan segera setelah
   port terbuka sambil tetap menahan.
3. **Perilaku setelah ONLINE terhadap board yang mati/daya habis.** Port akan
   terbuka (CDC-ACM), `CONNECTED` akan tampil, tetapi tidak ada byte masuk. Itu
   batas jalur serial, bukan dashboard — sama seperti catatan skill: port hidup
   ≠ robot hidup.
4. **Tiga item sesi 5 yang masih terbuka** (kecepatan 1,80 rps di lantai,
   lurus/melengkung, motor 3 di lantai dengan `--settle 3.0`) — tidak tersentuh.

---

## 11. Langkah berikutnya

1. Cas baterai, lalu uji gerak di lantai memakai acuan §10.1 (±99 cm).
2. Kalau operator ingin jalur ONLINE tanpa checkbox konfirmasi, minta
   menghapusnya — itu satu blok di `_online_controls()`, bukan perubahan
   struktural.
3. Putuskan commit untuk pekerjaan sesi 5 + 6 (keduanya belum di-commit).
4. Lanjutkan TUGAS 1C (motor 3 & 4) dan seterusnya seperti rencana sesi 5 §12.

---

## 12. Ronde 2 — "heartbeat loss" pada KIRI/KANAN/PUTAR, dan pengukuran IMU

Ronde ini dimulai dari laporan operator atas uji aktual: *"Saat kanan kiri dan
Putar R & L terjadi Heartbeat Loss"* dan *"Pembacaan Lidar kurang jelas … mungkin
bisa saja di titik tengah lingkaran itu dikasih liat posisi arah si robot
menghadap mananya (kalo bisa). Manfaatkan IMU nya untuk ini."*

**Tidak ada aktuasi di ronde ini.** Semua uji memakai port perekam in-process
atau pembacaan pasif; dashboard operator (PID 10655, jalan sejak 12:19:56) tidak
disentuh dan tetap memegang `/dev/ttyUSB0` dan `/dev/ttyACM0` selama sesi ini.

### 12.1 Fault ini sudah pernah tercatat

| Sumber | Bunyi catatan |
| --- | --- |
| `docs/rencana_chassis_live.md` §F8 | *"Heartbeat kadang hilang → robot berhenti mendadak \| FIXED sebagian \| Ambang heartbeat 0,3 s terlalu rapat untuk event loop yang sesekali menunda"* |
| `docs/sesi_4.md` §A4 | *"Heartbeat kadang hilang → robot berhenti mendadak \| TERUKUR (terobservasi) … membuat pengukuran jarak tidak bisa diulang → harus hilang dulu"* |

Jadi ini kemunculan ketiga. Mitigasi sebelumnya hanya menaikkan ambang 0,3 → 0,8 s
dan mengurangi beban tick; akarnya tidak pernah diukur.

Hanya satu tempat yang bisa memunculkan kata itu: `MotionGuard.poll()` /
`request_motion()` → `stopped_reason = "heartbeat lost"`. Artinya: selama > 0,8 s
server tidak memproses heartbeat dari browser, **padahal tombol masih ditahan**.

### 12.2 Yang TIDAK terbukti menjadi sebab (hasil negatif, penting)

Harness `~/AMRTestLander/tools/dash_probe.py`: adapter live sungguhan
(`SerialChassisAdapter` + `MotionGuard` + `LIVE_LIMITS`), port perekam memori,
panel LiDAR 360 titik sintetis yang di-refresh 1 Hz seperti di rig, digerakkan
Chromium headless dengan input mouse nyata.

| Uji | Hasil | Grade |
| --- | --- | --- |
| 4 arah @ 4 s, tanpa LiDAR | 603 heartbeat, gap median **100 ms**, p95 106 ms, **max 150 ms**; nol stall loop > 200 ms; nol `heartbeat lost` | TERUKUR |
| KIRI/PUTAR L/MAJU @ 15 s dengan panel LiDAR 360 titik aktif | `hb 0.00–0.05 s` sepanjang hold, `stream 50,0 Hz`, nol kehilangan | TERUKUR |
| CPU proses dashboard operator (sampling 5 s) | ~19 % satu core, 7 thread | TERUKUR |

Kesimpulan: beban tick + panel LiDAR **bukan** penyebabnya di mesin ini. Yang
belum bisa diukur dari sini adalah besar stall di rig saat robot benar-benar
bergerak dan browser operator berada di mesin lain.

### 12.3 Reproduksi terkendali + kegagalan perbaikan pertama

`dash_probe.py --simulate-stall 1.2 --stall-every 4` memblokir event loop 1,2 s
setiap 4 s — persis bentuk fault A4/F8. Hold KIRI 16 s:

| Percobaan | Hasil |
| --- | --- |
| Sebelum perbaikan (atau `--no-busy-allowance`) | hold **mati** sekitar t≈5 s: `heartbeat lost`, frame berhenti di 191 |
| Setelah `note_busy()` saja (percobaan pertama) | **masih mati** — lihat di bawah |

Percobaan pertama gagal karena alasan yang penting untuk dicatat: **thread stream
mengambil keputusan di tengah stall**, dari thread lain, pada 50 Hz. Saat stall
selesai dan watchdog baru mengukur delay-nya, robot sudah berhenti. "Memaafkan
setelah kejadian" selalu terlambat.

### 12.4 Perbaikan: guard tidak boleh menilai klien saat dirinya sendiri macet

Timer pengawas 50 ms di level aplikasi (`app._watch_loop`, satu untuk seluruh
proses) kini menyegarkan `MotionGuard.note_loop_tick()`. `heartbeat_fresh()` jadi
tiga kasus berurutan:

1. loop sendiri tidak tick ≥ `DEFAULT_LOOP_STALL_STOP_S` (**2,0 s**) → **TOLAK**.
   Proses yang tidak bisa jalan selama detik-detik tidak boleh terus mengirim
   frame motor; ini yang menjaga toleransi tetap terbatas.
2. loop sendiri tidak tick > `DEFAULT_LOOP_STALL_S` (**0,3 s**) → **IZINKAN**.
   Kita yang sedang macet, jadi kita tidak bisa menilai klien — inilah kasus yang
   dulu mematikan hold yang masih ditahan.
3. normal → klien harus melapor dalam 0,8 s, ditambah kelonggaran
   `note_busy()` yang dibatasi `DEFAULT_BUSY_ALLOWANCE_CAP_S` (**1,5 s**) dan
   di-reset setiap heartbeat masuk. Kelonggaran ini menutup celah beberapa
   milidetik setelah loop bangun, sebelum heartbeat yang mengantre diproses.

Status bar juga berhenti berbohong: `MOVING` hanya dicetak kalau guard masih
memegang perintah, dan alasan berhenti kini menjelaskan sisi mana yang hilang
(`_reason_note()`), memakai **kebaruan** stall (`RECENT_STALL_S = 3,0 s`) — nilai
maksimum dari beberapa menit lalu tidak boleh dipakai untuk menuduh server.

| Uji (hold 16 s, stall 1,2 s tiap 4 s) | Hasil | Grade |
| --- | --- | --- |
| Setelah perbaikan | **MOVING sepanjang 16 s**, frame 147 → 747, nol `heartbeat lost`, `loop 1189 ms` tampil di status | TERUKUR |
| Kontrol (timer heartbeat browser dimatikan lewat JS) | robot **berhenti** di `hb ≈ 0,9 s`, frame beku di 362, status: `idle … HEARTBEAT HILANG: loop server normal, jadi browser ini berhenti melapor` | TERUKUR |
| Hold normal 6 s (loop sehat) | `MOVING`, `hb 0.02 s`, `loop 113 ms`, tanpa kehilangan | TERUKUR |

Kontrolnya penting: jaring pengaman tidak dilonggarkan menjadi "selalu jalan".
Klien yang benar-benar bisu tetap dihentikan dalam ~0,8 s.

### 12.5 Pengukuran IMU (pasif, nol byte ditulis)

`~/AMRTestLander/tools/imu_probe.py` — buka `/dev/ttyACM0` sekali dengan DTR/RTS
rendah, **tidak menulis apa pun**, baca 10 s, dekode dengan `FrameDecoder`:

| Besaran | Hasil | Grade |
| --- | --- | --- |
| Fungsi yang masuk | `SYS` (0) 9 frame (~0,9/s), `IMU` (7) **390 frame** | TERUKUR |
| Pola waktu | burst pertama pada **0,100 s**, lalu lubang **2.303 ms**, lalu ~50 Hz mantap (rata-rata 39/s termasuk lubang) | TERUKUR |
| `az` | mean **1,0242**, stdev 0,052 → gravitasi ada di +z, satuan tampak **g** | TERUKUR |
| `ax`, `ay` | 0,0186 dan 0,1063 | TERUKUR |
| `gx` | mean 0,1814; **transien startup sampai 5,17** pada frame awal | TERUKUR |
| `gy`, `gz` | mean −0,0972 dan −0,0205; rentang [−0,891, 0,938] dan [−0,250, 0,262] | TERUKUR |
| Sumbu yaw, satuan gyro, dan tandanya | **TIDAK DIKETAHUI** | TIDAK DIKETAHUI |

Payload `SYS` terlihat: `04971b`, `049c1b`, `04961b` (subtype 0x04, uint16).

Konsekuensi yang harus dikatakan apa adanya: **arah hadap dari IMU belum bisa
digambar.** Sumbu mana yang yaw, satuannya (rad/s atau deg/s), dan tandanya belum
terukur, dan modul protokol sendiri mencatat satuan IMU "tidak didokumentasikan".
Yang dibutuhkan: satu pengukuran rotasi tangan (tanpa aktuasi motor) — robot
diam, lalu diputar ±90° ke kiri, jeda, ±90° ke kanan, jeda — sehingga sumbu dan
tanda bisa diidentifikasi dari data, bukan dari dugaan. Hal yang sama berlaku
untuk offset "depan robot" terhadap 0° LiDAR: itu fakta pemasangan, bukan
konstanta yang boleh dikarang.

### 12.6 Berkas ronde 2

| File | +/− | Isi | Mengapa |
| --- | --- | --- | --- |
| `src/amr_core/robot/motion_guard.py` | +100 / −2 | `DEFAULT_LOOP_STALL_S`, `DEFAULT_LOOP_STALL_STOP_S`, `DEFAULT_BUSY_ALLOWANCE_CAP_S`, `GuardState.busy_s`, `GuardState.last_loop_tick`, `note_busy()`, `note_loop_tick()`, `loop_age()`, `heartbeat_fresh()` 3 kasus | akar A4/F8 |
| `src/amr_dashboard/robot_runtime.py` | +74 / −0 | `LOOP_WATCH_INTERVAL_S`, `LOOP_DELAY_ALARM_S`, `LoopDiagnostics`, `loop_diagnostics()`, `reset_loop_diagnostics()`, `record_loop_delay()`, `note_loop_tick()` | pengukuran + jembatan ke guard |
| `src/amr_dashboard/app.py` | +36 / −0 | `_watch_loop()`, `_start_loop_watch()`, `app.on_startup(_start_loop_watch)` | watchdog 50 ms level aplikasi |
| `src/amr_dashboard/chassis_panel.py` | +45 / −1 | `_reason_note()`, `RECENT_STALL_S`, `MOVING` hanya saat guard masih memegang perintah, status memuat `hb` dan `loop` | berhenti menyembunyikan sebab |
| `tests/test_motion_guard_loop_delay.py` (baru) | +264 / −0 | 11 test A4/F8 | mengunci perbaikan |

Alat di luar repo: `~/AMRTestLander/tools/dash_probe.py` (dashboard live dengan
port perekam, LiDAR sintetis, stall buatan, `ZeroOnlyPort` yang membuang setiap
frame motor non-nol) dan `~/AMRTestLander/tools/imu_probe.py` (pembacaan IMU
pasif). Keduanya tidak di-commit.

### 12.7 Verifikasi ronde 2

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **409 passed** (398 sebelum ronde 2; +11 test A4/F8) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| Hold 16 s + stall 1,2 s | MOVING sepanjang hold, nol kehilangan | TERUKUR |
| Kontrol klien bisu | STOP di ~0,9 s dengan atribusi yang benar | TERUKUR |
| Port serial setelah sesi | hanya PID 10655 (dashboard operator) yang memegang | TERVERIFIKASI |
| Dashboard operator | tidak disentuh, tidak di-restart | TERVERIFIKASI |

### 12.8 Yang masih terbuka setelah ronde 2

1. **Besar stall sebenarnya di rig operator.** Panel kini menampilkan `loop N ms`
   dan menyebut sisi mana yang hilang, jadi satu sesi uji berikutnya akan
   menjawabnya. Kalau `loop` di atas 2000 ms muncul, guard memang akan (dan
   seharusnya) menghentikan robot.
2. **Sumbu/satuan/tanda yaw IMU** — perlu pengukuran rotasi tangan (§12.5).
3. **Offset "depan robot" terhadap 0° LiDAR** — perlu pengukuran (kotak di depan
   robot, baca sudut bucket yang menyala).
4. Item §10.1–§10.4 (gerak di lantai, motor 3, TUGAS 1C ke atas) tetap terbuka.

---

### 12.9 Identifikasi sumbu yaw IMU (rotasi tangan, tanpa aktuasi)

`~/AMRTestLander/tools/imu_rotate.py` — baca pasif 75 s, operator memutar badan
robot dengan tangan pada dua fase. Timeline 0,5 s (nilai rata-rata per bin):

| Fase | Waktu | gx | gy | gz | Tafsir |
| --- | --- | --- | --- | --- | --- |
| boot | 2,0–2,5 s | **+1,773** | +0,266 | +0,061 | transien startup gx, sama seperti §12.5 |
| diam | 2,5–28,1 s | ±0,07 | **−0,09** (bias tetap) | ±0,03 | ketiga gyro tenang |
| **rotasi 1** | 28,6–30,2 s | ±6 | ±5 | **+50,1 / +95,9 / +39,7 / +8,3** | hanya gz yang merespons |
| diam | 30,7–37,7 s | ±0,05 | −0,09 | ±0,03 | kembali tenang |
| **rotasi 2** | 38,2–40,2 s | ±20 | ±16 | **−33,9 / −75,5 / −52,4 / −27,4** | arah putar lawan → tanda berlawanan |
| diam | 40,7–75,0 s | ±0,05 | −0,09 | ±0,03 | tenang |

Integral per fase: rotasi 1 **+97,2** satuan·s, rotasi 2 **−96,3** satuan·s;
total 75 s hanya **+1,5** (kedua putaran saling meniadakan, konsisten).

**Kesimpulan (TERUKUR):**

1. **Sumbu yaw = `gz`.** Hanya `gz` yang merespons putaran badan; `gx`/`gy` hanya
   tersentuh saat robot sedikit miring, bukan saat diputar.
2. **Satuan gyro = derajat/detik.** Putaran yang diminta ±90° menghasilkan
   |∫gz| = 96,8 → rasio 1,075 terhadap 90°. Kalau satuannya rad/s, integralnya
   harus 1,5708 (60× lebih kecil); kalau LSB mentah, rasionya akan sembarang.
   Sisa 7,5 % wajar untuk putaran tangan + bin 0,5 s. Puncak 96–128 °/s selama
   putaran ~2 s juga sesuai untuk rata-rata 45 °/s.
3. **Bias diam sangat kecil**: gz mean ±0,03 °/s → drift integrasi ~0,3 °/menit
   pada sampel ini. Tetap perlu tombol reset arah.
4. **Tanda TERUKUR dan ditetapkan operator:** putaran pertama = **ke kiri,
   berlawanan arah jarum jam dilihat dari atas**, dan itu memberi `gz` positif.
   Jadi `+gz` = yaw ke kiri (kiri = berlawanan jarum jam), `−gz` = ke kanan —
   konsisten dengan aturan tangan kanan pada sumbu +z. Arah hadap dapat dihitung
   sebagai `heading_deg = ∫ gz dt` dan bertambah saat robot berputar ke kiri.
5. Laju frame 3631/75 s = **48,4 Hz**, dan lubang boot 2,3 s terlihat lagi
   (frame pertama 2,0–2,5 s).

Yang masih dibutuhkan sebelum arah hadap boleh digambar: (a) konfirmasi arah
putaran pertama terhadap sumbu jam (menetapkan tanda), (b) offset 0° LiDAR vs
arah depan badan robot (fakta pemasangan: taruh kotak di depan, baca bucket).

---

### 12.10 Offset depan LiDAR (terukur) dan arah hadap dari IMU (dipasang)

**Offset depan.** Dinding arena rata di depan robot memberi pola
`d = D/cos(theta - theta0)`. Fit grid 0,1° atas 132 titik (jarak 250-1500 mm, di
luar busur badan sendiri):

| Besaran | Hasil | Grade |
| --- | --- | --- |
| Arah tegak lurus dinding (`theta0`) | **1,0°** di frame LiDAR | TERUKUR |
| Jarak tegak lurus ke dinding (`D`) | **493 mm** (operator menyebut ±40 cm) | TERUKUR |
| Sisa sebaran (std proyeksi) | **5 mm** atas 132 titik → dinding benar-benar rata | TERUKUR |
| Pusat busur badan sendiri (105°-255°) | **180,0°** → LiDAR dipasang dengan 0° = depan | TERUKUR |

Dua pembacaan bebas setuju dalam 1° → `LIDAR_FRONT_OFFSET_DEG = 1,0` (±2°).
Cek silang hukum dinding datar: sektor 15°→504 mm, 30°→563, 45°→696, 60°→982;
hitungan 508/564/686/986 mm. Sapuan bersih: 4150 paket/10 s (436/s), **0 CRC
gagal, 0 sync gagal**, coverage 100%, 99 revolusi.

**Arah hadap dari IMU.** Fakta terukur dari §12.9 dipakai apa adanya: `gz` =
deg/s, kiri positif, dibaca dari handle yang sama dengan stream motor (handle
kedua akan menahan board 2,36 s lagi dan memecah stream).

| Berkas | +/− | Isi |
| --- | --- | --- |
| `src/amr_core/robot/imu.py` (baru) | +131 / −0 | `YawIntegrator`, `DEFAULT_DEADBAND_DPS = 0,05`, `MAX_STEP_S = 0,5` |
| `src/amr_core/robot/serial_chassis.py` | +67 / −1 | `imu_listener` opsional, `_drain_input()` non-blocking, `FrameDecoder` internal, `imu_frames` |
| `src/amr_dashboard/robot_runtime.py` | +26 / −0 | `_yaw`, `yaw_integrator()`, `reset_heading()`, `_feed_heading()`; reset referensi saat adapter live dibangun |
| `src/amr_dashboard/lidar_panel.py` | +166 / −1 | `LIDAR_FRONT_OFFSET_DEG = 1,0`, `SELF_RETURN_MM = 60`, `heading_dial_svg()`, `_robot_front_marker()`, legenda orientasi |
| `src/amr_dashboard/chassis_panel.py` | +58 / −0 | `_heading_row()`, `_heading_text()`, tombol **RESET arah** (di kartu yang tidak di-refresh, supaya bisa diklik) |
| `tests/test_imu_heading.py` (baru) | +262 / −0 | 12 test: skala 90°, tanda, gap boot tidak diintegrasi, deadband, reset, wiring listener, panah DEPAN di sudut terukur, pemisahan titik badan sendiri, dial jujur tanpa data |

Catatan desain yang perlu dibaca operator: panah arah hadap **tidak** digambar di
plot polar, karena plot itu berada di frame LiDAR yang ikut berputar bersama
badan — di sana depan robot selalu di sudut tetap (dan itu memang digambar
sebagai panah "DEPAN"). Arah hadap hanya bermakna terhadap ruangan, jadi ia
dapat dial sendiri dengan acuan "saat LIVE dimulai".

**Verifikasi (tanpa aktuasi).**

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **421 passed** (+12 test IMU/heading; 409 sebelum ini) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| `heading_probe.py` pada board nyata (9 s, idle) | CONNECTED, `settle_s = 2,5`, **frames_sent = 0** saat idle, IMU 331 frame / 40 Hz, integrator 331 sampel, `seconds_integrated` 6,67 s, heading **+0,03°** (drift 0,27°/menit), `skipped = 0`, `last_error` kosong | TERUKUR |
| Setelah `close()` | DISABLED, 1 frame (stop frame) — perilaku lama tidak berubah | TERUKUR |
| Serial port setelah sesi | bebas; hanya dibuka sesaat oleh probe | TERVERIFIKASI |

Yang **belum**: panah arah hadap ini belum pernah dilihat bergerak bersama robot
saat robot benar-benar diputar motor (uji lapangan), dan nilainya masih relatif —
perlu operator menekan RESET arah sebelum setiap run.

---

## Lampiran — cara menjalankan

```bash
# cara biasa (selalu LIVE, flag tidak bisa lupa)
~/amr_live.sh 8080

# atau: jalankan offline lalu tekan AKTIFKAN LIVE di panel (centang checkbox dulu)
cd ~/AMRTestLander/AMR_LKS_Dashboard
../.venv/bin/python run_dashboard.py --host 0.0.0.0 --port 8080 --chassis-port /dev/ttyACM0

# test & lint
../.venv/bin/python -m pytest -q
../.venv/bin/ruff check .

# pembuktian tanpa hardware: enam arah di port perekam
../.venv/bin/python ~/.hermes/skills/robotics/amr-stm32-port-boot-window/scripts/record_wire_harness.py --seconds 1.0
```