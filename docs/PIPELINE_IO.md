# สัญญา Input → Process → Output

เอกสารนี้อธิบายว่า "อะไรคือข้อมูลนำเข้า อะไรคือกระบวนการ อะไรคือผลลัพธ์" เพื่อให้แก้ข้อมูล
นำเข้าและรันซ้ำได้โดยไม่ต้องอ่านโค้ดทั้งระบบ

## 1. สามชั้นของโปรเจกต์

| ชั้น | โฟลเดอร์ | commit | ใครเขียน | หมายเหตุ |
|---|---|---|---|---|
| **INPUT** | `inputs/` | ✅ | คน | ข้อมูลนำเข้า + scenario — แก้แล้ว push = รันใหม่ |
| **PROCESS** | `scripts/`, `config/` | ✅ | นักพัฒนา | โค้ดแบบจำลอง + ค่าตั้งต้น |
| ระหว่างทาง | `data/` (ยกเว้นที่ commit), `model/` | ❌ | สคริปต์ | ดาวน์โหลด/สร้างใหม่ได้เสมอ |
| **OUTPUT** | `output/report/`, `site/` | ✅ เฉพาะ report | สคริปต์ 15/16/17 | ตาราง CSV, แผนที่ PNG, เว็บผลลัพธ์ |

ทุกสคริปต์หา root ของโปรเจกต์ผ่าน `scripts/lib/paths.py` (อ่าน `TT_ROOT` ก่อน แล้วค่อยเดินขึ้นจาก
ตำแหน่งไฟล์) จึงรันได้ทั้งบน Windows (`scripts/qpy.bat`) และบน Linux/GitHub Actions

## 2. Scenario — ปุ่มหมุนของแบบจำลอง

ไฟล์: `inputs/scenarios/<ชื่อ>.yaml` เลือกด้วยตัวแปร `TT_SCENARIO` (ค่าเริ่มต้น `base`)
บน Actions เลือกได้จากช่อง **scenario** ตอนกด Run workflow

มี 3 หมวด เพราะบางชื่อซ้ำกันแต่คนละความหมาย:

### หมวด `model:` — ทับ `config/model_params.py`

| key | ความหมาย | ค่าตั้งต้น |
|---|---|---|
| `trip_rate_pax` | เที่ยว-ยานพาหนะ/คน/วัน (ค่าดิบก่อน calibrate) | 2.0 |
| `freight_factor` | เที่ยวสินค้า = ค่านี้ × เที่ยวผู้โดยสารรวม | 0.10 |
| `gravity_beta_pax` / `gravity_beta_frg` | ค่า deterrence เริ่มต้นของ gravity | 0.008 / 0.005 |
| `gravity_max_iter` / `gravity_tol` | เงื่อนไขหยุดของ Furness | 300 / 0.001 |
| `logit_theta` | ความไวต่อต้นทุนใน mode choice (1/นาที) | 0.020 |
| `vot_thb_per_min` | value of time (บาท/นาที) | 3.0 |
| `aadt_year` | ปี AADT ที่ใช้เทียบ (พ.ศ.) | 2565 |
| `geh_target` / `geh_pass_pct` | เกณฑ์ GEH และสัดส่วนที่ต้องผ่าน | 5.0 / 0.85 |

### หมวด `calibrated:` — ทับ `config/calibrated_params.py`

ปกติค่าเหล่านี้ `13_calibrate_params.py` เขียนให้เอง ใส่ที่นี่เมื่อต้องการ "ตรึง" ค่าไว้หรือทดลองด้วยมือ
(ค่าใน scenario จะทับผลของขั้น 13 ตอนที่ขั้น 14 อ่านไปใช้)

| key | ความหมาย |
|---|---|
| `trip_rate_pax` / `freight_factor` | ค่าหลัง scale เข้ากับ AADT |
| `beta_pax` / `beta_frg` | ค่า beta ที่เลือกจาก grid search |

### หมวด `run:` — สคริปต์ assignment อ่านตรง

| key | ความหมาย | ค่าตั้งต้น |
|---|---|---|
| `k_factor` | สัดส่วนปริมาณชั่วโมงเร่งด่วนต่อรายวัน | 0.09 |
| `eq_iter` | รอบ MSA equilibrium ต่อ component (ลดลง = เร็วขึ้น/หยาบขึ้น) | 8 |

ลบ key ใดออก = ใช้ค่าตั้งต้นของ key นั้น การพิมพ์ชื่อ key ผิดจะถูกข้าม (ไม่ทับค่าใด) —
ตรวจได้จากบรรทัด `scenario=...` ในขั้น *Show environment* ของ run และในหน้าเว็บผลลัพธ์

## 3. กระบวนการ (PROCESS)

ลำดับการรันเหมือนเดิมทุกประการ (ดู `README.md`) โดย workflow จัดกลุ่มเป็น step:

```
01 fetch → 02a สกัดถนนจาก OSM → 02b TAZ+ประชากร → 02 โครงข่ายสะอาด
→ build_* (centroid → ราง/น้ำ/อากาศ/เรือสินค้า → connectors)
→ 03,04,04b,05a,05b (จังหวัด) → build_aadt_projection, 07a
→ 08a, 13 calibrate, 14 assignment → 15 report → 09a,09d,10a,10b,11, build_project
→ 16 summary → 17 build site
```

`stages` ที่เลือกได้ตอนกดรัน: `smoke` (01+02), `fetch`, `network`, `full`

## 4. ผลลัพธ์ (OUTPUT) และการแสดงผลบน GitHub

1. **Job Summary** — สรุปในหน้ารันของ Actions ทันทีที่จบ (`scripts/16_summary.py`):
   สถานะแต่ละขั้น, R²/GEH, สัดส่วนรายโหมดเทียบเป้า, สถิติ assignment
2. **GitHub Pages** — เว็บผลลัพธ์เต็ม (`scripts/17_build_site.py` → `site/index.html`):
   ตาราง T1–T6 พร้อมปุ่มดาวน์โหลด CSV, แผนที่ F1–F6, scenario ที่ใช้, รายงาน calibration
   *ต้องเปิดครั้งเดียวที่ Settings → Pages → Source: **GitHub Actions***
3. **Artifact `model-outputs`** — `model/`, `output/report/`, log และ `.qgz` (เก็บ 7 วัน)

ทั้งสามอย่างสร้างด้วย `if: always()` จึงได้ผลแม้บางขั้นจะล้ม (ส่วนที่ยังไม่มีจะขึ้นว่า "ยังไม่มี")

## 5. วงจรการทำงานปกติ

```
แก้ inputs/  →  git commit + push (main)  →  Actions รันอัตโนมัติ
   →  ดู Job Summary  →  ดูเว็บผลลัพธ์บน Pages  →  ปรับ inputs/ ต่อ
```

อยากรันด้วยมือ/เลือก scenario อื่น: **Actions → Run transport model pipeline → Run workflow**
