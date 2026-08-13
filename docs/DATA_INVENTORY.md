# Data Inventory — ขั้นที่ 1 (ข้อมูลนำเข้า)

ดาวน์โหลดซ้ำได้ทั้งหมดด้วย `python scripts/01_fetch_data.py all`

| ไฟล์ | แหล่ง | ขนาด | ใช้ทำอะไร |
|------|------|------|-----------|
| `data/boundaries/gadm41_THA.gpkg` | GADM v4.1 | 102 MB | ขอบเขตปกครอง — ADM_1=77 จังหวัด, ADM_2=928 อำเภอ, ADM_3=5,926 ตำบล → ฐาน TAZ |
| `data/raw/thailand-latest.osm.pbf` | Geofabrik | 309 MB | layer `lines`=ถนน, `points`=โรงเรียน/POI, `multipolygons`=นิคม/landuse/ท่าเรือ |
| `data/raw/tha_pop_2020_100m.tif` | WorldPop 2020 constrained | 27.5 MB | ประชากร 100m (EPSG:4326, ค่า 0–3081/เซลล์) → zonal stats ต่อโซน (passenger gen) |
| `data/calibration/aadt_2565.csv` | กรมทางหลวง / data.go.th | 0.5 MB | AADT 2,701 สถานี แยก 13 ชนิดรถ + รวม + จังหวัด |
| `data/calibration/history/aadt_256{3,4,5,6}.csv` | DOH data.go.th / opendata.doh.go.th | 2 MB | AADT ย้อนหลัง 4 ปี (หา growth trend) — 2563 = cp874 |
| `data/calibration/aadt_current.csv` | project จาก 2566 | 0.5 MB | **เป้า calibration ปัจจุบัน = project ปี 2569** (×1.1421, growth 4.53%/ปี) โดย `build_aadt_projection.py` ; 07a/13 อ่านไฟล์นี้ |

## AADT — โครงสร้างคอลัมน์
`ทางหลวงสาย, ตอนควบคุม, ชื่อสายทาง, จุดสำรวจ (กม.+ม. เช่น 25+556),`
`รถยนต์นั่ง(≤7)(>7), รถโดยสาร(เล็ก/กลาง/ใหญ่), รถบรรทุก(4ล้อ/6ล้อ/10ล้อ/พ่วง/กึ่งพ่วง),`
`รวม, %ยานยนต์หนัก, จักรยาน, มอเตอร์ไซค์, แขวงทางหลวง, จังหวัด`

- **passenger** ≈ รถยนต์นั่ง + รถโดยสาร + มอเตอร์ไซค์ ; **freight** ≈ รถบรรทุกทุกประเภท
- ⚠️ **ไม่มี lat/lon** — สถานีอ้างอิงด้วย สาย+กม. → ต้อง linear-referencing กับโครงข่ายตอนขั้น 7
  (ระหว่างนี้ใช้ฟิลด์ `จังหวัด` calibrate ระดับจังหวัดได้)

## Multimodal — โครงข่ายโหมดอื่น (data/multimodal/, data/network/)
ทำเป็น multimodal model: ถนน + อากาศ + ราง + น้ำ แข่งกันในขั้น Mode Choice

| โหมด | ไฟล์ | จำนวน | แหล่ง |
|------|------|-------|-------|
| 🚆 ราง (เส้น) | `data/network/rail_clean.gpkg` | 5,371 | OSM `railway=rail/...` (clean, 32647, speed/travel_min) |
| 🚆 สถานีรถไฟ | `data/multimodal/rail_stations.gpkg` | 855 | OSM `railway=station/halt` |
| ✈️ สนามบิน (node) | `data/multimodal/air_nodes.gpkg` | 41 | OpenFlights (เชิงพาณิชย์ + IATA) |
| ✈️ เส้นทางบิน | `data/multimodal/air_links.gpkg` | 50 | OpenFlights routes (in-country, +dist_km/fly_min) |
| ✈️ สนามบิน OSM | `airports_poly.gpkg` 70 / `airports_pts.gpkg` 27 | | OSM `aeroway=aerodrome` (รวมเล็ก/ทหาร) |
| 🚢 เส้นทางเรือ | `data/multimodal/ferry_routes.gpkg` | 411 | OSM `route=ferry` |
| 🚢 ท่าเรือ/ท่าเทียบ | `data/multimodal/ports.gpkg` | 529 | OSM `man_made=pier`/`amenity=ferry_terminal` |

หมายเหตุ: เส้นทางบิน OpenFlights เป็นชุด static (อาจเก่า) — topology ใช้ได้, ปรับความถี่จริงภายหลังได้
สคริปต์: `build_air_network.py` (อากาศ), `build_multimodal.py` (รางclean + แผนที่รวม)

## โหมดในขั้น Mode Choice (ขั้น 5)
- **ผู้โดยสาร:** รถยนต์ · มอเตอร์ไซค์ · รถโดยสาร · **รถไฟ** · **เครื่องบิน** · (เรือ เฉพาะ OD ชายฝั่ง/เกาะ)
- **สินค้า:** รถบรรทุกเล็ก/หนัก · **รถไฟ** · **เรือ** (อากาศน้อยมาก)
- แต่ละโหมดมีต้นทุน = access(centroid→terminal) + in-vehicle time + egress; logit เลือกตามต้นทุนรวม
