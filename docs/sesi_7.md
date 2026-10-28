# Sesi 7 — Plot LiDAR yang ter-mirror: penyebabnya terukur, plotnya kini menghadap atas

**Status: SELESAI — pertanyaan terbuka sesi 6 §12.11 ("objek yang seharusnya
tidak ada") terjawab dengan pengukuran: frame sudut LiDAR di robot ini berputar
**searah jarum jam**, sedangkan panel menggambar sudut mentah itu apa adanya,
sehingga seluruh plot ter-mirror. Setelah itu operator meminta dua hal lagi
(ronde 2): DEPAN menghadap **atas**, dan penanda arah hadap jangan berbentuk
segitiga. Keduanya dikerjakan, lalu di-commit dan di-push atas perintah
operator. Yang belum: operator belum melihat sendiri plot baru itu di dashboard
hidup. Tidak ada aktuasi sama sekali di sesi ini: tidak ada satu pun frame motor
yang dikirim, `/dev/ttyACM0` tidak pernah dibuka, robot tidak bergerak. LiDAR
hanya dibaca (read-only) di enam jendela pendek.**

**Tanggal:** 2026-10-28 (WIB, UTC+07:00)
**Host:** `stematel-pi5` (Raspberry Pi 5, Ubuntu 24.04.5 LTS ARM64)
**Repo:** `/home/stematelpi5/AMRTestLander/AMR_LKS_Dashboard` (branch `main`, HEAD `823d2fb`)
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
| §3 | temuan utama: uji pemisah botol | tidak |
| §4 | uji / eksperimen | tidak |
| §5 | akar masalah & perbaikan | tidak |
| §6 | daftar file yang berubah | tidak |
| §7 | verifikasi | tidak |
| §8 | yang BELUM terverifikasi | — |
| §9 | langkah berikutnya | — |
| §10 | ronde 2: depan ke atas, penanda baru, commit & push | tidak |

---

## 1. Ringkasan

1. Sesi 6 menutup dengan dua hipotesis yang tidak bisa dipisahkan dari log:
   pantulan multipath, atau konvensi sudut LiDAR yang ter-mirror. Sesi ini
   memisahkannya dengan uji fisik yang paling murah: satu botol yang sama,
   ditaruh di dua sisi robot, satu scan 10 detik per penempatan, lalu diff per
   sektor 15°.
2. Hasilnya menentukan (**TERUKUR**): botol di kiri-depan robot (~1,17 m)
   mendarat di sektor **315-330°**; botol yang sama di kanan-depan (~1,07 m)
   mendarat di **30-60°**; semua sektor lain tidak bergerak lebih dari 13 mm.
   Karena 0° adalah depan (dua pengukuran bebas di sesi 6), berarti sudut
   LiDAR membesar **ke kanan**, yaitu searah jarum jam dilihat dari atas —
   kebalikan dari asumsi `render_scan_svg` ("0 deg points right and increases
   counter-clockwise, matching the LiDAR's own convention").
3. Akibatnya plot bukan sekadar salah label: seluruh gambar adalah **cermin**
   ruangan terhadap sumbu depan-belakang. Itu persis kata operator, "bisa
   dibilang mirror tapi aneh". Perbaikannya satu titik konversi,
   `_screen_angle_deg()`: `90 - angle_deg` untuk frame searah jarum jam
   (`LIDAR_ANGLE_CLOCKWISE`). Konversi itu dipakai titik scan **dan** penanda
   DEPAN, sehingga keduanya tidak bisa lepas sinkron. Hasilnya tampak atas yang
   benar: depan di atas, kiri robot di kiri, kanan robot di kanan (ronde 2,
   §10).
4. Hipotesis multipath **tidak terbukti hari ini**: di seluruh scan sesi ini
   sektor jauh sangat stabil (mis. 4636 → 4630 mm, dan 4166 → 4160 mm antara
   botol terpasang dan diangkat), tidak ada titik yang muncul-hilang.
5. Yang sengaja tidak disentuh: dashboard operator tidak dijalankan dengan opsi
   LIVE, tidak ada perintah ke `/dev/ttyACM0`, tidak ada commit. Item sesi 6
   §10.1-§10.4 (gerak di lantai, motor 3, TUGAS 1C ke atas) tetap terbuka.

## 2. Baseline

| Item | Nilai | Grade |
| --- | --- | --- |
| HEAD repo | `823d2fb docs: log the open finding -- an object in the scan that should not be there` | TERVERIFIKASI |
| Sinkron dengan remote | `main` = `origin/main`, tanpa perbedaan | TERVERIFIKASI |
| Tree sebelum kerja | bersih (`git status --short` kosong) | TERVERIFIKASI |
| Stash | `stash@{0}: On main: lidar-wip-phase1` | TERVERIFIKASI |
| Test baseline | **421 passed** (13,13 s) — dijalankan ulang sesi ini, cocok dengan angka penutup sesi 6 | TERVERIFIKASI |
| Lint baseline | `ruff check .` bersih | TERVERIFIKASI |
| Dashboard operator | tidak ada proses dashboard yang berjalan; `/dev/ttyUSB0` bebas | TERVERIFIKASI |

## 3. Temuan utama

### 3.1 Gejala

Kata operator di sesi 6, dipakai apa adanya:

> "Kaya ada objek yang seharusnya ga disitu. bisa dibilang mirror tapi aneh"

dan ditegaskan bahwa IMU-nya benar sementara LiDAR-nya yang janggal.

### 3.2 Bukti

Semua scan memakai pembaca produksi (`LidarReader`, kode yang sama dengan
dashboard), 10 detik, read-only, tidak ada byte yang ditulis ke port. Satu botol
dipindah oleh operator; robot tidak digeser, tidak diputar, tidak diaktukan.

| Scan | Penempatan botol | Status | Paket | CRC gagal | Sync gagal | Coverage | Revolusi |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | kiri-depan robot, ~1,17 m (operator: "hampir 1 meter") | RUNNING | 4150 (434/s) | 0 | 0 | 100 % | 100 |
| B | diangkat | RUNNING | 4150 (437/s) | 0 | 0 | 100 % | 100 |
| C | kanan-depan robot, ~1,07 m | RUNNING | 4150 (436/s) | 0 | 0 | 100 % | 99 |

Diff per sektor 15° (`tools/lidar_scan_diff.py`, ambang 60 mm dan 10 %):

| Perbandingan | Sektor yang bergerak | A → B | Tafsir |
| --- | --- | --- | --- |
| A → B (botol kiri diangkat) | **315-330°** | 1174 → 2012 mm (+838) | botol kiri = 315-330°, jarak 1174 mm |
| B → C (botol kanan dipasang) | **30-45°, 45-60°** | 1367 → 1068 mm (−299), 1518 → 1066 mm (−452) | botol kanan = 30-60°, jarak 1066-1068 mm |
| A → C (kontrol silang, botol pindah sisi) | 30-45, 45-60, 315-330 | — | kedua sisi berlawanan, persis seperti cermin |

Semua sektor lain berubah ≤ 13 mm antar scan (0-12 %), yaitu derau, bukan
peristiwa: contohnya 285-300° 4636 → 4630 → 4632 mm dan 300-315° 4166 → 4160 →
4175 mm. Busur badan sendiri tetap 20-29 mm di 105-270°.

Arah depan hari ini: dinding depan rata pada 345-45°, titik terdekat
**1331 mm @ 17°**. Sesi 6 §12.10 mengukur 1,0° ketika robot berdiri tepat
menghadap dinding; hari ini robot berdiri agak miring (digit tangan), jadi arah
depan ada di rentang 0-17° — pergeseran ini **tidak** mengubah kesimpulan
cermin, karena kedua penempatan botol berbeda 90° satu sama lain dan tetap
jatuh di sisi yang berlawanan.

Catatan metode: catatan pembaca yang muncul ("1 reader note") adalah
`connected to /dev/ttyUSB0 @ 230400 baud` — bukan peringatan. Tidak ada
dashboard yang berjalan, jadi stream tidak dibagi dua pembaca seperti sesi 6
§12.11.

### 3.3 Kesimpulan

Yang boleh diklaim:

1. **TERUKUR** — frame sudut mentah LiDAR di robot ini membesar searah jarum jam
   dilihat dari atas: kiri robot = 315-330°, kanan robot = 30-60°, dengan 0°
   sebagai depan.
2. **TERUKUR** — `render_scan_svg` menggambar sudut mentah langsung
   (`x = c + r·cos θ`, `y = c − r·sin θ`), yang pada frame searah jarum jam
   menghasilkan **gambar cermin** dari ruangan.
3. **INFERENSI** — bahwa cermin inilah yang dilihat operator sebagai "objek yang
   seharusnya tidak ada": mekanismenya terbukti ada, tetapi mata operator belum
   pernah membandingkannya setelah perbaikan. Ini satu-satunya klaim di sesi ini
   yang belum boleh naik ke TERUKUR.
4. **HIPOTESIS yang melemah** — multipath: di sesi ini sektor jauh tidak
   menunjukkan perilaku muncul-hilang sama sekali, jadi tidak ada bukti baru
   untuknya. Kalau setelah perbaikan masih ada objek janggal, hipotesis ini
   kembali jadi kandidat utama.

Yang **tidak** boleh diklaim: bahwa plot sudah pernah dilihat benar oleh
operator, dan bahwa masalah LiDAR selesai seluruhnya.

## 4. Uji / eksperimen

| Trial | Parameter | Hasil | Gerak | Catatan |
| --- | --- | --- | --- | --- |
| Scan A | botol kiri-depan ~1,17 m, 10 s | 315-330° = 1174 mm, sektor lain stabil | **tidak ada** | jalur uji pemisah sesi 6 §12.11 |
| Scan B | botol diangkat, 10 s | 315-330° = 2012 mm (+838) | **tidak ada** | menutup identifikasi: itulah botolnya |
| Scan C | botol kanan-depan ~1,07 m, 10 s | 30-45° = 1068 mm, 45-60° = 1066 mm | **tidak ada** | uji kontrol sisi, memisahkan cermin dari salah paham kiri/kanan |
| Uji RED | `LIDAR_ANGLE_CLOCKWISE=False` (perilaku lama) di skrip probe | botol 315° tergambar **di bawah** pusat, 45° di atas → assersi test baru GAGAL | **tidak ada** | membuktikan test baru memang sensitif terhadap perbaikan |
| `pytest` penuh | 423 test | 423 passed (13,13 s) | **tidak ada** | 421 sebelum, +2 test baru |
| `ruff` | seluruh repo | bersih | **tidak ada** | — |
| Preview HTML | satu scan 10 s, dirender dua cara | `tools/scans/plot_before_after.html` (46 508 B) | **tidak ada** | bukti visual sebelum/sesudah untuk operator |

Tidak ada trial yang gagal di sesi ini. Tidak ada aktuasi, jadi tidak ada uji
lantai.

## 5. Akar masalah & perbaikan

Gejala: plot LiDAR menampilkan objek di sisi yang salah, sehingga tampak seperti
objek yang tidak ada di tempatnya.

Sebab: konvensi sudut. Panel mengasumsikan sudut membesar berlawanan jarum jam
(komentar dan docstring `render_scan_svg` menyebutnya "matching the LiDAR's own
convention"), sedangkan pengukuran sesi ini menunjukkan sebaliknya. Pada frame
searah jarum jam, menggambar sudut mentah dengan rumus matematika biasa
menghasilkan pencerminan (pencerminan kiralitas, bukan rotasi): panah DEPAN
tetap menunjuk ke kanan, tetapi sisi kiri robot tergambar di bawah, bukan di
atas.

Bukti: §3.2 (tiga scan, dua penempatan botol, satu kontrol silang).

Perbaikan:

| Perubahan | Isi |
| --- | --- |
| `LIDAR_ANGLE_CLOCKWISE = True` | konstanta terukur + komentar berisi prosedur dan angka pengukurannya |
| `_screen_angle_deg()` | satu titik konversi frame LiDAR → frame gambar: `90 - angle_deg` (cermin + rotasi, depan ke atas), dipakai gambar scan **dan** penanda DEPAN supaya keduanya tidak bisa lepas sinkron |
| docstring `render_scan_svg` + caption panel | menyebut penjelasan barunya: gambar = tampak atas, tidak ter-mirror; panah DEPAN ke kanan → kiri robot tampil di atas plot |
| `LIDAR_FRONT_OFFSET_DEG` | **tidak diubah** (tetap 1,0°): nilainya benar sebagai fakta pemasangan di frame LiDAR; yang salah adalah cara menggambarnya |

Verifikasi tanpa aktuasi: uji RED + 423 test + preview HTML dua-versi dari satu
scan yang sama.

## 6. Daftar file yang berubah

| File | +/− | Isi perubahan (nama fungsi/konstanta) | Mengapa |
| --- | --- | --- | --- |
| `src/amr_dashboard/lidar_panel.py` | +82 / −28 | `LIDAR_ANGLE_CLOCKWISE` (baru), `_screen_angle_deg()` (baru, `90 - angle`), `render_scan_svg()` (memakai konversi itu; docstring), `_robot_front_marker()` (ditulis ulang: `<rect>` chassis + `<polyline>` chevron + label DEPAN, menggantikan `<polygon>` segitiga), dua caption operator | (ronde 1) plot ter-mirror karena frame searah jarum jam digambar apa adanya; (ronde 2) permintaan operator: depan ke atas, penandanya jangan segitiga |
| `tests/test_lidar_dashboard.py` | +59 / −0 | `_point_at()`, `_data_dots()` (baru), `test_the_plot_puts_the_front_up_and_the_robots_left_on_the_left()`, `test_the_front_marker_points_up_and_is_not_a_triangle()` | mengunci kesimpulan §3.2 dan permintaan ronde 2 di dalam test |
| `tests/test_imu_heading.py` | +19 / −12 | `test_the_plot_draws_the_front_marker_at_the_measured_offset()` menyusul penanda baru; helper `_marker_rotation()` + `_marker_label()` menggantikan `_marker_tip()` yang membaca `<polygon>` | test lama membaca segitiga yang sudah tidak ada |
| `docs/sesi_7.md` | +430 / −0 | dokumen ini | aturan log per sesi |

Total: **+590 / −40** di 4 file (3 di antaranya kode).

File bantu di luar repo (tidak di-commit, sengaja):

| Path | Isi |
| --- | --- |
| `~/AMRTestLander/tools/lidar_scan_probe.py` | sudah ada sejak sesi 6; dipakai apa adanya untuk tiga scan |
| `~/AMRTestLander/tools/lidar_scan_diff.py` | **baru** (2 747 B): diff dua tabel sektor, ambang mm dan % — yang mengubah tiga scan jadi satu kalimat |
| `~/AMRTestLander/tools/lidar_plot_preview.py` | **baru** (4 557 B): satu scan dirender dua cara (lama vs sekarang) jadi satu halaman HTML |
| `~/AMRTestLander/tools/scans/scan_A_botol.txt`, `scan_B_tanpa_botol.txt`, `scan_C_botol_kanan.txt` | keluaran mentah ketiga scan |
| `~/AMRTestLander/tools/scans/plot_before_after.html` | 46 508 B, bukti visual sebelum/sesudah |
| `~/.hermes/cache/scratch/mirror_red_check.py` | skrip uji RED (menjalankan render dengan `LIDAR_ANGLE_CLOCKWISE=False`) |

## 7. Verifikasi

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **423 passed** (13,13 s) — 421 + 2 test baru | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| Uji RED pada perilaku lama | assersi test baru gagal (315° di bawah pusat, 45° di atas) | TERVERIFIKASI |
| Test lama yang menyentuh penanda DEPAN | tetap lulus tanpa diubah selain konstantanya tidak perlu diubah | TERVERIFIKASI |
| LiDAR setelah sesi | port bebas, semua proses pembaca sudah berhenti | TERVERIFIKASI |
| `/dev/ttyACM0` | tidak pernah dibuka sesi ini | TERVERIFIKASI |
| Stash `lidar-wip-phase1` | masih terdaftar setelah seluruh pekerjaan | TERVERIFIKASI |
| Peta ASCII dari data nyata (scan C) | memakai `_screen_angle_deg()` panel: dinding depan di baris atas, botol kanan-depan di kanan-atas, ruang 4,1-4,6 m (raw 285-315°) di kiri-atas | TERUKUR |
| `pytest` ronde 2 | 423 passed (12,6-12,9 s); tidak ada test yang dihapus, dua test lama disesuaikan | TERVERIFIKASI |
| `ruff check .` ronde 2 | bersih | TERVERIFIKASI |

## 8. Yang BELUM terverifikasi

1. **Plot yang sudah diperbaiki dilihat operator dengan objek yang diketahui.**
   Semua bukti sesi ini dari angka dan SVG; mata operator belum menilai. Cara
   menutupnya: jalankan dashboard, taruh botol di kiri-depan, dan pastikan titik
   itu muncul di **atas** panah DEPAN (sebelum ini: di bawah). Perkiraan 2 menit,
   tanpa aktuasi selama LIVE tidak diaktifkan.
2. **Orientasi "depan ke atas" baru sebatas dikerjakan, belum dinilai operator.**
   Ronde 1 menggambar depan ke kanan; operator meminta depan ke atas, dan itu
   sudah diimplementasikan (§10) serta dikunci test. Yang belum: penilaian mata
   operator pada plot baru, dan apakah penanda robot yang baru terasa pas
   ukurannya pada rentang 4 m.
3. **Multipath di sektor jauh** — belum dipisah, dan sesi ini tidak menemukan
   bukti baru untuknya (baru negatif). Cara menutupnya: setelah perbaikan
   dipakai, perhatikan sektor 10-70° lagi; kalau masih ada objek muncul-hilang
   di luar geometri ruangan, jalankan `lidar_phantom_probe.py` dengan algoritma
   kehadiran yang sudah diperbaiki.
4. **Item sesi 6 yang tetap terbuka**: §10.1 robot benar-benar bergerak dari
   dashboard (±99 cm), §10.2 jeda boot 2,5 s dirasakan operator, §10.4 motor 3 &
   4 di lantai / TUGAS 1C ke atas.
5. **`ScanPoint.xy()`** di `src/amr_core/lidar/scan.py` masih memakai konvensi
   berlawanan jarum jam. Terverifikasi tidak dipakai siapa pun (`grep` nol
   pemakai), jadi tidak mengubah perilaku — tetapi ia adalah tempat kedua yang
   menyimpan asumsi yang sama.

## 9. Langkah berikutnya

1. Operator melihat `tools/scans/plot_before_after.html` (salin ke mesin yang
   ada browsernya): kiri = gambar lama yang ter-mirror, kanan = gambar sekarang.
2. Putuskan commit untuk sesi 7 (dua berkas kode + dokumen ini). Sesi 5 & 6
   sudah ter-commit dan tersinkron dengan `origin/main`.
3. Kalau mau, konfirmasi visual singkat di dashboard dengan botol (perkiraan
   2 menit, tanpa aktuasi) sebelum perbaikan ini dianggap selesai.
4. Baru setelah itu kembali ke kebutuhan lapangan: cas baterai, uji gerak
   ±99 cm (sesi 6 §10.1).
5. Putuskan commit untuk pekerjaan sesi ini **sudah dijawab operator**: commit
   dan push dijalankan di akhir sesi (ronde 2, §10).


---

## 10. Ronde 2 — "DEPAN menghadap atas", penanda yang tidak segitiga, lalu commit

Permintaan operator, persis:

> "Aku mau depan robot menghadap atas di dashboard. AKu juga mau arah hadap robot
> jangan segitiga gitu, jelek. Setelah itu commit dan push"

Dua perubahan tampilan, nol aktuasi.

| Perubahan | Isi | Alasan |
| --- | --- | --- |
| Orientasi plot | `_screen_angle_deg()` dari `-angle` menjadi `90 - angle` | ronde 1 sudah membalik kiralitasnya (tidak ter-mirror) tetapi depan tergambar ke kanan; operator meminta depan ke atas |
| Penanda arah hadap | `<polygon>` segitiga (hull + ujung, satu bidang biru penuh) diganti `<rect>` chassis sudut tumpul 24 x 30 px + `<polyline>` chevron di hidung + label `DEPAN` di tengah atas | kata operator: "arah hadap robot jangan segitiga gitu, jelek"; segitiga di antara titik scan juga terbaca seperti halangan |

Catatan teknis yang perlu dibaca operator:

1. Penanda itu **simbol, bukan skala**. Pada rentang tampil 4 m, chassis 30 cm
   yang digambar sesuai skala hanya akan jadi ~11 px -- tidak terbaca. Bentuknya
   dibuat tetap supaya arah hadap selalu terbaca.
2. Rotasi SVG berputar searah jarum jam di layar, jadi chassis yang digambar
   menghadap ke atas diberi `rotate(90 - screen_angle)`; dengan offset pemasangan
   1,0 deg hasilnya kemiringan 1 deg. Offset terukurnya jadi **terlihat**, bukan
   disembunyikan sebagai angka di caption.
3. `LIDAR_FRONT_OFFSET_DEG` tetap 1,0 deg. Itu fakta pemasangan di frame LiDAR;
   yang berubah hanya cara menggambarnya.

Verifikasi ronde 2 (tanpa aktuasi):

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **423 passed** (12,6-12,9 s) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| Uji orientasi pada 24 sektor data nyata (scan C) | dinding depan di baris atas, botol kanan-depan (1068 mm @ 44 deg) di **kanan-atas**, ruang jauh 4,1-4,6 m (raw 285-315 deg = sisi kiri robot) di **kiri-atas** | TERUKUR |
| Test kunci | `test_the_plot_puts_the_front_up_and_the_robots_left_on_the_left()`, `test_the_front_marker_points_up_and_is_not_a_triangle()` | TERVERIFIKASI |
| Test lama yang ikut disesuaikan | `test_the_plot_draws_the_front_marker_at_the_measured_offset()` (membaca `<polygon>` yang sudah tidak ada) | TERVERIFIKASI |

Peta ASCII di bawah dihitung dari scan C (botol di kanan-depan, 10 s) memakai
`lidar_panel._screen_angle_deg()` -- konversi panel sendiri, bukan hitungan
kedua yang bisa berbeda. `^` = hidung DEPAN, `R` = robot, `#` = kembalian LiDAR,
`.` = badan sendiri (jarak < 60 mm).

```
file: /home/stematelpi5/AMRTestLander/tools/scans/scan_C_botol_kanan.txt   (^ = DEPAN, R = robot, # = kembali LiDAR, . = badan sendiri)
+-------------------------------------------------------------+
|                                                             |++5.0m
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|         #                                                   |     
|                                                             |     
|    #                   #  #                                 |     
|                              # #                            |     
|                                        #                    |     
|                                  ##                         |     
|                              ^               #              |     
|                        #     R                              |++0.0m
|                                                             |     
|                                                #            |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |     
|                                                             |+-5.0m
+-------------------------------------------------------------+
                    -2.5m      0      +2.5m   (x: kiri robot = negatif)
```

Yang terbaca dari peta itu: titik-titik depan ada di **atas**, hidung `^` tepat
di atas `R`, botol (kanan-depan robot) di **kanan-atas**, dan bukaan jauh
(4,1-4,6 m, yang di frame mentah ada di 285-315 deg) di **kiri-atas** -- yaitu
sisi kiri robot. Sebelum perbaikan, seluruh peta ini adalah cerminnya.

Commit & push (ronde 2, atas perintah operator):

| Aksi | Hasil |
| --- | --- |
| Commit kode | `f9d59dd` fix: draw the LiDAR plot front-up and stop mirroring the room |
| Commit dokumen | `docs: log session 7` (commit dokumen ini sendiri) |
| Push | `main` -> `origin/main` |


### 10.1 Adendum 14:31-14:35 — dua pembacaan LiDAR GAGAL: dashboard sudah memegang port

Setelah perbaikan di-commit dan di-push, dua pembacaan susulan **GAGAL** dan
sebabnya terukur, bukan ditebak:

| Waktu | Aksi | Hasil | Grade |
| --- | --- | --- | --- |
| 14:31 | regenerasi `plot_before_after.html` (10 s) | `status=ERROR packets_ok=1316` (normalnya 4150), waktu baca efektif terpotong | **GAGAL** |
| 14:34 | pembacaan verifikasi 6 s | `status=ERROR packets_ok=848 crc=0 sync=0 reconnects=4`, `last_error: SerialException: device reports readiness to read but returned no data (device disconnected or multiple access on port?)` | **GAGAL** |

Sebab: **dua pembaca pada satu port**. `fuser -v /dev/ttyUSB0` menunjukkan
`stematelpi5 13855 F.... python`, yaitu `run_dashboard.py` yang dijalankan
operator pada **14:22:17** (masih hidup, listen di `127.0.0.1:8080`). Ini
persis yang sudah dicatat sesi 6 §12.11: port serial satu pemilik. Catatan
pembaca menyebut siklus `connected ... serial error ... connected` empat kali.

Yang **tidak** terpengaruh: §3.2 (ketiga scan A/B/C) — semuanya diambil sebelum
14:22, ketika belum ada dashboard, dan tiap scan mencatat `crc=0 sync=0
coverage=100%`. Peta ASCII §10 juga dibaca dari scan C yang bersih.

Yang **terpengaruh**: `plot_before_after.html` versi 14:31 (dibaca sebagian
dengan status ERROR; jarak per sektor tetap sah karena CRC bersih dan delta-nya
kecil, tetapi berkas itu **belum boleh dipakai sebagai bukti**). Regenerasinya
menunggu dashboard berhenti.

Aturan untuk sesi berikutnya: **hentikan dashboard dulu, baru jalankan probe**
(`pkill -f run_dashboard.py`), atau jangan jalankan probe sama sekali selama
operator memakai dashboard.

Catatan penting yang ditemukan di sini: kode `lidar_panel.py` terakhir berubah
**14:27:31**, sedangkan proses dashboard hidup sejak **14:22:17** -- jadi
dashboard yang sedang dilihat operator masih memuat gambar versi antara
(cermin sudah dibalik, tetapi depan masih ke kanan dan penandanya masih
segitiga). Perlu **restart dashboard** supaya tampilan ronde 2 muncul.

---

## Lampiran — cara menjalankan

```bash
# uji pemisah: scan, pindahkan objek, scan lagi, lalu diff
~/AMRTestLander/.venv/bin/python ~/AMRTestLander/tools/lidar_scan_probe.py --seconds 10 > /tmp/a.txt
# ... pindahkan objeknya ...
~/AMRTestLander/.venv/bin/python ~/AMRTestLander/tools/lidar_scan_probe.py --seconds 10 > /tmp/b.txt
~/AMRTestLander/.venv/bin/python ~/AMRTestLander/tools/lidar_scan_diff.py /tmp/a.txt /tmp/b.txt

# bukti visual sebelum/sesudah perbaikan cermin (satu scan, dua gambar)
~/AMRTestLander/.venv/bin/python ~/AMRTestLander/tools/lidar_plot_preview.py --seconds 10

# peta ASCII tampak atas dari data scan mentah, memakai konversi panel sendiri
~/AMRTestLander/.venv/bin/python ~/.hermes/cache/scratch/ascii_map.py \
    ~/AMRTestLander/tools/scans/scan_C_botol_kanan.txt

# test & lint
cd ~/AMRTestLander/AMR_LKS_Dashboard
../.venv/bin/python -m pytest -q
../.venv/bin/ruff check .

# dashboard operator (TIDAK dijalankan di sesi ini)
~/amr_live.sh 8080
```
