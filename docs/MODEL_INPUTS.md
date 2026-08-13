# ทบทวนข้อมูลที่ต้องใช้ทั้งหมด — Multimodal 4-Step Model

สถานะ: ✅ พร้อม · ⚠️ มี แต่ต้องปรับ/เติม · ❌ ยังไม่ทำ (จะสร้างในขั้นถัดไป)
พารามิเตอร์ทั้งหมดรวมที่ [`config/model_params.py`](../config/model_params.py)

## A. ข้อมูลเชิงพื้นที่ (spatial inputs) — รวบรวมแล้ว

| # | ข้อมูล | ไฟล์ | สถานะ |
|---|--------|------|-------|
| 1 | ขอบเขต/โซน TAZ (77 จังหวัด) | `data/zones_taz/taz_provinces.gpkg` | ✅ |
| 2 | centroid **ถ่วงน้ำหนักประชากร** + snap | `taz_centroids_pw.gpkg` (canonical) | ✅ |
| 3 | ประชากร/โซน | `zone_population.gpkg` (WorldPop) | ✅ |
| 4 | สถานศึกษา (pax attraction) | `data/landuse/schools_*.gpkg` (17,970) | ✅ |
| 5 | นิคม/อุตสาหกรรม (freight gen) | `data/landuse/industrial.gpkg` (676 km²) | ✅ |
| 6 | โครงข่ายถนน | `data/network/network_clean.gpkg` (141k) | ✅ |
| 7 | โครงข่ายราง | `data/network/rail_clean.gpkg` (5,371) | ✅ |
| 8 | โครงข่ายอากาศ | `air_nodes.gpkg`(41) + `air_links.gpkg`(50) | ✅ |
| 9 | โครงข่ายน้ำ (ผู้โดยสาร/ferry) | `data/network/water_clean.gpkg` (411) | ✅ |
| 9b | โครงข่ายน้ำ-**สินค้า** (ท่าเรือใหญ่+ชายฝั่ง) | `seaport_nodes`(10)·`water_freight_links`(9) | ✅ |
| 10 | terminal: สถานีรถไฟ/สนามบิน/ท่าเรือ | `rail_stations`(855)·`air_nodes`(41)·`ports`(529) | ✅ |
| 11 | access/egress connector (โซน→terminal) | `access_{rail,air,water,seafreight}.gpkg` | ✅ |
| 12 | AADT ปรับเทียบ (2,701 สถานี) | `data/calibration/aadt_2565.csv` | ⚠️ ยังไม่ geolocate |

## B. ผลลัพธ์ที่โมเดลจะคำนวณ (จะสร้างในขั้นถัดไป)

| ขั้น | ผลลัพธ์ | สถานะ |
|------|---------|-------|
| 3 | Trip generation P/A (2 สาย) | ✅ `model/1_trip_generation/` |
| 4 | OD cost matrix (road) 77×77 | ✅ `od_cost_road.csv` (0 หลุด) |
| 4 | OD trip matrix (gravity) pax/freight | ✅ `od_passenger.csv`·`od_freight.csv` + desire lines |
| 5 | Mode split (door-to-door logit) | ✅ `mode_split_*.csv` (จยย42·รถ29·เมล์26·ราง3 / บรรทุก62·ราง36) |
| 6 | Assigned link volume (PCU) | ✅ `assigned_final_dist.gpkg` (อำเภอ 928, directed, congestion-aware, ขนานผ่าน `lib/passign.py`) |
| 7 | Calibration report (GEH) | ✅ `calibration_report_final.txt` — k=1.34, GEH<5=3.6%, R²=+0.108 (ดู docs/CALIBRATION.md, LIMITATIONS.md §4) |

## C. พารามิเตอร์ (ใน model_params.py) — กำหนดเป็น v1 แล้ว

| กลุ่ม | ตัวอย่างค่า | ปรับที่ |
|-------|------------|---------|
| trip rate / freight factor | 2.0 เที่ยว/คน/วัน · FF 0.10 | calibrate |
| ความเร็วโหมด | ถนนตามชั้น · ราง 80 · เรือ 30 · บิน 750 กม/ชม | คงที่ |
| access | 50 กม/ชม · detour 1.3 | คงที่ |
| gravity beta | pax 0.030 · freight 0.015 | calibrate |
| logit: VOT/ค่าโดยสาร/ASC/θ/transfer | VOT 80฿/ชม · θ 0.020 | calibrate |
| PCU | car 1.0 · จยย 0.33 · รถเมล์/บรรทุกใหญ่ 2.5 | คงที่ |

## D. ช่องว่าง/ข้อจำกัดที่ต้องรู้ (gaps)

1. **AADT ยังไม่มีพิกัด** — สถานีอ้างอิงด้วย สาย+กม. ต้อง linear-reference เข้าโครงข่ายถนนในขั้น 7 (ระหว่างนี้ calibrate ระดับจังหวัดด้วยฟิลด์ `จังหวัด` ได้)
2. ~~น้ำ-สินค้า~~ ✅ **แก้แล้ว** — สร้างโครงข่ายท่าเรือใหญ่ 10 แห่ง + เส้นทางเดินเรือชายฝั่ง 9 เส้น (`water_freight_links`) + `access_seafreight`
3. ~~centroid เรขาคณิต~~ ✅ **แก้แล้ว** — ใช้ centroid **ถ่วงน้ำหนักประชากร** (`taz_centroids_pw.gpkg`); access_air จังหวัดไกลลด 27→18
4. **การจ้างงาน** ใช้ proxy = ประชากร+สถานศึกษา (ไม่มีสำมะโนการจ้างงานรายจังหวัด) → attraction ผู้โดยสารโดยประมาณ
5. **fare/VOT/logit/beta เป็นค่าสมมติ** → ต้องปรับในขั้น 7 ให้ตรง AADT
6. **air-freight ไม่โมเดล** (สัดส่วนน้อยมากในไทย)
8. **Mode-share calibration** — logit ใช้ VOT เดียว → ✈️เครื่องบิน ~0% (ดีมานด์จริงมาจากกลุ่ม VOT สูง) และ🚆รางสินค้าสูงเกิน ต้องมี **ข้อมูล mode-share survey** หรือแยกกลุ่มผู้เดินทาง (AADT ปรับได้แค่ปริมาณถนนรวม)
7. **topology โครงข่าย** ยังไม่ตรวจ connectivity สำหรับ routing — ควรตรวจ/ซ่อมก่อนหา OD (segment หลุด/ไม่ต่อกันจะทำ Dijkstra ไม่ผ่านบางคู่)

## E. สรุปความพร้อม
- **ขั้น 1–3:** ✅ ครบ
- **ขั้น 4 (Distribution):** พร้อมเริ่ม — ต้องตรวจ topology ถนน/รางก่อน routing (ข้อ D7)
- **ขั้น 5 (Mode choice):** ข้อมูล+พารามิเตอร์พร้อม (ค่าเป็น v1)
- **ขั้น 7 (Calibration):** ต้อง geolocate AADT ก่อน (ข้อ D1)
