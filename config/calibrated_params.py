# -*- coding: utf-8 -*-
"""ค่าพารามิเตอร์ที่ผ่านการ calibrate (สร้างโดย 13_calibrate_params.py)
วิธีได้มา: beta = grid search เทียบ AADT 2565 (พิกัด v2, PCU แยกสาย)
trip rate/freight factor = least-squares scale ให้ k->1
ASC = iterative fit เข้าเป้า mode share ทางการปี 2565 (สนข./NAM + สัดส่วนตันสินค้า)
2-segment VOT: general 180 baht/hr (88%) + business 600 baht/hr (12%)"""
BETA_PAX = 0.0250      # R2=0.030 medGEH=56.1
BETA_FRG = 0.0080      # R2=-0.050 medGEH=87.9
TRIP_RATE_PAX = 0.0792 # จาก 2.0 x k_flow(0.03875)/fac_pax(0.9789)
FREIGHT_FACTOR = 0.1709
VOT_GEN, VOT_BIZ, BIZ_SHARE = 3.0000, 10.0000, 0.12
MC_MAX_MIN = 90
ASC_PAX = {'car': 0, 'motorcycle': 5, 'bus': 130.26, 'rail': 129.9, 'air': -287.11, 'water': 35, 'truck': 0}
ASC_FRG = {'car': 0, 'motorcycle': 5, 'bus': 25, 'rail': 480.4, 'air': 10, 'water': -44.95, 'truck': 0}
FAC_PAX_ROAD = 0.9789  # PCU ถนนต่อ trip ผู้โดยสาร (ทุกทริป)
FAC_FRG_ROAD = 1.7596
SHARE_PAX = {'car': 0.68896, 'motorcycle': 0.19398, 'bus': 0.09038, 'rail': 0.00822, 'air': 0.01338, 'water': 0.00508}  # สัดส่วนโหมดผู้โดยสาร (ทุกทริป)
SHARE_FRG = {'truck': 0.87978, 'rail': 0.01666, 'water': 0.10356}
