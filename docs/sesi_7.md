# Sesi 7 — Plot LiDAR yang ter-mirror: penyebabnya terukur, plotnya kini menghadap atas

**Status: SELESAI — pertanyaan terbuka sesi 6 §12.11 ("objek yang seharusnya
tidak ada") terjawab dengan pengukuran: frame sudut LiDAR di robot ini berputar
**searah jarum jam**, sedangkan panel menggambar sudut mentah itu apa adanya,
sehingga seluruh plot ter-mirror. Setelah itu operator meminta dua hal lagi
(ronde 2): DEPAN menghadap **atas**, dan penanda arah hadap jangan berbentuk
segitiga. Keduanya dikerjakan, lalu di-commit dan di-push atas perintah
operator. Ronde 3 & 4 (permintaan operator: gambarkan robotnya, hapus tulisan DEPAN,
lalu kecilkan supaya skala jaraknya jujur) sudah dikerjakan tetapi **belum
di-commit** — menunggu keputusan operator. Yang belum:
operator belum melihat sendiri plot baru itu di dashboard hidup. Tidak ada aktuasi sama sekali di sesi ini: tidak ada satu pun frame motor
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
| §10 | ronde 2-4: depan ke atas, penanda robot, skala | tidak |
| §11 | arm: protokol pabrik + probe read-only | tidak |

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
| `src/amr_dashboard/lidar_panel.py` | +124 / −31 | `LIDAR_ANGLE_CLOCKWISE` (baru), `_screen_angle_deg()` (baru, `90 - angle`), `render_scan_svg()` (memakai konversi itu; docstring), `_robot_front_marker()` (ditulis ulang dua kali: `<polygon>` segitiga → `<rect>` + chevron + label DEPAN → gambar robot `<g class="robot-marker">` berisi bodi + 4 roda + sensor hidung + hub, tanpa tulisan), dua caption operator | (ronde 1) plot ter-mirror karena frame searah jarum jam digambar apa adanya; (ronde 2) permintaan operator: depan ke atas, penandanya jangan segitiga |
| `tests/test_lidar_dashboard.py` | +103 / −0 | `_point_at()`, `_data_dots()` (baru), `test_the_plot_puts_the_front_up_and_the_robots_left_on_the_left()`, `test_the_front_marker_is_the_robot_and_carries_no_label()` | mengunci kesimpulan §3.2 dan permintaan ronde 2 & 3 di dalam test (tanpa `<polygon>`, tanpa teks `DEPAN`, 4 roda) |
| `tests/test_imu_heading.py` | +10 / −13 | `test_the_plot_draws_the_robot_at_the_measured_offset()` menyusul penanda baru; helper `_marker_rotation()` membaca rotasi grup robot | test lama membaca `<polygon>` dan label `DEPAN` yang sudah tidak ada |
| `docs/sesi_7.md` | +960 / −0 | dokumen ini | aturan log per sesi |

Total: **+1197 / −44** di 4 file (3 di antaranya kode), kumulatif sejak HEAD `823d2fb`.

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

Catatan penting yang ditemukan di sini: saat itu kode `lidar_panel.py` terakhir
berubah **14:27:31**, sedangkan proses dashboard hidup sejak **14:22:17** -- jadi
dashboard yang sedang dilihat operator masih memuat gambar versi antara
(cermin sudah dibalik, tetapi depan masih ke kanan dan penandanya masih
segitiga). Perlu **restart dashboard** supaya tampilan ronde 2 muncul.


### 10.2 Ronde 3 — "gambarkan robotnya", tanpa tulisan DEPAN

Permintaan operator, persis:

> "Gausah dikasi tulisan depan, Kalo kamu bisa gambarkan robotnya sih hebat yah.
> Jadi ga kaya geometri jelek gitu."

Yang berubah: penanda `<polygon>` segitiga (ronde 1) lalu `<rect>` + chevron +
label `DEPAN` (ronde 2) diganti **gambar robot tampak atas** dalam satu grup
`<g class="robot-marker">` yang diputar sebagai satu kesatuan: bodi chassis
sudut tumpul 24 x 32 px, empat roda abu-abu di kedua sisi, satu tonjolan sensor
di hidung (satu-satunya asimetri depan-belakang, jadi arah hadap terbaca tanpa
kata), dan titik hub tempat LiDAR duduk. Label `DEPAN` di dalam plot dihapus;
caption di luar plot yang menjelaskan.

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **423 passed** (13,2 s) | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| `"DEPAN" not in svg`, `"<polygon" not in svg` | test mengunci keduanya | TERVERIFIKASI |
| Rasterisasi penanda (dari SVG yang benar-benar dirender) | bodi + 4 roda + sensor hidung + hub, simetris kiri-kanan | TERUKUR |

Rasterisasi penanda hasil render (W = roda, `.` = bodi, `o` = sensor hidung,
`+` = hub LiDAR; depan = atas):

```
                            
             oo             
            oooo            
           oooooo           
  .........oooooo.........  
WWWW........oooo........WWWW
WWWW.........oo.........WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
  ........................  
  ........................  
  ...........++...........  
  ..........++++..........  
  ..........++++..........  
  ...........++...........  
  ........................  
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
WWWW....................WWWW
  ........................  
  ........................  
                            
                            
                            
                            
```

Alat baru, dan penting: `~/AMRTestLander/tools/robot_marker_preview.py` membuat
`tools/scans/robot_marker.html` **luring** dari berkas scan (tanpa membuka
port), jadi tampilan bisa diperiksa sementara dashboard tetap memegang
`/dev/ttyUSB0`. Halaman itu memuat plot 600 px, plot 300 px (ukuran dashboard),
dan penanda yang sama pada offset 0/30/60 deg untuk membuktikan rotasinya rapi.

Status ronde 3: **belum di-commit**; menunggu keputusan operator.


### 10.3 Ronde 4 — robot digambar sesuai ukuran, bukan simbol

Kata operator, persis:

> "Buat lebih kecil, ini tuh kesannya kayak tembok dan robot berdekatan. Padahal
> aslinya 1 meter lebih"

Ini bukan soal selera: penanda 32 px di plot 300 px membuat dinding 1,17 m
terlihat menempel. Angkanya jelas di plot default (rentang 4 m, radius 142 px =
35,5 px per meter):

| Besaran | Sebelum | Sesudah |
| --- | --- | --- |
| Panjang bodi di layar | 32 px (= 0,90 m ruang nyata) | **12,4 px** (= 0,35 m) |
| Lebar bodi | 24 px (= 0,68 m) | **9,2 px** (= 0,26 m) |
| Hidung robot dari pusat | 16 px | **6,2 px** |
| Celah hidung ke dinding 1,17 m (41,7 px) | 25,7 px | **35,5 px** |
| Skala ikut rentang tampil? | tidak (angka px tetap) | **ya** (`px_per_mm` dari plot) |

Perubahan teknis: konstanta baru `ROBOT_FOOTPRINT_MM = (260,0, 350,0)`
(lebar x panjang, dalam mm) dan `_robot_front_marker()` sekarang menerima
`px_per_mm` dari `render_scan_svg()` (`radius / max_range_mm`), lalu menghitung
setiap ukuran sebagai milimeter x `px_per_mm`. Karena itu robot **ikut mengecil
dan membesar bersama rentang tampil**, jadi gambarnya tetap jujur di rentang
berapapun.

Catatan kejujuran: `ROBOT_FOOTPRINT_MM` masih **nominal** -- chassis unit sekolah
ini belum pernah diukur dengan meteran. Ganti dengan angka hasil ukur begitu ada
meteran; tidak ada bagian lain yang perlu diubah.

Verifikasi ronde 4:

| Item | Hasil | Grade |
| --- | --- | --- |
| `pytest -q` | **424 passed** (13,3 s); +1 test skala | TERVERIFIKASI |
| `ruff check .` | bersih | TERVERIFIKASI |
| Test skala | bodi = `ROBOT_FOOTPRINT_MM` x `px_per_mm` (toleransi 0,05 px), dan panjangnya **dua kali** saat rentang tampil dijadikan separuh | TERVERIFIKASI |
| Rasterisasi penanda hasil render (300 px dan 600 px) | bodi + 4 roda + sensor hidung + hub, simetris | TERUKUR |

Penanda pada plot 600 px (W = roda, `.` = bodi, `o` = sensor hidung,
`+` = hub; depan = atas):

```
                         
                         
          oooo           
         oooooo          
   ......oooooo.......   
  WW.................WW  
  WW.................WW  
  WW.................WW  
   ...................   
   ........++.........   
   .......++++........   
   ...................   
   ...................   
  WW.................WW  
  WW.................WW  
  WW.................WW  
   ...................   
                         
                         
                         
```

Penanda pada plot 300 px (ukuran sebenarnya di dashboard):

```
              
     oooo     
  WW.......WW 
  WW.......WW 
   ...++....  
   .........  
  WW.......WW 
  WW.......WW 
              
              
```

Alatnya: `~/AMRTestLander/tools/robot_marker_preview.py` (luring, tanpa port).


---

## 11. Arm — protokol pabrik dibaca, probe read-only disiapkan (tanpa aktuasi)

Keputusan operator: **arm dulu**, kamera sesudahnya. Alasannya berubah begitu
paket pabrik diperiksa: SDK Python resmi untuk board yang sama ternyata sudah
ada di disk, sedangkan SDK kamera tidak ada dan menuntut `sudo` (lihat
`~/AMRTestLander/tools/camera_sudo_todo.md`, di luar repo).

Sumber yang dibaca (bukan ditebak): `~/LanderAsli(Beta).zip`, 261 entri, 1,0 MB,
diekstrak ke `~/.hermes/cache/scratch/lander_asli/` (di luar repo).

| Berkas / temuan | Isi | Grade |
| --- | --- | --- |
| `arm_pc/ros_robot_controller_sdk.py` | `buf_write` = `AA 55 <func> <len> <data> crc8(buf[2:])`; `PACKET_FUNC_BUS_SERVO = 5`; opcode baca `0x05` posisi, `0x07` vin, `0x09` suhu, `0x0D` status torque, `0x12` id, `0x32` angle limit; opcode tulis `set_position`, `enable_torque`, `set_offset`, `stop`, `set_id` | SOURCE-ONLY |
| `arm_pc/main.py` | 6 slider memetakan ke servo id **1, 2, 3, 4, 5, 10** (slider 6 -> id 10) | SOURCE-ONLY |
| `arm_pc/bus_servo_control.py` | `set_position(duration, [[id, pos]])`, posisi = pulse 0..1000, durasi ms/1000; **`if servo_id == 10: position = 1000 - position`** -> id 10 dibalik; `unloadBusServo()` = `enable_torque(id, 1)` (1 = lepas torsi, bukan mengunci) | SOURCE-ONLY |
| `arm_pc/action_group_controller.py` | berkas `.d6a` = SQLite, tabel `ActionGroup`, tiap baris = durasi_ms + 6 pulse; dijalankan dengan set tiap servo lalu `sleep(durasi)` | SOURCE-ONLY |
| `arm_pc/ActionGroups/` | 7 action group, termasuk `garbage_pick.d6a`, `garbage_pick_init.d6a`, `camera_up.d6a` | TERVERIFIKASI (ada) |

Kecocokan transport dengan repo ini, diuji **luring tanpa membuka port**: modul
SDK vendor dimuat sebagai modul Python lalu `buf_write`-nya direkonstruksi
persis, dibandingkan byte demi byte dengan `build_frame()` di
`src/amr_core/robot/stm32_protocol.py`.

| Item | Hasil | Grade |
| --- | --- | --- |
| `crc8` repo vs `checksum_crc8` vendor atas 100 payload acak | **identik, 0 beda** | TERVERIFIKASI |
| 18 frame baca (6 opcode x servo id 1/5/10) vs frame vendor | **18/18 byte-identik** | TERVERIFIKASI |
| Contoh | baca posisi servo 1 = `aa 55 05 02 05 01 6f` | TERVERIFIKASI |

Artinya: transport arm tidak menambah ketidakpastian -- board, framing, dan CRC
sudah dipakai sehari-hari untuk motor. Yang masih SOURCE-ONLY hanyalah arti
opcode dan pemetaan joint, dan itu yang harus diukur.

Alat baru: `~/AMRTestLander/tools/arm_probe.py` (di luar repo).

| Sifat | Isi |
| --- | --- |
| Read-only secara struktural | opcode yang boleh dikirim hanya yang ada di `READ_COMMANDS`; guard menolak opcode lain; tidak ada `set_position` / `enable_torque` / `stop` di berkas itu |
| Wajib `--confirm` | tanpa itu keluar dengan kode 2 dan tidak menyentuh port |
| Port eksklusif | `serial.Serial(..., exclusive=True)` -> gagal bersih kalau dashboard memegang `/dev/ttyACM0` |
| `--settle 3.0` | jendela boot 2,36 s setelah open (terukur di sesi 6) |
| Nol balasan | dilaporkan apa adanya + saran periksa daya/kabel, **bukan** mengganti opcode sampai "kebetulan cocok" |

Yang **belum** dilakukan: `/dev/ttyACM0` belum pernah dibuka di sesi ini, tidak
ada satu byte pun dikirim ke board, tidak ada aktuasi, dan probe belum
dijalankan. Langkah berikutnya butuh: arm diberi daya, area arm bebas, dan
dashboard berhenti (port satu pemilik).

Bukti bahwa probe belum pernah jalan: keluaran satu-satunya darinya adalah
`--help` dan penolakan tanpa `--confirm` (exit 2).


### 11.1 Cara mengetesnya, dan berkas instruksi di luar repo

Permintaan operator: *"kamu calo nyuruh aku jalanin command tertentu tulis di
file aja, jangan di chat ... aku gabisa copas soalnya"*. Mulai sekarang setiap
urutan perintah ditulis ke berkas di luar repo (`.txt`), dan di chat hanya
disebut path-nya.

| Berkas | Isi |
| --- | --- |
| `~/AMRTestLander/tools/ARM_TEST.txt` | prosedur uji arm: prasyarat, cek port, `--listen` dulu, probe read-only, cara membaca tabel, pohon diagnosis kalau tidak ada balasan, larangan sesi ini, dan rancangan tahap uji gerak (belum dijalankan) |
| `~/AMRTestLander/tools/CAMERA_SUDO.txt` | semua perintah yang butuh password sudo untuk jalur kamera (bekas `camera_sudo_todo.md`) |

Perubahan pada `arm_probe.py` setelah itu:

| Item | Isi |
| --- | --- |
| Mode `--listen SECONDS` | hanya membuka port dan melaporkan frame yang masuk; **tidak mengirim satu byte pun** -- uji "board hidup?" tanpa menulis ke board |
| Transkrip otomatis | setiap eksekusi menulis `~/AMRTestLander/tools/logs/arm_probe_<cap waktu>.txt`; bukti tidak lagi hanya ada di layar terminal |
| Penamaan fungsi | `PACKET_FUNC_NAMES` untuk menerjemahkan fungsi frame (SYS/LED/BUZZER/MOTOR/PWM_SERVO/BUS_SERVO/KEY/IMU/...) di mode listen |

Terverifikasi tanpa port: `py_compile` bersih, dan tanpa `--confirm` skrip
keluar dengan kode 2 serta tidak menyentuh port.


### 11.2 Probe dijalankan — 6/6 servo menjawab, limit tiap joint terukur

Operator menjalankan sendiri (dan Hermes menjalankan ulang setelah perbaikan).
Dashboard dimatikan lebih dulu; /dev/ttyACM0 bebas di kedua kali.

**Sesi `--listen 5` (operator, 15:32):** 407 frame tanpa mengirim satu byte pun
= **IMU 400 frame (~80 Hz)** + **SYS 7 frame (~1,4/s)**, `crc gagal 0`. Board
hidup, dan CRC/framing kita benar di board ini.

**Sesi `--confirm` (15:36-15:37):**

| id | balas id | posisi | limit | vin mV | temp C | torque |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 491 | 50-950 | 8051 | 31 | 0 |
| 2 | 2 | 705 | 40-960 | 8002 | 28 | 0 |
| 3 | 3 | 40 | 0-900 | 8009 | 27 | 0 |
| 4 | 4 | 96 | 70-970 | 8022 | 27 | 0 |
| 5 | 5 | 514 | 50-950 | 8051 | 28 | 0 |
| 10 | 10 | 205 | 200-600 | 7969 | 28 | 0 |

**TERUKUR:** arm ini punya **6 joint, id 1, 2, 3, 4, 5, 10** (cocok dengan
pemetaan GUI pabrik), rail daya servo hidup (~8,0 V di semua servo), suhu
27-31 C, dan **rentang aman tiap servo** kini punya angkanya -- sebelumnya
hanya dari dokumen. id 10 paling sempit (200-600), konsisten dengan grip
berjari pendek. Arti status torque `0` **belum diketahui** dan tidak diklaim.

**Dua bug di probe sendiri, keduanya ketemu hari ini (ditulis sebagai GAGAL):**

| Trial | Gejala | Sebab | Perbaikan |
| --- | --- | --- | --- |
| probe pertama | `TypeError: unsupported format string passed to NoneType` dan tabel kosong | `row["id"]` dipakai untuk dua arti (id yang ditanya vs id yang menjawab), lalu ditimpa hasil bacaan | kunci dipisah: `asked` vs `id` |
| probe pertama | dilaporkan **0/6 menjawab** padahal 36 frame func 5 masuk (satu per pertanyaan) | bit status dibaca terbalik; vendor memakai `if success == 0: return info`, jadi **0 = berhasil** | `if success != 0: return None` |

Pelajaran yang dicatat: "0/6 menjawab" yang datang bersama 36 balasan func 5
berarti **dekoder** yang salah, bukan arm-nya. Yang membedakan cuma menghitung
frame masuk -- tanpa itu, hasilnya akan dilaporkan sebagai "arm tidak terhubung".

Keluaran mentah yang akhirnya membuka keduanya (satu query per baris,
payload setelah `AA 55 05 <len>`):

```
id=1 position 0x05 -> 01 05 00 eb 01         posisi = 0x01EB = 491
id=1 vin      0x07 -> 01 07 00 75 1f         vin    = 0x1F75 = 8053 mV
id=1 temp     0x09 -> 01 09 00 1f            suhu   = 31 C
id=1 torque   0x0D -> 01 0d 00 00            status = 0
id=1 id       0x12 -> 01 12 00 01            balas id = 1
id=1 limit    0x32 -> 01 32 00 32 00 b6 03   limit  = 50 .. 950
id=254 id     0x12 -> fe 12 ff 65            broadcast: status 0xFF -> ditolak
```

Perbaikan lain di `arm_probe.py` pada sesi yang sama: mode `--listen` mencetak
**semua frame selain IMU** apa adanya (sebelumnya hanya 40 frame pertama, yang
selalu keburu dihabiskan IMU sehingga frame SYS tidak pernah terlihat), dan
setiap eksekusi menulis transkrip ke `tools/logs/`.

**Aturan operator yang dicatat (keras):** saat menggerakkan arm, **jangan sentuh
gripper** dan jangan perintahkan servo id 10. Membaca id 10 tidak
menggerakkannya; yang dilarang adalah memerintahkannya. Aturan ini ditulis di
`tools/ARM_TEST.txt`, di bagian "Tahap berikutnya", dan di skill
`amr-stm32-port-boot-window`.

Tahap berikutnya (uji gerak) **belum** dijalankan dan tetap butuh izin
terpisah: satu joint, satu perintah, langkah kecil di dalam limit terukur,
durasi lambat, arm di udara.


### 11.3 Alat tahap-2 (gerak satu joint) sudah siap, belum dijalankan

`~/AMRTestLander/tools/arm_move_test.py` -- skrip pertama di proyek ini yang
*bisa* menggerakkan arm. Dibuat sengaja membosankan, dan pagarnya berlapis:

| Pagar | Isi | Hasil uji |
| --- | --- | --- |
| Gripper | id 10 ditolak sebelum apa pun terjadi (aturan operator) | exit 3, pesan eksplisit (terverifikasi) |
| Limit | target harus di dalam limit terukur servo; limit dibaca ulang dari servo saat itu | target 999 di id 5 ditolak (terverifikasi) |
| Langkah | `|target - posisi sekarang| <= --max-step` (default 25 pulse) | target 700 dari 514 (+186) ditolak (terverifikasi) |
| Kecepatan | durasi minimum 500 ms | durasi 200 ms ditolak (terverifikasi) |
| Konfirmasi | kata `MOVE` harus diketik; tanpa `--confirm` hanya mencetak frame dan keluar | exit 2 (terverifikasi) |
| Satu pemilik port | `exclusive=True` | gagal bersih kalau dashboard memegang port |
| Bukti | frame dicetak + transkrip ke `tools/logs/`, posisi dibaca ulang setelah gerak | -- |

Frame geraknya diuji luring terhadap rekonstruksi `bus_servo_set_position`
milik SDK vendor: **3/3 kasus byte-identik**, mis. id 5 +16 pulse dalam 2000 ms
= `aa 55 05 07 01 d0 07 01 05 12 02 ...`. Frame stop (`0x03`) juga sudah ada.

Terverifikasi tanpa gerak: kelima penolakan di atas, dan satu pembacaan nyata
(id 5 = 514, limit 50-950) yang membuktikan jalur baca di skrip ini hidup.

**Belum dijalankan**: belum ada satu byte gerak yang pernah dikirim ke arm di
sesi ini. Uji pertama yang diusulkan: id 5, target 530 (langkah +16), durasi
2000 ms, arm di udara, tangan di luar jangkauan, gripper tidak disentuh.


### 11.4 Uji gerak pertama — satu joint, +16 pulse, BERHASIL

Izin operator: *"Uji saja, asal jangan sentuh griper"*. Dashboard mati, port
bebas, id 5 dibaca dulu (514, limit 50-950 dari servo sendiri).

| Item | Nilai | Grade |
| --- | --- | --- |
| Frame yang dikirim | `aa 55 05 07 01 d0 07 01 05 12 02 05` (id 5, pulse 530, durasi 2000 ms) | TERVERIFIKASI (byte-identik dgn SDK vendor) |
| Posisi sebelum | 514 | TERUKUR |
| Posisi diminta | 530 (+16 pulse) | — |
| Posisi setelah dibaca ulang | **525** | TERUKUR |
| Selisih terhadap permintaan | −5 pulse (~0,5 % dari rentang 0-1000) | TERUKUR |
| Gripper | **tidak diperintahkan, tidak disentuh**; id 10 ditolak oleh skrip sebelum apa pun terjadi | TERVERIFIKASI |
| Kata `MOVE` | diketik Hermes atas persetujuan operator di sesi (operator tidak bisa mengetik dari chat) | — |
| Frame diterima saat sesi | 11, dengan **1 CRC gagal** (balasan yang dipakai lolos CRC; dicatat apa adanya) | TERUKUR |

Catatan: servo **menahan** posisi barunya setelah gerak (tidak ada perintah
pelepas torsi yang dikirim), jadi arm tidak menjadi lemas. Yang **belum**
diketahui dan tidak diklaim: id 5 itu sendi yang mana secara fisik -- hanya
operator yang melihatnya yang bisa memetakan, dan itu langkah berikutnya.


#### 11.4.1 Ulangan dengan langkah lebih besar — dan dua hal yang muncul

Operator: *"Ulang, ga keliatan samsek"* (+16 pulse memang terlalu kecil untuk
mata: 11 pulse nyata ~ 3 derajat). Ulangan: id 5, 526 -> 645 (+119 pulse,
2500 ms, `--max-step 150`).

| Item | Nilai | Grade |
| --- | --- | --- |
| Frame | `aa 55 05 07 01 c4 09 01 05 85 02 8d` | TERVERIFIKASI |
| Posisi sebelum / diminta / sesudah | 526 / 645 / **638** | TERUKUR |
| Langkah nyata | +112 pulse (~11 % dari rentang 0-1000) | TERUKUR |
| CRC gagal | 2 dari 12 frame diterima (ulangan pertama: 1 dari 11) | TERUKUR |
| Gripper | tetap tidak diperintahkan dan tidak disentuh | TERVERIFIKASI |

Dua hal yang **belum** dijelaskan dan tidak diklaim:

1. **Apakah mekaniknya ikut bergerak.** Servo melaporkan posisinya berubah,
   tetapi laporan itu hanya membuktikan encoder di dalam servo. Kalau sendi
   fisiknya tidak terlihat bergerak pada langkah 112 pulse, kandidatnya: horn/
   kopel servo lepas, atau sendi itu memang berputar di sumbu yang sulit dilihat.
2. **Dua joint berubah tanpa perintah.** Pembacaan ulang seluruh id sesudahnya:
   id 1 491 -> **457** (-34), id 4 96 -> **113** (+17), id 2 +3, id 3 tetap 40.
   Penyebabnya belum diketahui: bisa operator menyentuhnya, bisa sag di bawah
   gravitasi. Tidak ada perintah yang dikirim untuk id 1/2/3/4 di sesi ini.


### 11.5 Manual pabrik: peta id -> sendi (menjelaskan kenapa gerakan tak terlihat)

Operator menunjuk berkasnya: `~/dokumentasi_lander/1. Tutorials/9. Robotic Arm
Control/9. Robotic Arm Control.pdf` (90 hal.). Teksnya diekstrak dengan
`pypdfium2` (dipasang ke venv, tanpa sudo); halaman gambar dirender ke PNG untuk
mata operator, karena **Hermes tidak bisa melihat gambar** (modelnya teks).

Kutipan langsung, hal. 27:

> "No. 1 is the pan-tilt servo, No. 2, 3, and 4 are the robotic arm joint
> servos, No. 5 is the wrist servo, and No. 10 is the claw servo. When the
> robotic arm is in use, a total of 6 servos are controlled."

| id | fungsi menurut manual | Grade |
| --- | --- | --- |
| 1 | servo pan-tilt | SOURCE-ONLY |
| 2, 3, 4 | sendi lengan | SOURCE-ONLY |
| 5 | **wrist** (pergelangan) | SOURCE-ONLY |
| 10 | **claw / gripper** | SOURCE-ONLY |

Konsekuensi langsung: uji gerak kita memakai **id 5 = wrist**. Pergelangan yang
berputar ~112 pulse memang kandidat kuat untuk "tidak terlihat dari tempat
operator berdiri" -- jadi pengamatan operator dan manual saling mendukung, dan
hipotesis "kopel servo lepas" belum perlu dipakai.

Catatan manual lain yang berguna:

- Arm = 6-DOF, 6 x servo **HX-06L** (hal. 25). Sudut netral (hal. 28-29): servo
  1-5 sejajar horizontal/vertikal terhadap chassis, dan **gripper terbuka 2-3 cm**.
  Posisi terukur arm kita (id 3 = 40, di ujung bawah limit 0-900) menunjukkan
  arm **tidak** dalam posisi netral.
- Hal. 32 menyebut servo 3 pernah punya deviasi -18 yang dikoreksi lewat software
  host (GUI `arm_pc/`) -- jadi deviasi tersimpan per servo dan bisa menjelaskan
  posisi yang tampak "melenceng" tanpa bug.
- Dua pernyataan pabrik yang **saling bertentangan** dan belum diselesaikan:
  hal. 25 bilang "2 for the pan-tilt unit, 2 for the main body, and 1 for the
  wrist" (kalau ditambah claw = 6, berarti pan-tilt 2 servo), sedangkan hal. 27
  hanya menyebut 1 servo pan-tilt. Yang terukur: bus menjawab tepat 6 id
  (1,2,3,4,5,10), jadi jumlahnya 6 -- pembagian fungsinya yang belum pasti.
- User Manual hal. 4 menulis dua kabel servo 3-pin dari pan-tilt masuk ke **port
  servo STM32** (PWM, fungsi 4), bukan ke bus. Artinya unit pan-tilt itu
  kemungkinan bukan bagian dari 6 bus servo di atas. Belum kami verifikasi di
  robot ini; operator yang bisa melihat langsung.
- Arm manual hal. 24 menyebut Aurora930 dipakai untuk hand-tracking, sortir balok
  warna, line-following + buang halangan, klasifikasi sampah, dan transport
  point-to-point. Jadi **kamera dan arm saling terkait** -- prioritas
  arm-dulu/kamera-kemudian bukan dua jalur yang benar-benar terpisah.

Halaman yang dirender untuk operator (Hermes tidak bisa melihatnya):
`~/AMRTestLander/tools/manual_pages/arm_hal27.png` (penomoran servo),
`arm_hal28.png` (kriteria netral), `arm_hal1.png` (foto/daftar produk),
`landerpi_hal1..6.png` (ikhtisar produk + wiring).


### 11.6 Keputusan operator: pemetaan sudah diketahui, kartu SD asli sudah ter-flash

Catatan commit (diminta operator: *"Commit aja kenapa nunggu lama"*):

| Commit | Isi |
| --- | --- |
| `f9d59dd` | fix: draw the LiDAR plot front-up and stop mirroring the room |
| `83929cd` | fix: draw the robot itself, to scale, as the LiDAR plot's facing marker |
| (commit dokumen ini) | docs: log session 7 |

Operator: *"sebenarnya sih aku udh tau ya pemetaannya. Soalnya ini kan sebenarnya
ganti SD card aja. Aslinya udh ada softwarenya sendiri dan aku udh pernah nyoba.
Tapi kalo kamu butuh makesure bilang aja nanti aku jadi pengamat untukmu."*

Dua hal yang berubah karenanya:

1. **Pemetaan id -> sendi naik dari SOURCE-ONLY (manual) menjadi "operator, dari
   software pabrik".** Uji gerak 4x untuk memetakan id 1-4 tidak lagi wajib; ia
   jadi opsi kalau Hermes butuh bukti mata sendiri. Prosedurnya (id per id,
   langkah kecil, id 10 dikecualikan, operator menyebut sendinya) sudah ditulis
   di `tools/ARM_TEST.txt`.
2. **Kartu SD asli pabrik adalah sumber daya yang belum dimanfaatkan.** Image itu
   pernah dipakai dan berisi software yang jalan. Membacanya (read-only) bisa
   menjawab hal-hal yang sampai sekarang jadi penghalang, terutama: apakah SDK
   Deptrum/Aurora930 sudah ada di sana (kalau ya, jalur kamera tidak perlu unduh
   tarball), konfigurasi/deviasi servo versi pabrik, dan action group yang
   benar-benar dipakai.

Prosedur membacanya -- termasuk peringatan read-only dan bagian yang butuh
password -- ditulis di `~/AMRTestLander/tools/SDCARD_INSPECT.txt`.

**Koreksi dari operator:** kartu SD aslinya **sudah ter-flash** (isinya sudah
ditimpa image sendiri), jadi jalur "colok kartunya" tertutup. Yang tersisa:
operator punya **backup seluruh isinya** sebagai berkas, tetapi tidak punya
kartu SD kosong untuk menampung hasil restore. Catatan penting: berkas backup
itu **tidak perlu kartu SD dan tidak perlu di-restore** untuk diperiksa -- ia
bisa dibaca di tempat, read-only (pindai string tanpa sudo, atau loop-mount
read-only yang butuh password). Itu jalur yang ditawarkan berikutnya, menunggu
lokasi dan format berkas backup-nya dari operator.


### 11.7 Paket kamera dari Drive: manual yang "hilang" ternyata ada, plus SDK aarch64

Operator menyalin satu zip dari Drive: `~/dokumentasi_lander/drive-download-20261028T084843Z-1-001.zip`.
Zip itu belum selesai saat pertama kuperiksa (`BadZipFile`; ditulis proses node,
bertambah ~2,5 MB/s), jadi daftar isinya kuwalik dulu lewat pembacaan header
sekuensial. Setelah unduhannya selesai: **1064 MB, 21 entri, 1,14 GB setelah
dibuka**.

| Isi zip | Ukuran | Berguna untuk kita? |
| --- | --- | --- |
| `1 Depth Camera Overview/1 Deptrum® Aurora 930 Depth Camera Overview.pdf` | 0,33 MB | **ya** — manual depth camera yang operator kira tidak ada |
| `2 .../ROS1 .../1 Depth Camera Setup and Usage.pdf` + paket x86_64 | 25,4 MB | tidak langsung (jalur ROS1, VM x86) |
| `2 .../ROS2 .../1 ... in ROS2.pdf` + `deptrum-ros-driver-humble-aarch64.tar.gz` | 43,2 MB | **ya** — berisi SDK aarch64 + sample |
| `3 .../Winwods/` (tool + pdf) | 117,5 MB | tidak |
| `4 Appendix/1 Virtual Machine Image` | 623,2 MB | tidak (VM ROS1 Melodic x86) |
| `4 Appendix/2 Source Code` (ROS1+ROS2, x86_64 & **aarch64**) | 88,7 MB | sebagian |
| `4 Appendix/3 Tools` (`deptrum-scope-linux-**aarch64**-v3.6.17`) | 239,8 MB | **ya** — GUI scope arm64 |

Diekstrak selektif (bukan 1 GB, hanya yang perlu) ke
`~/dokumentasi_lander/kamera_aurora930/`: tiga PDF, tarball scope aarch64,
paket ROS2 aarch64, dan `sdk_aarch64/` (97 entri `ext/`).

Yang ditemukan di dalamnya (TERVERIFIKASI: dibaca dari arsipnya):

| Berkas | Isi |
| --- | --- |
| `.../lib/libdeptrum_stream_aurora900.so.1.1.19` | **SDK stream aarch64**, 16 MB |
| `include/deptrum/{stream,device,aurora900_series,stream_types,common_types}.h` | header API C |
| `samples/bin/{hello_deptrum,sample,sample_lite,firmware_upgrade}` | **biner aarch64 siap jalan**, tanpa build |
| `scripts/99-deptrum-libusb.rules` | `SUBSYSTEM=="usb", ATTRS{idVendor}=="3251", MODE:="0666", TAG+="uaccess", TAG+="udev-acl"` |
| `scripts/install_dependency.sh` | `libusb-1.0-0-dev`, `libgl1-mesa-dev`, `build-dep glfw`, `libglu1-mesa-dev`, `libxi-dev`, `libudev-dev` |

**Kenapa udev itu wajib (TERUKUR, bukan dugaan):** node kamera sekarang
`crw-rw-r-- root root` → user hanya bisa membaca, sedangkan komunikasi ke kamera
butuh menulis. Jadi satu aturan udev itulah pembukanya, dan itu satu-satunya
langkah yang butuh password.

`~/AMRTestLander/tools/CAMERA_SUDO.txt` ditulis ulang (versi 2) dengan perintah
**nyata** dari skrip vendor, bukan placeholder lagi, termasuk peringatan supaya
`sudo apt-get build-dep glfw` tidak dijalankan buta (butuh deb-src).

Jalur tanpa ROS sudah terlihat: biner `hello_deptrum` (aarch64) + SDK, lalu
pembaca frame via `ctypes`. Yang **belum** terverifikasi: apakah kamera benar-
benar mengalirkan frame — itu menunggu aturan udev dipasang operator.

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

# probe arm READ-ONLY (butuh --confirm, port harus bebas)
~/AMRTestLander/.venv/bin/python ~/AMRTestLander/tools/arm_probe.py --confirm

# penanda robot: pratinjau LURING dari berkas scan (tidak membuka port)
~/AMRTestLander/.venv/bin/python ~/AMRTestLander/tools/robot_marker_preview.py \
    --scan ~/AMRTestLander/tools/scans/scan_C_botol_kanan.txt

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
