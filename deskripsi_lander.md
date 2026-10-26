# Panduan & Deskripsi Lengkap Robot Hiwonder LanderPi ROS2

> **Dokumen Referensi Resmi & Spesifikasi Teknis Komprehensif**  
> Sumber data dihimpun dari:
> - [Hiwonder Official Store - LanderPi Product Page](https://www.hiwonder.com/products/landerpi?variant=41948378988631)
> - [OpenELAB Technology Ltd. - LanderPi Robot Car Kit](https://openelab.io/products/landerpi-robot-car?variant=46099795968198)
> - [Hiwonder Official Wiki Documentation](https://wiki.hiwonder.com/projects/LanderPi/en/latest/)

---

## 1. Ikhtisar Produk (Product Overview)

**Hiwonder LanderPi** adalah platform robot riset dan edukasi tingkat lanjut (*advanced composite educational mobile manipulator*) bertenaga **Raspberry Pi 5** yang beroperasi secara native di atas framework **ROS 2 (Robot Operating System 2)**. 

Robot ini menggabungkan platform pergerakan bergerak (*mobile base*) dengan lengan robot artikulasi **6 Derajat Kebebasan (6-DOF Robotic Arm)**, sensor **TOF LiDAR 360°**, kamera visi mendalam **3D Structured Light Depth Camera (Aurora930 Pro)**, serta modul suara cerdas **WonderEcho Pro AI Voice Interaction Box**. 

LanderPi dirancang untuk menjembatani integrasi antara robotika mobile, manipulasi lengan robotik, computer vision, autonomous driving, hingga konsep mutakhir **Embodied AI** yang ditenagai oleh **Multimodal Large Language Models (LLM seperti OpenAI ChatGPT)**.

```
                    ┌──────────────────────────────────────────────┐
                    │               LanderPi System                │
                    └──────────────────────┬───────────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         ▼                                 ▼                                 ▼
┌──────────────────┐             ┌──────────────────┐             ┌──────────────────┐
│  High-Level AI   │             │   Low-Level MCU  │             │ 6-DOF Robot Arm  │
│  Raspberry Pi 5  │◄──Serial───►│   STM32F407VET6  │◄──Serial───►│ 6x HX-06L Servos │
│ (Ubuntu 22/ROS2) │             │ (RRC Lite Board) │             │ Eye-in-Hand Cam  │
└────────┬─────────┘             └────────┬─────────┘             └──────────────────┘
         │                                │
         ├─► Aurora930 Pro 3D Cam         ├─► AB-Phase Magnetic Encoder Motors
         ├─► Aoride MS200 TOF LiDAR       ├─► QMI8658 6-Axis IMU Sensor
         ├─► WonderEcho Pro AI Box        ├─► Battery BMS & 5V/5A Power Supply
         └─► Wi-Fi / App / ChatGPT LLM    └─► PWM Servos (Chassis Steering)
```

---

## 2. Fitur Unggulan Utama (Key Features)

1. **Pemrosesan Cerdas Raspberry Pi 5 & ROS 2 Native**:  
   Ditenagai oleh prosesor quad-core 64-bit Arm Cortex-A76 pada Raspberry Pi 5 dengan lingkungan sistem berbasis **Raspberry Pi OS + Ubuntu 22.04 LTS + ROS 2 Humble** (berjalan dalam arsitektur container Docker yang terisolasi dan stabil).
2. **Arsitektur Dual-Controller (Kolaborasi Efisien)**:  
   - **Komputer Tingkat Tinggi (High-Level)**: Raspberry Pi 5 menangani komputasi visual, inferensi model deep learning, SLAM, navigasi Nav2, MoveIt2, serta komunikasi Large AI Model.
   - **Kontroler Gerak Tingkat Rendah (Low-Level)**: Papan **RRC Lite (berbasis STM32F407VET6 Cortex-M4 @ 168 MHz)** dengan FPU/DSP onboard menangani kontrol closed-loop motor encoder dengan algoritma PID presisi tinggi, telemetri bus servo, pembacaan IMU 6-axis, dan manajemen daya.
3. **Pilihan 3 Jenis Chassis Modular & Fleksibel**:  
   Dapat dikonfigurasi menjadi **Mecanum Chassis** (gerakan omnidirectional), **Ackermann Chassis** (pengemudian presisi gaya mobil), atau **Tank Chassis** (daya jelajah tinggi di medan kasar).
4. **Lengan Robotik 6-DOF dengan Smart Bus Servo**:  
   Menggunakan 6 unit servo cerdas serial bus **HX-06L** berkekuatan torsi 6 kg·cm dengan feedback sudut real-time, perlindungan stall, temperatur, dan voltase. Lengan ini mendukung kinematika balik (Inverse Kinematics) dan mampu mengangkat beban hingga 200 gram.
5. **Kamera 3D Depth "Eye-in-Hand"**:  
   Kamera **Aurora930 Pro 3D Depth** dipasang tepat di ujung lengan robot (end-effector/gripper). Memberikan perspektif orang pertama (First-Person View / FPV) dengan data awan titik (*point cloud*) untuk pengenalan objek, estimasi koordinat 3D, penentuan jarak, pengukuran volume, serta pemilahan (*sorting*) barang secara mandiri.
6. **LiDAR 360° TOF SLAM & Navigasi Otonom**:  
   Menggunakan **Aoride/Oradar MS200 TOF LiDAR** berfrekuensi sampling 4500Hz untuk pemetaan 2D/3D (Cartographer, Gmapping, RTAB-VSLAM), perencanaan rute (TEB/DWB Local Planner), dynamic obstacle avoidance, navigasi multi-titik, dan patroli area (*LiDAR Guard/Tracking*).
7. **Empowered by Large AI Model (Embodied AI & ChatGPT)**:  
   Mengintegrasikan model multimodal besar dengan ChatGPT sebagai inti penalaran semantik. Robot mampu memahami instruksi suara natural manusia, mengonversinya menjadi rencana aksi fisik, menavigasi ke tujuan, mengidentifikasi target secara visual, dan memanipulasi objek secara otomatis (*Voice-to-Action pipeline*).
8. **Autonomous Driving & Deep Learning (YOLOv8 & MediaPipe)**:  
   Mendukung pengenalan rambu lalu lintas, lampu APILL, deteksi lajur jalan dengan kendali PID, deteksi gestur tangan, pelacakan ujung jari (*fingertip control*), pose tubuh manusia, dan augmented reality (AR).
9. **Simulasi Digital Twin (MoveIt2, URDF & Gazebo)**:  
   Tersedia model deskripsi robot lengkap dalam format URDF/Xacro, visualisasi interaktif di RViz2, serta simulasi dinamika fisik di Gazebo.

---

## 3. Perbandingan Varian Edisi Kit (Starter, Standard, Advanced)

LanderPi dipasarkan dalam 3 tingkatan kit fungsional:

| Parameter / Fitur | Starter Kit | Standard Kit | Advanced Kit |
| :--- | :--- | :--- | :--- |
| **Kamera Bawaan** | Kamera Monokuler HD (Monocular Camera) | **Aurora930 Pro 3D Depth Camera** | **Aurora930 Pro 3D Depth Camera** |
| **Sensor LiDAR** | Aoride MS200 TOF LiDAR (360°) | Aoride MS200 TOF LiDAR (360°) | Aoride MS200 TOF LiDAR (360°) |
| **Lengan Robotik** | 6-DOF Robotic Arm (HX-06L Bus Servos) | 6-DOF Robotic Arm (HX-06L Bus Servos) | 6-DOF Robotic Arm (HX-06L Bus Servos) |
| **Modul Suara AI** | Tidak disertakan | Tidak disertakan | **WonderEcho Pro AI Voice Box** |
| **Kemampuan Visi 2D** | Pengenalan warna, QR Code, line follower, YOLOv8 rambu lalu lintas | Pengenalan warna, QR Code, line follower, YOLOv8 rambu lalu lintas | Pengenalan warna, QR Code, line follower, YOLOv8 rambu lalu lintas |
| **Kemampuan Visi 3D** | Tidak didukung | **Point cloud, RTAB-VSLAM 3D, estimasi koordinat 3D, pengukuran dimensi/jarak** | **Point cloud, RTAB-VSLAM 3D, estimasi koordinat 3D, pengukuran dimensi/jarak** |
| **Interaksi Suara & ChatGPT** | Tidak didukung | Tidak didukung | **Didukung penuh (Voice Control, LLM ChatGPT, Multimodal Embodied AI)** |
| **Pilihan RAM Raspberry Pi 5** | Tanpa Pi / 2GB / 4GB / 8GB / 16GB | Tanpa Pi / 2GB / 4GB / 8GB / 16GB | Tanpa Pi / 2GB / 4GB / 8GB / 16GB |
| **Kartu MicroSD 64GB** | Termasuk (jika beli dengan Pi 5) | Termasuk (jika beli dengan Pi 5) | Termasuk (jika beli dengan Pi 5) |

---

## 4. Karakteristik & Spesifikasi 3 Pilihan Chassis

Pengguna dapat memilih salah satu dari 3 desain platform mekanikal:

```
┌─────────────────────────────────┬─────────────────────────────────┬─────────────────────────────────┐
│        Mecanum Chassis          │        Ackermann Chassis        │          Tank Chassis           │
├─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────┤
│ • 4 Roda Mecanum independen     │ • Pengemudian belok roda depan  │ • Sistem crawler / track karet  │
│ • Pergerakan omnidirectional    │ • Sistem kemudi servo digital   │ • Daya cengkeram & traksi tinggi│
│ • Bisa strafe & drift menyamping│ • Mirip dinamika mobil nyata    │ • Handal di rintangan & tanjakan│
└─────────────────────────────────┴─────────────────────────────────┴─────────────────────────────────┘
```

### Rincian Komparasi Chassis (Versi Kamera Depth):

| Parameter | Mecanum Chassis (M1) | Ackermann Chassis (A1) | Tank Chassis (T1) |
| :--- | :--- | :--- | :--- |
| **Gaya Gerakan** | Omnidirectional (Maju, mundur, menyamping/strafe, rotasi di tempat, diagonal) | Pengemudian gaya mobil (Ackermann Steering Geometry: kemudi roda depan, traksi belakang) | Gerakan diferensial tank (Dual tracked drive, putar di tempat, daya jelajah rintangan) |
| **Dimensi Fisik** | 212 x 174 x 441 mm | 213 x 160 x 448 mm | 278 x 195 x 458 mm |
| **Berat Bersih** | 1.79 kg | 1.73 kg | 2.18 kg |
| **Tipe Motor Penggerak** | 4x 310 Metal Geared DC Motor (JGA27-310R20) | 2x 310 Metal Geared DC Motor (Roda Belakang) | 2x MC520 High-Torque Metal Geared DC Motor |
| **Servo Kemudi** | - | 1x LD-1501MG High-Torque Digital Servo (Roda Depan) | - |
| **Karakteristik Medan** | Lantai datar indoor, laboratorium, arena kompetisi | Lintasan sirkuit autonomous driving, simulasi mobil otonom | Karpet tebal, tanjakan, area luar ruangan datar/kasar |

---

## 5. Spesifikasi Detail Perangkat Keras (Hardware Specifications)

### 5.1. Komputer Utama (High-Level Controller)
- **Model**: Raspberry Pi 5 Mainboard.
- **Prosesor**: Broadcom BCM2712, Quad-core Arm Cortex-A76 @ 2.4GHz (kriptografi 64-bit).
- **GPU**: VideoCore VII GPU @ 800MHz.
- **Kapasitas RAM**: Pilihan varian 2GB / 4GB / 8GB / 16GB LPDDR4X SDRAM.
- **Konektivitas**: Dual-band Wi-Fi (802.11ac 2.4GHz & 5.0GHz), Bluetooth 5.0 / BLE, Gigabit Ethernet (RJ45).
- **Penyimpanan**: 64GB High-Speed TF / MicroSD Card (sudah terisi image sistem ROS 2).
- **Port USB**: 2x USB 3.0 (kecepatan 5Gbps), 2x USB 2.0.

### 5.2. Kontroler Gerak Bawah (Motion Controller - RRC Lite)
- **Mikrokontroler Inti**: **STM32F407VET6** (32-bit ARM Cortex-M4 dengan hardware FPU & DSP, clock speed 168 MHz, 512 KB Flash, 192 KB SRAM).
- **Sensor IMU Onboard**: **QMI8658** 6-Axis Motion Tracking Sensor (3-axis gyroscope dan 3-axis accelerometer terintegrasi).
- **Koneksi Motor**: 4x soket motor encoder PH2.0 6-pin.
- **Port Servo Serial Bus**: 2x port 5264-3P untuk daisy-chain servo lengan robotik HX-06L.
- **Port Servo PWM**: 4x port PWM dengan jumper pemilih tegangan (5V / VIN) untuk kemudi Ackermann atau pan-tilt.
- **Regulator Daya Internal**: Output khusus 5V @ 5A teregulasi untuk mencatu daya Raspberry Pi 5 secara stabil.
- **Antarmuka Eksternal**:
  - Port I2C expansion.
  - SWD Debug port untuk pemrograman mikrokontroler.
  - Port USB-Serial (CH340/FTDI) untuk komunikasi data berkecepatan tinggi dengan Raspberry Pi 5.
  - 2x LED RGB programmable.
  - 2x Tombol pengguna (User Buttons) & 1x Tombol Reset.
  - Buzzer terintegrasi untuk notifikasi status baterai dan startup.

### 5.3. Lengan Robotik 6-DOF (Articulated Robotic Arm)
- **Derajat Kebebasan (DOF)**: 6 Derajat Kebebasan (Base Rotation, Shoulder Pitch, Elbow Pitch, Wrist Pitch, Wrist Roll, Gripper Claw).
- **Servo Utama**: 6 unit **Hiwonder HX-06L Smart Serial Bus Servo**.
  - **Tegangan Kerja**: 6.0 V – 8.4 V (Rated 7.4 V).
  - **Torsi Stall**: 6.0 kg·cm @ 7.4 V.
  - **Kecepatan Rotasi**: 0.20 detik / 60° @ 7.4 V.
  - **Sudut Rotasi**: 0° – 240° (nilai register internal: 0 – 1000).
  - **Presisi Kendali**: 0.3°.
  - **Transmisi Gigi**: Gigi Logam Tahan Aus (Full Metal Gears).
  - **Protokol Komunikasi**: Serial UART Bus (Baudrate 115200 bps).
  - **ID Servo**: Dapat dialamatkan dari 0 hingga 253.
  - **Telemetri Umpan Balik**: Posisi sudut real-time, temperatur motor, dan voltase input.
  - **Sistem Proteksi**: Stall protection (perlindungan macet) dan over-temperature protection.
- **Maksimum Beban Angkat yang Direkomendasikan**: **200 gram**.

### 5.4. Kamera Visi 3D Depth (Aurora930 Pro)
- **Teknologi**: 3D Structured Light Depth Sensing (Deptrum Aurora 930 Series).
- **Dimensi**: 76.5 x 20.7 x 21.8 mm.
- **Jarak Antar Lensa (Baseline)**: 40 mm.
- **Jarak Kerja Efektif**: 15 cm – 300 cm (rentang operasional optimal: 30 – 300 cm).
- **Akurasi Depth**: ±8 mm @ 1 m; Presisi: 3 mm @ 0.5 m dan 7 mm @ 1 m.
- **Format & Resolusi Citra**:
  - **Depth**: 16-bit Raw, resolusi 640 x 400 @ 12–15 fps (FOV: Horizontal 71°–74°, Vertikal 46°–51°).
  - **RGB (Color)**: Format NV12, resolusi 640 x 400 @ 12–15 fps.
  - **Inframerah (IR)**: 8-bit Raw, resolusi 640 x 400 @ 12–15 fps.
- **Konsumsi Daya**: Rata-rata < 1.6 W (5 V ±10%, 1.5 A).
- **Tingkat Keamanan Laser**: **Class 1 Laser Safety** (Standar internasional, 100% aman untuk mata manusia).
- **Antarmuka**: USB 2.0 Wafer Connector.
- **Kompatibilitas Sistem Operasi**: Linux, ARMv8, ROS/ROS2, Windows, Android.

### 5.5. Sensor LiDAR TOF 360° (Aoride / Oradar MS200)
- **Prinsip Pengukuran**: Time-of-Flight (TOF) Pulse Laser Ranging.
- **Sudut Pemindaian**: 360° Omnidirectional Scanning tanpa area buta (*blind spot*).
- **Jangkauan Pengukuran**: 
  - Jarak minimum: 0.1 meter.
  - Jarak maksimum: 13.4 meter (teruji pada objek putih maupun hitam dengan reflektifitas berbeda).
- **Frekuensi Sampling (Measurement Rate)**: 4.500 sampel per detik (4.5 kHz).
- **Kecepatan Pindai (Scan Rate)**: 7 – 15 Hz dapat diatur.
- **Resolusi Sudut**: 0.8°.
- **Akurasi Pengukuran**: ±20 mm (pada jarak 3 – 12 meter).
- **Sumber Cahaya Laser**: Laser semikonduktor inframerah 905 nm.
- **Toleransi Cahaya Lingkungan**: Mampu bekerja hingga 30.000 Lux (andal untuk kondisi luar maupun dalam ruangan).
- **Dimensi & Berat**: 37.7 x 37.5 x 33 mm; Berat ultra-ringan 40 gram.
- **Motor Pemutar**: Built-in brushless motor berdaya tahan tinggi dan hening.

### 5.6. Modul Suara AI (WonderEcho Pro AI Voice Box)
- **Fungsi Utama**: Speech-to-Text (STT), Text-to-Speech (TTS), voice broadcasting, dan kontrol suara offline.
- **Mikrofon & Audio**: Array mikrofon terintegrasi dengan peredam kebisingan dinamis (*noise reduction*) dan penangkapan suara jarak jauh (*far-field pickup*).
- **Kata Pemicu (Wake Word)**: Mendukung penggantian kata pemicu dalam bahasa Inggris dan Mandarin.
- **Antarmuka**: Terhubung ke Raspberry Pi 5 untuk menyalurkan perintah suara ke pipeline Large Language Model (ChatGPT).

### 5.7. Motor Penggerak & Encoder
- **Tipe Motor**:
  - Mecanum & Ackermann: DC Geared Motor model **JGA27-310R20** magnet permanen.
  - Tank: DC Geared Motor model **MC520** torsi tinggi.
- **Rasio Roda Gigi (Gearbox)**: 1:20 dengan gigi full-metal berkualitas tinggi.
- **Kecepatan**: 9.000 RPM (motor tanpa beban), 450 ± 10 RPM (setelah reduksi gearbox).
- **Torsi**: Torsi kerja 0.4 kg·cm, Torsi stall ≥ 1.0 kg·cm.
- **Encoder**: Encoder magnetik quadrature Hall 2-fase (Fase A dan Fase B) dengan 13 kutub magnetik (resolusi pembacaan kecepatan dan arah putaran yang presisi).
- **Perlindungan Mekanikal**: Dilengkapi *wrapped rear tail shell* pelindung sirkuit PCB encoder dan cincin magnetik dari debu dan benturan fisik.

### 5.8. Sistem Baterai & Daya
- **Tipe Baterai**: Lithium-Polymer (LiPo) 2S Pack (sel silinder berkualitas tinggi seri 18650).
- **Tegangan & Kapasitas**: 7.4 V, 2200 mAh, discharge rate 10C.
- **Maksimum Arus Pelepasan**: ≤ 10 A.
- **Sirkuit Proteksi (BMS)**: Perlindungan terintegrasi terhadap overcharge, over-discharge, overcurrent, dan hubungan arus pendek (*short circuit*).
- **Daya Tahan Operasional**: ± 60 menit waktu pemakaian aktif (tergantung beban motor dan komputasi visi).
- **Siklus Pakai**: Lebih dari 300 siklus pengisian penuh.
- **Konektor**: Soket SM dengan proteksi polaritas terbalik (*reverse polarity protection*).
- **Charger Bawaan**: Charger pintar khusus 8.4 V dengan indikator LED (Merah = Mengisi, Hijau = Penuh / Standby). Waktu pengisian dari tegangan 7.0V ke 8.4V adalah sekitar 1 jam.

### 5.9. Struktur Bodi & Kemasan
- **Material Rangka**: Paduan Aluminium Full Logam (Aviation-grade Aluminium Alloy) dengan pemrosesan CNC dan finishing *sandblasted anodized* tahan gores.
- **Dimensi Kemasan**: 43 x 23 x 21 cm.
- **Berat Total Pengiriman**: Sekitar 2.8 kg.

---

## 6. Arsitektur Perangkat Lunak & Sistem Operasi

LanderPi menggunakan arsitektur modular berlapis untuk menjamin kehandalan sistem dan kemudahan pengembangan sekunder (*secondary development*):

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Aplikasi Pengguna & Layanan Cerdas                   │
│  WonderPi App (iOS/Android) │ Wireless Gamepad │ ChatGPT Multimodal AI │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    Algoritma Otonom & Computer Vision                  │
│   YOLOv8 Deteksi Objek  │ MediaPipe Gestur │ OpenCV Pelacak Garis/Warna │
│   Nav2 Navigasi & Rute  │ Cartographer SLAM │ RTAB-VSLAM Depth 3D       │
│   MoveIt2 Kinematika    │ Gazebo Simulasi   │ RViz2 Visualisasi         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                  ROS 2 Humble Middleware (Docker ARM64)                │
│             Nodes, Topics, Services, Actions, URDF Robot Model         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│              Sistem Operasi Host: Raspberry Pi OS (Debian 12)          │
│                Kernel Linux 6.x ARMv8, VNC Remote, SSH, Wi-Fi          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Serial UART (115200 bps)
┌───────────────────────────────────▼────────────────────────────────────┐
│          Firmware Kontrol Bawah: RRC Lite (STM32F407 Keil C)           │
│        PID Closed-loop Motor Encoder │ Telemetri Servo HX-06L          │
│        Filter Data IMU QMI8658       │ Manajemen Daya & Buzzer         │
└────────────────────────────────────────────────────────────────────────┘
```

- **Sistem Operasi**: Raspberry Pi OS (64-bit ARMv8).
- **Container Environment**: Docker Container berbasis Ubuntu 22.04 LTS yang memuat **ROS 2 Humble Hawksbill**.
- **Bahasa Pemrograman yang Didukung**: **Python 3**, **C++**, **C** (firmware STM32), dan **JavaScript**.
- **Perpustakaan AI & Visi**: OpenCV, MediaPipe, Ultralytics YOLOv8, PyTorch, PySerial.
- **Protokol Komunikasi Internal**: Topic, Service, dan Action Client-Server standar ROS 2.

---

## 7. Fungsionalitas Algoritma & Pembelajaran Robotika

### 7.1. Navigasi & Pemetaan SLAM (Simultaneous Localization and Mapping)
- **2D LiDAR Mapping**: Menggunakan algoritma *Cartographer* atau *Gmapping* untuk menghasilkan peta grid 2D lingkungan sekitar dengan presisi tinggi.
- **3D Visual SLAM (RTAB-VSLAM)**: Menggabungkan data citra RGB, peta kedalaman inframerah, dan data orientasi IMU untuk membentuk peta 3D point cloud padat serta menghindari *odometry drift*.
- **Autonomous Navigation & Path Planning (Nav2)**: 
  - Penentuan rute global dan lokal secara dinamis menggunakan costmap berlapis.
  - Menghindari rintangan bergerak secara real-time (*dynamic obstacle avoidance*).
  - Navigasi satu titik (Fixed-Point) dan multi-titik (Waypoint Sequencing).
- **LiDAR Sentry & Guard**: Mode penjaga area di mana robot memantau sektor 360° dan memberikan alarm atau memutar bodi jika ada objek yang mendekat.
- **LiDAR Tracking**: Robot mengunci jarak terhadap suatu target dan mengikutinya secara otonom.

### 7.2. Manipulasi Lengan Robotik 6-DOF & "Eye-in-Hand"
- **Kinematika Maju & Balik (Forward & Inverse Kinematics)**: Menghitung posisi koordinat kartesius $(X, Y, Z)$ dan orientasi sudut dari keenam persendian servo.
- **Perencanaan Lintasan Bebas Tabrakan (MoveIt2)**: Menggunakan MoveIt2 untuk menghasilkan trayektori gerak lengan yang mulus tanpa menabrak bodi robot atau rintangan luar.
- **Vision-Guided Sorting (Eye-in-Hand)**: Kamera depth di gripper mendekati target secara bertahap, mengukur jarak koordinat 3D target, mengambil balok, dan memindahkannya ke wadah tujuan secara otonom.

### 7.3. Visi Komputer & Deep Learning
- **YOLOv8 Autonomous Driving**: Model deteksi objek saraf tiruan yang dilatih untuk mendeteksi rambu lalu lintas (belok kanan/kiri, stop, lampu merah/hijau, penyeberangan jalan). Robot secara otomatis mematuhi aturan rambu.
- **MediaPipe Human-Robot Interaction**:
  - *Hand Tracking & Gestures*: Mengendalikan arah gerak robot dengan gestur jari.
  - *Fingertip Trajectory*: Robot mengikuti pola lintasan yang digambar oleh ujung jari di depan kamera.
  - *Human Pose & Face Detection*: Mengikuti pergerakan tubuh dan wajah pengguna.
- **OpenCV Classical Vision**:
  - *Color Recognition & Tracking*: Pelacakan bola atau balok berwarna menggunakan ruang warna HSV dan algoritma kendali PID.
  - *Line Following / Autonomous Patrolling*: Robot menyusuri garis lajur berwarna di lantai secara mulus.
  - *QR Code Detection*: Membaca kode QR untuk memicu skenario tugas khusus.
  - *Augmented Reality (AR)*: Menampilkan objek grafis virtual 3D di atas marker tag dalam tangkapan video kamera.

### 7.4. Integrasi Multimodal Large Language Model (Embodied AI & ChatGPT)
*(Khusus untuk varian Advanced Kit dengan WonderEcho Pro)*
- **Voice-to-Action Semantics**: Pengguna berbicara secara natural (misal: *"LanderPi, cari apel di atas meja dan antarkan ke meja belajar"*).
- **LLM Reasoning & Decomposition**: ChatGPT menerjemahkan intensi bahasa ke dalam rantai tindakan logis (*action sequence*).
- **Persepsi & Eksekusi Terintegrasi**: Robot mengeksekusi urutan tugas ROS 2 secara bertahap:
  1. Menavigasi menuju lokasi target.
  2. Mengaktifkan kamera visi untuk mencari objek.
  3. Mengarahkan lengan robotik dan menjepit objek.
  4. Menavigasi kembali ke lokasi pengantaran dan meletakkan barang.
  5. Memberikan respons konfirmasi suara kepada pengguna melalui WonderEcho Pro.

### 7.5. Kendali Formasi Multi-Robot (Group Control / Swarm)
- Menggunakan arsitektur jaringan **Host-Slave**: Satu unit LanderPi bertindak sebagai pemimpin (*master*), dan unit LanderPi lainnya bertindak sebagai pengikut (*slaves*).
- Mendukung formasi baris, kolom, atau segitiga secara tersinkronisasi melalui pertukaran topik koordinat ROS 2 melalui Wi-Fi.

---

## 8. Metode Kontrol & Konektivitas

LanderPi menyediakan 4 opsi antarmuka kendali yang fleksibel:

1. **Aplikasi Seluler WonderPi (iOS & Android)**:
   - **Mode AP (Direct Hotspot)**: Robot memancarkan SSID mandiri berawalan `HW-xxxx` (Password bawaan: `hiwonder`). Tidak memerlukan router eksternal.
   - **Mode STA (LAN)**: Robot dan ponsel terhubung ke jaringan Wi-Fi lokal yang sama (mendukung frekuensi 2.4GHz dan 5GHz).
   - Fitur App: Kontrol joystick pergerakan chassis, slider kendali 6 servo lengan robotik, live video feed FPV, tombol fungsi AI (Line Follower, Tracking, Lidar Avoidance, Gestur Tangan).
2. **Wireless Gamepad Controller (PS2 Style)**:
   - Menggunakan dongle receiver USB 2.4GHz yang dipasang ke port USB Raspberry Pi.
   - Tombol Start untuk reset/koneksi, joystick kiri untuk translasi maju-mundur, joystick kanan untuk belok/strafe.
3. **PC Remote Desktop (VNC) & Terminal SSH**:
   - Akses antarmuka grafis (GUI) sistem operasi robot melalui VNC Viewer untuk menjalankan RViz2, MoveIt, atau browser.
   - Akses command line via SSH (`ssh pi@<IP_ROBOT>`) untuk debugging, kompilasi kode ROS 2, dan scripting.
4. **Perangkat Lunak PC & Kalibrasi Visual**:
   - Software PC khusus dari Hiwonder untuk pengujian individual motor, debugging bus servo, penyesuaian threshold warna, dan kalibrasi kinematika lengan.

---

## 9. Daftar Kelengkapan Isi Paket (Packing List)

Isi paket tergantung pada edisi kit yang dipilih:

### 9.1. Komponen Standar di Semua Kit (Shared Components):
- 1x Bodi Chassis Metal pilihan (Mecanum / Ackermann / Tank) beserta motor DC gear encoder.
- 1x Lengan Robotik 6-DOF terakit dengan 6 unit Smart Bus Servo HX-06L.
- 1x Papan Kontroler RRC Lite (STM32F407VET6) terpasang dengan sensor IMU QMI8658.
- 1x Sensor Aoride MS200 TOF LiDAR 360°.
- 1x Baterai Lithium-Polymer 7.4V 2200mAh 10C dengan kabel pelindung.
- 1x Dedicated Smart Charger 8.4V.
- 1x Wireless Gamepad Handle + USB Wireless Receiver 2.4GHz.
- 1x Set Blok Objek Berwarna & Kartu Proyek Visi.
- 1x Obeng & Set Baut / Mur / Aksesoris Perakitan Tambahan.
- Kabel penghubung motor, servo, dan jalur komunikasi serial.

### 9.2. Komponen Khusus per Varian Kit:
- **Starter Kit**: Disertai 1x Kamera Visi Monokuler USB HD.
- **Standard Kit**: Disertai 1x **Aurora930 Pro 3D Structured Light Depth Camera** beserta braket dudukan di end-effector lengan robot.
- **Advanced Kit**: Disertai 1x **Aurora930 Pro 3D Structured Light Depth Camera** dan 1x **WonderEcho Pro AI Voice Interaction Box** beserta kabel audio-USB.

*(Catatan: Unit Raspberry Pi 5 dan Kartu TF 64GB hanya disertakan apabila memilih opsi varian "With Raspberry Pi 5" pada saat pemesanan).*

---

## 10. Sumber Daya Pembelajaran & Tautan Referensi Resmi

Untuk mempelajari instalasi sistem, contoh kode sumber, dan dokumentasi API, rujuk tautan berikut:
- **Dokumentasi & Wiki Resmi**: [https://wiki.hiwonder.com/projects/LanderPi/en/latest/](https://wiki.hiwonder.com/projects/LanderPi/en/latest/)
- **Tutorial & Panduan Video Hiwonder**: [https://www.hiwonder.com.cn/store/learn/180.html](https://www.hiwonder.com.cn/store/learn/180.html)
- **Pusat Download Aplikasi & Software**: [https://www.hiwonder.net/app-software](https://www.hiwonder.net/app-software)
- **Repositori Resmi Hiwonder di GitHub**: [https://github.com/hiwonder](https://github.com/hiwonder)
- **Halaman Produk Hiwonder Global**: [https://www.hiwonder.com/products/landerpi](https://www.hiwonder.com/products/landerpi)
- **Halaman Produk OpenELAB**: [https://openelab.io/products/landerpi-robot-car](https://openelab.io/products/landerpi-robot-car)
