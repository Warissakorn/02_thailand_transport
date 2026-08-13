# แบบจำลองขนส่งหลายรูปแบบระดับประเทศ (Thailand Multimodal 4-Step Transport Model)

แบบจำลองการขนส่งและจราจรประเทศไทยตามกรอบ 4-step (trip generation → distribution →
mode choice → assignment) ครอบคลุม **ถนน · ราง · อากาศ · น้ำ** แยกผู้โดยสาร/สินค้า
หน่วยวิเคราะห์หลัก **928 อำเภอ** ปรับเทียบกับ **AADT กรมทางหลวง (project ปี 2569 จากแนวโน้ม 2563–2566)** และ
สถิติ mode share ทางการ (สนข.)

- ที่มาข้อมูลทุกชิ้น → [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)
- ระเบียบวิธี+สมการทุกขั้น → [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)
- ข้อจำกัด → [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)
- แนวทางพยากรณ์อนาคต 30 ปี + scenario + subarea → [`docs/FORECASTING_GUIDE.md`](docs/FORECASTING_GUIDE.md)
- ประวัติผลปรับเทียบทุก variant → [`docs/CALIBRATION.md`](docs/CALIBRATION.md)
- ตาราง/รูปพร้อมใส่รายงาน → `output/report/{tables,figures}/`

## โครงสร้างโปรเจกต์
```
02_thailand_transport/
├── thailand_transport.qgz      โปรเจกต์ QGIS (เลเยอร์จัดกลุ่มครบ)
├── config/
│   ├── model_params.py         พารามิเตอร์ตั้งต้น (v1, มีคำอธิบายทุกค่า)
│   ├── calibrated_params.py    ค่าที่ผ่านการ calibrate + วิธีได้มา (สร้างโดย script 13)
│   └── osmconf.ini             การสกัด tag จาก OSM pbf
├── data/
│   ├── raw/                    ข้อมูลดิบ (OSM pbf, WorldPop)
│   ├── boundaries/             GADM 4.1
│   ├── network/                โครงข่าย routable (ถนน/ราง/น้ำ)
│   ├── multimodal/             terminal + โครงข่ายอากาศ/เรือสินค้า
│   ├── zones_taz/              TAZ + centroid + access connectors
│   ├── landuse/                โรงเรียน/นิคม (trip gen)
│   └── calibration/            AADT 2565 + targets/ (สถิติ mode share ทางการ)
├── model/                      ผลลัพธ์ราย stage (1_trip_generation … 5_calibration)
├── scripts/                    pipeline ทั้งหมด (เรียงเลข) + lib/ + qpy.bat
├── docs/                       เอกสารอ้างอิงทั้งหมด
└── output/report/              ตาราง CSV + รูป 300dpi พร้อมใส่รายงาน
```

## Pipeline (ทำซ้ำได้ทุกขั้น)
รันทุกสคริปต์ผ่าน **`scripts\qpy.bat`** (ตั้ง environment QGIS headless):
```bat
cd projects\02_thailand_transport
scripts\qpy.bat scripts\01_fetch_data.py all     & REM ดาวน์โหลดข้อมูลทุกแหล่ง
scripts\qpy.bat scripts\02_prep_network_taz.py   & REM โครงข่ายถนน + TAZ จังหวัด
REM 03,04,04b,05a,05b : โมเดลระดับจังหวัด (trip gen -> gravity -> mode choice)
REM build_*.py        : โครงข่ายราง/น้ำ/อากาศ/เรือสินค้า + connectors + centroid ถ่วง ปชก.
scripts\qpy.bat scripts\build_aadt_projection.py & REM AADT ย้อนหลัง 2563-66 -> project ปีปัจจุบัน 2569 -> aadt_current.csv
scripts\qpy.bat scripts\07a_geolocate_aadt.py    & REM วางสถานี AADT (chainage v2) จาก aadt_current.csv
scripts\qpy.bat scripts\08a_district_prep.py     & REM TAZ อำเภอ 928 + trip gen
scripts\qpy.bat scripts\13_calibrate_params.py   & REM calibrate beta/scale/ASC  -> calibrated_params.py
scripts\qpy.bat scripts\14_final_assignment.py   & REM final: multi-path MSA (directed+BPR) -> assigned_final_dist (ขนานผ่าน lib/passign.py)
scripts\qpy.bat scripts\15_report_outputs.py     & REM ตาราง+รูปสำหรับรายงาน
REM 09a,09d,10a,10b,11 : เลเยอร์ประกอบใน .qgz (desire รายโหมด / sequence paths /
REM                      จราจรถนนรวม v1 จังหวัด+อำเภอ / flow components จังหวัด)
scripts\qpy.bat scripts\build_project.py         & REM ประกอบ .qgz
```
ลำดับเต็มและบทบาทของแต่ละสคริปต์ดูหัวไฟล์ (docstring). `scripts/lib/` = โค้ดใช้ร่วม
(`transport_graph.py` แกนกราฟ/assignment, `passign.py` assignment แบบขนาน). สคริปต์รุ่นก่อน
ที่ถูกแทนที่ (province equilibrium 06/06b/07b, district-v1 08b/09b/09c/12, render เดิม) อยู่ใน
`scripts/archive/` — เก็บไว้ทำซ้ำได้ ไม่อยู่ใน pipeline หลัก

## ผลลัพธ์หลัก (canonical)
| ไฟล์ | สาระ |
|------|------|
| `model/4_trip_assignment/assigned_final_dist.gpkg` | ปริมาณจราจรถนนรวม (PCU/วัน + peak + V/C) — directed, congestion-aware |
| `model/4_trip_assignment/flowf_*.gpkg` | 7 องค์ประกอบ (d2d/access-egress × คน/สินค้า) ผลรวม = ตัวรวม (additivity ตรวจแล้ว) |
| `model/5_calibration/calibration_report_final.txt` | GEH/R²/RMSE เทียบ AADT project 2569 (รวม/คน/สินค้า) |
| `model/5_calibration/scatter_final.csv` | ข้อมูล scatter จำลอง-vs-จริง รายสถานี (ทำกราฟในรายงาน) |
| `model/3_mode_choice/mode_share_calibrated.csv` | mode share โมเดล vs เป้าทางการ 2565 |

## สภาพแวดล้อม
QGIS 3.44.7 (มี numpy 1.26 / scipy 1.13 ในตัว) บน Windows · ไม่ต้องติดตั้งปลั๊กอินเพิ่ม
รายละเอียดซอฟต์แวร์และเวอร์ชันข้อมูล: `docs/DATA_SOURCES.md` §4
