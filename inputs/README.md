# inputs/ — ข้อมูลนำเข้าของแบบจำลอง

โฟลเดอร์นี้คือ **ชั้น INPUT ชั้นเดียว** ของโปรเจกต์ ทุกอย่างในนี้ commit ลงรีโป และเป็นสิ่งเดียว
ที่ตั้งใจให้ "คน" แก้ — แก้แล้วเปิด PR เข้า `main` พอ merge ระบบจะรันแบบจำลองใหม่และอัปเดต
หน้าเว็บผลลัพธ์ให้เอง (ดู `.github/workflows/run_pipeline.yml`; `main` ป้องกันไว้ push ตรงไม่ได้
— ดู `../docs/BRANCH_PROTECTION.md`)

> ห้ามแก้ไฟล์ใน `data/`, `model/`, `output/`, `site/` ด้วยมือ — สคริปต์เป็นผู้สร้างและจะถูกเขียนทับ

## ผังไฟล์

| ไฟล์ / โฟลเดอร์ | คืออะไร | ใช้ในขั้น | แหล่งที่มา |
|---|---|---|---|
| `scenarios/base.yaml` | ชุดสมมติฐาน/พารามิเตอร์ของการรัน | 3–14 | กำหนดเอง |
| `calibration/aadt_2565.csv` | ปริมาณจราจร AADT ปี 2565 แยกชนิดรถ/สายทาง | 7a, 13 | กรมทางหลวง (data.go.th) — โหลดอัตโนมัติโดย `01_fetch_data.py` |
| `calibration/history/aadt_256[3-6].csv` | AADT ย้อนหลังสำหรับประมาณแนวโน้ม | `build_aadt_projection.py` | กรมทางหลวง |
| `calibration/targets/*.csv` | เป้าหมายสัดส่วนการเดินทาง/ขนส่งสินค้ารายโหมด | 13 | สนข./กระทรวงคมนาคม — โหลดอัตโนมัติ |
| `landuse/schools_pts.gpkg`, `schools_poly.gpkg` | ตำแหน่งสถานศึกษา (attraction ผู้โดยสาร) | 3, 8a | OSM |
| `landuse/industrial.gpkg` | พื้นที่อุตสาหกรรม (production/attraction สินค้า) | 3, 8a | OSM |
| `multimodal/rail_lines.gpkg`, `rail_stations.gpkg` | โครงข่ายและสถานีรถไฟ | 5a, 13, 14 | OSM |
| `multimodal/ports.gpkg`, `ferry_routes.gpkg` | ท่าเรือ/ท่าเทียบ และเส้นทางเรือโดยสาร | `build_water.py`, 14 | OSM |
| `multimodal/airports_pts.gpkg`, `airports_poly.gpkg` | สนามบิน | 14, 15 | OSM |
| `multimodal/openflights_airports.dat`, `openflights_routes.dat` | ข้อมูลสนามบิน/เส้นทางบิน | `build_air_network.py` | OpenFlights |

ไฟล์ที่ **สร้างจากของในนี้** จะไปอยู่ที่ `data/multimodal/` (`air_nodes`, `air_links`,
`seaport_nodes`, `water_freight_links`) และ `data/calibration/aadt_current.csv`

## วิธีแก้ที่พบบ่อย

**1. ปรับสมมติฐาน (ไม่ต้องแตะข้อมูลภูมิสารสนเทศ)**
แก้ `scenarios/base.yaml` เช่นเปลี่ยน `beta_pax` หรือ `eq_iter` → commit → push

**2. ลองหลายทางเลือกโดยไม่ทับของเดิม**
คัดลอกเป็น `scenarios/high_rail.yaml` → push → ไปที่แท็บ **Actions → Run transport model
pipeline → Run workflow** แล้วใส่ `scenario = high_rail`

**3. อัปเดตข้อมูล AADT เป็นปีใหม่**
วางไฟล์ปีใหม่ที่ `calibration/history/aadt_2567.csv` (คอลัมน์เหมือนไฟล์เดิม)
แล้วปรับ `model.aadt_year` ใน scenario ถ้าจะเปลี่ยนปีฐานเทียบ

**4. เพิ่ม/แก้โครงข่ายราง ท่าเรือ สนามบิน**
แก้ไฟล์ `.gpkg` ที่เกี่ยวข้องใน `multimodal/` (คงชื่อ layer และชื่อคอลัมน์เดิมไว้) แล้ว commit

ก่อน commit ตรวจได้ทันทีด้วย `python3 scripts/_check_inputs.py`
(ตัวเดียวกับที่ CI ใช้เป็นเงื่อนไข merge — จับ key ที่สะกดผิดและค่าที่หลุดช่วง)

รายละเอียดของทุก key ใน scenario อยู่ที่ [`../docs/PIPELINE_IO.md`](../docs/PIPELINE_IO.md)
