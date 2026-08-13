# ที่มาของข้อมูล (Data Sources & Provenance)

เอกสารอ้างอิงข้อมูล**ทุกชิ้น**ที่ใช้ในแบบจำลองขนส่งหลายรูปแบบระดับประเทศ (multimodal 4-step model)
สำหรับใช้อ้างอิงในรายงานวิชาการ — ทุกชุดข้อมูลดาวน์โหลดซ้ำได้ด้วย `scripts/01_fetch_data.py`

> หมายเหตุปี: AADT ใช้ปี พ.ศ. 2565 (ค.ศ. 2022) · ประชากร ค.ศ. 2020 · OSM สกัด มิ.ย. 2026
> ความต่างช่วงเวลาของข้อมูล (temporal mismatch) ระบุไว้ใน `LIMITATIONS.md`

---

## 1. ข้อมูลปฐมภูมิ (Primary datasets)

### 1.1 ขอบเขตการปกครอง — GADM v4.1
| รายการ | รายละเอียด |
|--------|-----------|
| ชุดข้อมูล | GADM database of Global Administrative Areas, version 4.1 — Thailand |
| ผู้ผลิต | GADM (gadm.org) |
| URL ดาวน์โหลดตรง | https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_THA.gpkg |
| รุ่น/ปี | v4.1 (เผยแพร่ ค.ศ. 2022) |
| วันที่เข้าถึง | 23 มิถุนายน 2026 |
| สัญญาอนุญาต | ใช้ได้เสรีเพื่อการศึกษา/ไม่ใช่เชิงพาณิชย์ (ห้ามเผยแพร่ซ้ำ — ดู gadm.org/license) |
| ไฟล์ในโปรเจกต์ | `data/boundaries/gadm41_THA.gpkg` (101.7 MB) |
| เนื้อหาที่ใช้ | ADM_1 = 77 จังหวัด (TAZ หลัก), ADM_2 = 928 อำเภอ (TAZ ละเอียด), ADM_3 = 5,926 ตำบล (สำรอง) |
| การประมวลผล | reproject → EPSG:32647, เพิ่ม zone_id/district_id (`02_prep_network_taz.py`, `08a_district_prep.py`) |
| ข้อควรระวัง | ฟิลด์ชื่อไทย `NL_NAME_1` บางจังหวัดสะกดเป็น "อำเภอเมือง<จังหวัด>" — โค้ด normalize แล้ว (`07a_geolocate_aadt.py`) |

**อ้างอิง:** GADM (2022). *GADM database of Global Administrative Areas, version 4.1.* URL: https://gadm.org

### 1.2 โครงข่ายคมนาคมและสถานที่ — OpenStreetMap (ผ่าน Geofabrik)
| รายการ | รายละเอียด |
|--------|-----------|
| ชุดข้อมูล | OpenStreetMap extract ประเทศไทย (`thailand-latest.osm.pbf`) |
| ผู้ผลิต | อาสาสมัคร OpenStreetMap; ตัดข้อมูลรายประเทศโดย Geofabrik GmbH |
| URL ดาวน์โหลดตรง | https://download.geofabrik.de/asia/thailand-latest.osm.pbf |
| รุ่น/ปี | daily extract ณ วันดาวน์โหลด (ข้อมูล ณ ~22 มิ.ย. 2026) |
| วันที่เข้าถึง | 23 มิถุนายน 2026 (ถนน) · 24 มิถุนายน 2026 (ราง/อากาศ/น้ำ/โรงเรียน/นิคม) |
| สัญญาอนุญาต | Open Database License (ODbL) 1.0 — ต้องระบุ "© OpenStreetMap contributors" |
| ไฟล์ในโปรเจกต์ | `data/raw/thailand-latest.osm.pbf` (308.7 MB) |
| การประมวลผล | สกัดด้วย GDAL/ogr2ogr + `config/osmconf.ini` (เพิ่ม tag: oneway, maxspeed, ref, lanes, railway, aeroway, amenity, landuse, route) |

ชั้นข้อมูลที่สกัดจาก OSM (ตัวกรอง → ไฟล์):
| ชั้นข้อมูล | ตัวกรอง OSM | ไฟล์ | จำนวน |
|-----------|------------|------|-------|
| ถนนทั้งหมด | `highway IN (motorway..residential,living_street,road)` | `data/network/roads_raw_4326.gpkg` | 1,611,398 เส้น |
| ถนนสายหลัก (โมเดล) | tertiary ขึ้นไป + links | `data/network/network_clean.gpkg` | 141,469 เส้น / 158,104 กม. |
| ทางรถไฟ | `railway IN (rail,light_rail,narrow_gauge)` | `data/multimodal/rail_lines.gpkg` → `data/network/rail_clean.gpkg` | 5,371 เส้น |
| สถานีรถไฟ | `railway IN (station,halt)` | `data/multimodal/rail_stations.gpkg` | 855 จุด |
| สนามบิน (พื้นที่/จุด) | `aeroway='aerodrome'` | `airports_poly.gpkg` / `airports_pts.gpkg` | 70 / 27 |
| เส้นทางเรือ ferry | `route='ferry'` | `ferry_routes.gpkg` → `data/network/water_clean.gpkg` | 411 เส้น / 6,507 กม. |
| ท่าเรือ/ท่าเทียบ | `man_made='pier'` OR `amenity='ferry_terminal'` | `data/multimodal/ports.gpkg` | 529 จุด |
| สถานศึกษา | `amenity IN (school,university,college)` | `schools_poly.gpkg` + `schools_pts.gpkg` | 17,970 แห่ง (รวม) |
| พื้นที่อุตสาหกรรม | `landuse IN (industrial,port)` | `data/landuse/industrial.gpkg` | 675.8 ตร.กม. |

**อ้างอิง:** OpenStreetMap contributors (2026). *OpenStreetMap Thailand extract.* สกัดโดย Geofabrik GmbH. URL: https://download.geofabrik.de/asia/thailand.html (ODbL 1.0)

### 1.3 ประชากรเชิงพื้นที่ — WorldPop 2020 (constrained, 100 m)
| รายการ | รายละเอียด |
|--------|-----------|
| ชุดข้อมูล | Thailand population 2020, constrained individual countries (BSGM), 100 m |
| ผู้ผลิต | WorldPop, School of Geography and Environmental Science, University of Southampton |
| URL ดาวน์โหลดตรง | https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/THA/tha_ppp_2020_constrained.tif |
| รุ่น/ปี | ค.ศ. 2020 |
| วันที่เข้าถึง | 23 มิถุนายน 2026 |
| สัญญาอนุญาต | CC BY 4.0 |
| ไฟล์ในโปรเจกต์ | `data/raw/tha_pop_2020_100m.tif` (27.5 MB, 9952×17816, EPSG:4326) |
| ผลรวมทั้งประเทศ | 74,992,832 คน (ผลรวม raster — WorldPop ปรับเข้าค่าประมาณ UN) |
| การประมวลผล | zonal sum ต่อจังหวัด/อำเภอ (`zone_population.gpkg`, `district_tripgen.csv`) และ centroid ถ่วงน้ำหนักประชากร (`build_popweighted_centroids.py`, `08a_district_prep.py`) |

**อ้างอิง:** WorldPop (2020). *Thailand population 2020, constrained individual countries dataset (100 m).* University of Southampton. URL: https://www.worldpop.org (CC BY 4.0; DOI ระบุบนหน้า dataset)

### 1.4 ปริมาณจราจร AADT — กรมทางหลวง (พ.ศ. 2565)
| รายการ | รายละเอียด |
|--------|-----------|
| ชุดข้อมูล | ปริมาณจราจรบนทางหลวง ปี 2565 (Annual Average Daily Traffic) |
| ผู้ผลิต | กรมทางหลวง กระทรวงคมนาคม |
| พอร์ทัล | ศูนย์กลางข้อมูลเปิดภาครัฐ data.go.th — ชุดข้อมูล `addt2565` |
| หน้า dataset | https://data.go.th/dataset/addt2565 |
| URL ดาวน์โหลดตรง | https://data.go.th/dataset/0ed9305b-0752-4189-bd89-0dfa96e6f992/resource/6cfd40db-807d-4169-9b0d-879bd94b88e3/download/65.csv |
| รุ่น/ปี | พ.ศ. 2565 (ค.ศ. 2022) |
| วันที่เข้าถึง | 23 มิถุนายน 2026 |
| สัญญาอนุญาต | Open Government License – Thailand |
| ไฟล์ในโปรเจกต์ | `data/calibration/aadt_2565.csv` (2,701 สถานีสำรวจ) |
| โครงสร้าง | ทางหลวงสาย/ตอนควบคุม/จุดสำรวจ(กม.+ม.)/ปริมาณแยก 13 ชนิดรถ/รวม/แขวง/จังหวัด — **ไม่มีพิกัด lat-lon** |
| การประมวลผล | geolocate ด้วยเลขสาย (ref) + สัดส่วน กม. ในจังหวัด (`07a_geolocate_aadt.py` → `aadt_points.gpkg`, วางได้ 2,646/2,701 = 98%) — เป็นการประมาณ; ดู LIMITATIONS |

**อ้างอิง:** กรมทางหลวง (2565). *ปริมาณจราจรบนทางหลวง ปี 2565.* ศูนย์กลางข้อมูลเปิดภาครัฐ. URL: https://data.go.th/dataset/addt2565 (เข้าถึง 23 มิ.ย. 2026)

### 1.5 เส้นทางบินภายในประเทศ — OpenFlights
| รายการ | รายละเอียด |
|--------|-----------|
| ชุดข้อมูล | OpenFlights airports & routes databases |
| ผู้ผลิต | OpenFlights.org (Jani Patokallio และผู้ร่วมพัฒนา) |
| URL ดาวน์โหลดตรง | https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat · .../routes.dat |
| วันที่เข้าถึง | 24 มิถุนายน 2026 |
| สัญญาอนุญาต | Open Database License (ODbL) 1.0 |
| ไฟล์ในโปรเจกต์ | `data/multimodal/openflights_airports.dat`, `openflights_routes.dat` |
| เนื้อหาที่ใช้ | สนามบินไทยมี IATA 41 แห่ง; คู่เส้นทางบินในประเทศ 50 คู่ (ไม่มีทิศ) |
| **ข้อจำกัดสำคัญ** | ฐานข้อมูล routes **หยุดปรับปรุงราว ค.ศ. 2014** — โครงข่าย (topology) ใช้ได้ แต่ไม่มีความถี่เที่ยวบิน/สายการบินปัจจุบัน |
| การประมวลผล | สร้าง node/link + ระยะ great-circle + เวลาบิน = 30 นาที (ภาคพื้น) + ระยะ/750 กม./ชม. (`build_air_network.py` → `air_nodes.gpkg`, `air_links.gpkg`) |

**อ้างอิง:** OpenFlights.org (2014/2026). *Airport and route databases.* URL: https://openflights.org/data (ODbL 1.0; เข้าถึง 24 มิ.ย. 2026)

### 1.6 ท่าเรือพาณิชย์หลักและเส้นทางเดินเรือชายฝั่ง — ผู้ศึกษากำหนดเอง (author-constructed)
| รายการ | รายละเอียด |
|--------|-----------|
| ชุดข้อมูล | ท่าเรือใหญ่ 10 แห่ง + เส้นทางเดินเรือชายฝั่ง 9 เส้น |
| ที่มา | พิกัดกำหนดโดยผู้ศึกษาจากตำแหน่งท่าเรือสาธารณะที่ทราบทั่วไป: กรุงเทพ (คลองเตย), ศรีราชา, แหลมฉบัง, สัตหีบ, มาบตาพุด, ชุมพร, สุราษฎร์ธานี (บ้านดอน), สงขลา, ระนอง, ภูเก็ต |
| สมมติฐาน | ความเร็วเรือชายฝั่ง 25 กม./ชม.; เส้นทางเชื่อมอ่าวไทย 8 เส้น + อันดามัน 1 เส้น |
| ไฟล์ | `data/multimodal/seaport_nodes.gpkg`, `water_freight_links.gpkg` (สร้างโดย `build_water_freight.py`) |
| หมายเหตุการอ้างอิง | ระบุในรายงานเป็น "โครงข่ายสมมุติที่ผู้ศึกษากำหนดจากตำแหน่งท่าเรือจริง" — ไม่ใช่ข้อมูลทางการ |

---

## 2. ข้อมูลที่สร้างขึ้น (Derived datasets)

ทุกไฟล์สร้างซ้ำได้จากข้อมูลปฐมภูมิ + สคริปต์ (ลำดับ pipeline ดู `README.md`)

| ไฟล์ | สร้างโดย | อินพุต | สาระ |
|------|---------|--------|------|
| `data/zones_taz/taz_provinces.gpkg` | 02 | GADM ADM_1 | TAZ 77 จังหวัด (32647) + zone_id, area_km2 |
| `data/zones_taz/district_taz.gpkg` | 08a | GADM ADM_2 | TAZ 928 อำเภอ + district_id |
| `data/zones_taz/taz_centroids_pw.gpkg` | build_popweighted_centroids | GADM + WorldPop + ถนน | centroid ถ่วงประชากร snap เข้าโครงข่าย (จังหวัด) |
| `data/zones_taz/district_centroids.gpkg` | 08a | เดียวกัน | centroid ถ่วงประชากร (อำเภอ) |
| `data/zones_taz/zone_population.gpkg` | (QGIS zonal) | GADM + WorldPop | ประชากรต่อจังหวัด |
| `data/zones_taz/access_{rail,air,water,seafreight}.gpkg` | build_connectors, build_water_freight | centroid + terminal | เส้น access โซน→terminal + access_min (50 กม./ชม., detour 1.3) |
| `data/network/network_clean.gpkg` | 02 | OSM | ถนนสายหลัก + speed_kmh/travel_min/capacity/oneway_i |
| `data/network/rail_clean.gpkg` | build_multimodal | OSM | ราง + ความเร็วตามประเภท (rail 80, light_rail 40, narrow_gauge 60 กม./ชม.) |
| `data/network/water_clean.gpkg` | build_water | OSM ferry | เส้นเรือ + เวลา (30 กม./ชม.) |
| `model/1_trip_generation/*` | 03, 08a | ประชากร/โรงเรียน/นิคม | P/A ผู้โดยสาร+สินค้า (จังหวัด gpkg / อำเภอ csv) |
| `model/2_trip_distribution/od_cost_*.csv` | 04, 08b | โครงข่าย+centroid | เวลาเดินทางระหว่างโซน (Dijkstra) |
| `model/2_trip_distribution/od_{passenger,freight}.csv` | 04b | P/A + cost | OD trips (doubly-constrained gravity) |
| `model/3_mode_choice/linehaul_{rail,water}.csv` | 05a | โครงข่ายราง/น้ำ | เวลา terminal→terminal |
| `model/3_mode_choice/mode_split_*.csv`, `mode_share_*.csv` | 05b | OD + GC ทุกโหมด | ผลแบ่งโหมด (MNL logit) |
| `model/3_mode_choice/desire_*.gpkg` | 09a, build_desire_lines | mode_split/OD | desire lines รวม + รายโหมด |
| `model/4_trip_assignment/assigned_road_total_{prov,dist}.gpkg` | 10a, 10b | mode_split + โครงข่าย | จราจรถนนรวม (door-to-door + access/egress) |
| `model/4_trip_assignment/flow*_​*.gpkg` | 11, 12 | เดียวกัน | flow components แยกโหมด×สาย (ผลรวม=ตัวรวม ตรวจแล้ว diff 0.0000%) |
| `model/4_trip_assignment/seq_*.gpkg` | 09d | mode_split + โครงข่าย | sequence paths (access→line-haul→egress) |
| `model/5_calibration/aadt_points.gpkg` | 07a | AADT + โครงข่าย | สถานี AADT วางบนโครงข่าย (ประมาณ) |
| `model/5_calibration/aadt_compare_*.gpkg`, `calibration_report_*.txt` | 07b | โมเดล + AADT | ผลเทียบ GEH/R²/RMSE รายสถานี |

## 3. พารามิเตอร์แบบจำลอง

รวมศูนย์ที่ `config/model_params.py` — ทุกค่า version-controlled พร้อม comment ที่มา
(ค่าที่ผ่านการ calibrate จะระบุวิธีได้มา; ค่าสมมติจะระบุว่าเป็นสมมติฐานพร้อมเหตุผล)
หมวดหลัก: trip rate, สัดส่วน attraction, ความเร็วรายโหมด, gravity β, VOT/ค่าโดยสาร/ASC/θ (logit),
PCU, BPR α-β, K-factor, เกณฑ์ GEH

## 4. ซอฟต์แวร์

| ซอฟต์แวร์ | รุ่น | ใช้ทำ |
|-----------|-----|-------|
| QGIS | 3.44.7 "Solothurn" | ประมวลผลเชิงพื้นที่, PyQGIS headless, แผนที่ |
| GDAL/OGR | 3.12.1 | สกัด OSM pbf, rasterize |
| Python (ใน QGIS) | 3.12 + numpy 1.26.4, scipy 1.13.0 | กราฟ/Dijkstra/gravity/logit/assignment |
| แหล่งโค้ด | `scripts/` ทั้งหมดในโปรเจกต์ | pipeline ทำซ้ำได้ทุกขั้น |

---

## 5. ข้อมูลเป้าหมายการปรับเทียบ (Calibration targets — สถิติทางการ)

### 5.1 ปริมาณการขนส่งสินค้าภายในประเทศ จำแนกตามรูปแบบการขนส่ง พ.ศ. 2560–2565
| รายการ | รายละเอียด |
|--------|-----------|
| ผู้ผลิต | สำนักงานนโยบายและแผนการขนส่งและจราจร (สนข.) กระทรวงคมนาคม |
| พอร์ทัล | MOT Data Catalog (ชุดข้อมูล `dataset_12_031`) / otp.gdcatalog.go.th |
| URL ดาวน์โหลดตรง | https://otp.gdcatalog.go.th/dataset/8d7f86ef-a6e2-4dcd-b227-02b87fedce0c/resource/8f792f68-d194-479d-9f95-ccfbc934dbe8/download/dataset_12_03-2560-2565.csv |
| วันที่เข้าถึง | 2 กรกฎาคม 2026 |
| สัญญาอนุญาต | Open Government License – Thailand |
| ไฟล์ | `data/calibration/targets/freight_by_mode_2560_2565.csv` |
| สาระ (ปี 2560 เป็นตัวอย่าง) | สัดส่วนตัน-สินค้าในประเทศ: ถนน 87.99% · ราง 1.37% · น้ำ 10.62% · อากาศ 0.02% |
| ใช้ทำ | เป้า calibrate mode share ฝั่งสินค้า (ขั้น Mode Choice) |

### 5.2 สัดส่วนการเดินทางระหว่างเมืองจำแนกตามรูปแบบ (สนข. — แบบจำลอง NAM ปีฐาน 2560)
| รายการ | รายละเอียด |
|--------|-----------|
| ผู้ผลิต | สนข. (แบบจำลอง NAM) ร่วมด้วยข้อมูล รฟท. / ทอท. / กรมท่าอากาศยาน |
| พอร์ทัล | MOT Data Catalog (ชุดข้อมูล `otp_65_03`) |
| URL ดาวน์โหลดตรง | https://otp.gdcatalog.go.th/dataset/12eb6ec3-659a-42d0-b5e4-b94e9ab660f4/resource/af3886c8-eafa-430a-aaed-1af32f2c1eb1/download/otp_65_03.csv |
| วันที่เข้าถึง | 2 กรกฎาคม 2026 |
| สัญญาอนุญาต | Open Government License – Thailand |
| ไฟล์ | `data/calibration/targets/intercity_pt_share_otp6503.csv` |
| สาระ (ปี 2560, ล้านคน-เที่ยว/ปี) | รถยนต์ส่วนบุคคล 552.8 (55.45%) · รถโดยสารระหว่างเมือง 371.2 (37.23%) · รถไฟ 34.95 (3.51%) · เครื่องบิน 38.0 (3.81%) |
| ใช้ทำ | เป้า calibrate mode share ผู้โดยสาร**ระหว่างเมือง** (interzonal) — แก้จุดอ่อนโหมดอากาศ |

### 5.3 ปริมาณผู้โดยสารขนส่งสาธารณะภายในประเทศ รายโหมด (ค.ศ. 2013–)
| รายการ | รายละเอียด |
|--------|-----------|
| ผู้ผลิต | กระทรวงคมนาคม |
| URL ดาวน์โหลดตรง | https://datagov.mot.go.th/dataset/8a3b54cd-791e-461f-b3ec-50581c92ab52/resource/e0a4e2c5-17ad-4f09-a6e2-619f20587a85/download/domestic-passenger.csv |
| วันที่เข้าถึง | 2 กรกฎาคม 2026 · สัญญาอนุญาต Open Government License – Thailand |
| ไฟล์ | `data/calibration/targets/passenger_domestic_by_mode.csv` |
| ใช้ทำ | ตรวจสอบข้าม (cross-check) แนวโน้มผู้โดยสารราง/น้ำ/อากาศ |

### 5.4 โครงข่ายทางหลวง GIS ทางการ — พบแต่**ใช้ไม่ได้** (บันทึกข้อเท็จจริง)
ตรวจสอบเมื่อ 2 ก.ค. 2026: เซิร์ฟเวอร์ GIS กรมทางหลวง `gisweb.doh.go.th/arcgis/rest/services`
ออนไลน์และมี service `km` (หลักกิโลเมตร) และ `fgdsNetwork` (โครงข่าย) แต่ทุก service ตอบ
HTTP 503 (ArcGIS Server 9.31 — instance ไม่ทำงาน); ชุด `transportgis` บน data.go.th ตอบ 403;
HRIS (hris.doh.go.th) เป็นเว็บแอปไม่มี API เปิด → จึงใช้วิธี linear-referencing บนเส้น OSM
ตามเลขสายทาง (ref) + ค่า กม. ของสถานี (วิธี v2, ดู `07a`) และระบุความคลาดเคลื่อนใน LIMITATIONS

## 6. แหล่งที่ค้นหาแล้วไม่ได้ใช้ (บันทึกเพื่อความครบถ้วน)
- โครงข่ายทางหลวงชนบท (DRR FeatureServer `gis.drr.go.th`) — เป็นถนน ทช. ไม่ใช่ ทล. ที่มีสถานี AADT
- ข้อมูลจดทะเบียนยานพาหนะ (กรมการขนส่งทางบก) — ไม่จำเป็นหลังใช้ k→1 calibration กับ AADT โดยตรง
