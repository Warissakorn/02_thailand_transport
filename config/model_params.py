# -*- coding: utf-8 -*-
"""พารามิเตอร์กลางของแบบจำลอง (single source of truth) — สคริปต์ทุกขั้นนำเข้าจากไฟล์นี้
ค่าทั้งหมดเป็น "ค่าตั้งต้น v1" ที่จะถูกปรับในขั้น 7 (calibration กับ AADT)
หน่วย: เวลา=นาที, ระยะ=กม., ความเร็ว=กม./ชม., เงิน=บาท
"""

# ── CRS ───────────────────────────────────────────────
CRS_DATA   = "EPSG:4326"   # เก็บข้อมูลดิบ
CRS_METRIC = "EPSG:32647"  # คำนวณระยะ/เครือข่าย (UTM 47N)

# ── ขั้น 3: Trip Generation ───────────────────────────
TRIP_RATE_PAX = 2.0    # เที่ยว-ยานพาหนะ/คน/วัน (ผู้โดยสาร)
FREIGHT_FACTOR = 0.10  # เที่ยวสินค้า = FF × เที่ยวผู้โดยสารรวม
# น้ำหนัก attraction/production (รวม=1 ต่อชุด)
W_PAX_ATTR  = {'pop': 0.7, 'school': 0.3}
W_FRG_PROD  = {'ind': 0.8, 'pop': 0.2}   # ผลิตสินค้า = อุตสาหกรรมนำ
W_FRG_ATTR  = {'ind': 0.5, 'pop': 0.5}   # ดึงดูดสินค้า = บริโภคนำ

# ── ขั้น 2: ความเร็วโครงข่าย (กม./ชม.) ────────────────
SPEED_ROAD_DEFAULT = {  # ใช้เมื่อไม่มี maxspeed (ดู 02_prep_network_taz.py)
    'motorway':110,'trunk':90,'primary':80,'secondary':70,'tertiary':60,
    'unclassified':50,'residential':40,'living_street':20,'road':50}
SPEED_RAIL = {'rail':80,'light_rail':40,'narrow_gauge':60}
SPEED_BOAT = 30.0
AIR_CRUISE_KMH = 750.0
AIR_TERMINAL_MIN = 30.0   # เวลาขึ้น-ลง/taxi ต่อเที่ยวบิน

# ── access/egress (โซน → terminal โดยรถยนต์) ──────────
ACCESS_KMH   = 50.0
ACCESS_DETOUR = 1.3       # ตัวคูณระยะตรง→ระยะถนนจริง

# ── ขั้น 4: Distribution (gravity, exp deterrence) ────
# f(c) = exp(-beta × cost_min)
GRAVITY_BETA_PAX = 0.008   # ระดับประเทศ: ทริปลดครึ่งทุก ~87 นาที (ปรับในขั้น 7)
GRAVITY_BETA_FRG = 0.005   # สินค้าเดินทางไกลกว่า
GRAVITY_MAX_ITER = 300    # Furness balancing
GRAVITY_TOL = 1e-3

# ── ขั้น 5: Mode Choice (multinomial logit) ───────────
# generalized cost (นาที-เทียบเท่า) = IVT + access + egress + transfer + fare/VOT
VOT_THB_PER_MIN = 180.0/60.0  # value of time 180 บาท/ชม. (เดินทางไกล; ปรับในขั้น 7)
# ค่าโดยสาร/ต้นทุน out-of-pocket
FARE = {  # บาท/คน: ('fixed', 'per_km') — รถยนต์/จยย. หารจำนวนผู้โดยสารแล้ว
    'car':        (0.0, 1.5),   # ค่าน้ำมันหารผู้โดยสาร ~2 คน
    'motorcycle': (0.0, 1.0),
    'bus':        (0.0, 0.5),
    'rail':       (0.0, 1.0),
    'air':        (1200.0, 3.0),
    'water':      (0.0, 1.5),
    'truck':      (0.0, 4.0),   # ขนส่งสินค้าทางถนน (ต่อเที่ยว/หน่วย)
}
# transfer/รอ-เปลี่ยนโหมด (นาที-เทียบเท่า)
TRANSFER_MIN = {'car':0,'motorcycle':0,'bus':10,'rail':20,'air':45,'water':20,'truck':0}
# ASC (alternative specific constant, นาที-เทียบเท่า; penalty โหมดสาธารณะ; ปรับในขั้น 7)
ASC = {'car':0,'motorcycle':5,'bus':25,'rail':20,'air':10,'water':35,'truck':0}
# ตัวคูณ IVT ต่อโหมด (เทียบเวลา routing ถนน)
IVT_FACTOR = {'car':1.0,'motorcycle':1.0,'bus':1.15,'truck':1.2}
LOGIT_THETA = 0.020       # ความไวต่อต้นทุน (1/นาที); ปรับในขั้น 7
# โหมดที่ใช้ได้ต่อสาย
MODES_PAX = ['car','motorcycle','bus','rail','air','water']
MODES_FRG = ['truck','rail','water']   # truck แตกเป็นเล็ก/ใหญ่ตอน assignment
# ความเร็วเฉลี่ยประมาณระยะทางจากเวลา (สำหรับคิดค่าโดยสารต่อ กม.)
NOMINAL_KMH = {'road':65,'rail':70,'water':25}

# ── ขั้น 6: Assignment (PCU) ──────────────────────────
PCU = {'car':1.0,'motorcycle':0.33,'bus':2.5,
       'truck_small':1.5,'truck_large':2.5,'rail':0,'air':0,'water':0}  # ราง/บิน/น้ำ ไม่ลงถนน

# ── ขั้น 7: Calibration ───────────────────────────────
AADT_YEAR = 2565
GEH_TARGET = 5.0
GEH_PASS_PCT = 0.85       # ต้องผ่าน GEH<5 อย่างน้อย 85% ของ link ที่มีสถานี
