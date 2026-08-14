# -*- coding: utf-8 -*-
"""boundaries — เลือกแหล่งขอบเขตการปกครอง: GADM (หลัก) หรือ OSM (สำรอง)

GADM เป็นตัวตั้งต้นเสมอเมื่อมีไฟล์ ถ้าต้นทาง GADM ล่มจนดาวน์โหลดไม่ได้
จะใช้ชั้นที่สกัดจาก OSM pbf แทน (สร้างโดย scripts/02c_boundaries_osm.py)
ทั้งสองแหล่งมีฟิลด์ชุดเดียวกัน (GID_1/NAME_1/NL_NAME_1, GID_2/NAME_2/NAME_1)
สคริปต์ปลายน้ำจึงไม่ต้องรู้ว่ามาจากไหน

ที่มาที่ใช้จริงถูกบันทึกไว้ที่ data/boundaries/SOURCE.txt เพื่อแสดงในรายงาน
"""
import os

from .paths import ROOT

GADM = ROOT + r"\data\boundaries\gadm41_THA.gpkg"
OSM_ADM1 = ROOT + r"\data\boundaries\osm_adm1.gpkg"
OSM_ADM2 = ROOT + r"\data\boundaries\osm_adm2.gpkg"
SOURCE_TXT = ROOT + r"\data\boundaries\SOURCE.txt"


def have_gadm():
    return os.path.exists(str(GADM))


def source():
    """'gadm' หรือ 'osm'"""
    return "gadm" if have_gadm() else "osm"


def adm1_uri():
    """URI ชั้นจังหวัด (77) — EPSG:4326"""
    if have_gadm():
        return str(GADM) + "|layername=ADM_ADM_1"
    return str(OSM_ADM1) + "|layername=adm1"


def adm2_uri():
    """URI ชั้นอำเภอ/เขต — EPSG:4326"""
    if have_gadm():
        return str(GADM) + "|layername=ADM_ADM_2"
    return str(OSM_ADM2) + "|layername=adm2"


def write_source(note=""):
    """บันทึกที่มาลง SOURCE.txt (เรียกโดย 02b/02c)"""
    try:
        # ไม่ทับบันทึกที่ละเอียดกว่าของ 02c (เช่น "osm (adm1=77 adm2=926)")
        if not note and read_source().startswith(source()):
            return
        os.makedirs(os.path.dirname(str(SOURCE_TXT)), exist_ok=True)
        with open(str(SOURCE_TXT), "w", encoding="utf-8") as fh:
            fh.write((source() + (" " + note if note else "")).strip() + "\n")
    except Exception:
        pass


def read_source():
    """อ่านที่มาที่ใช้จริงในรอบล่าสุด ('' ถ้ายังไม่มีไฟล์บันทึก)"""
    try:
        with open(str(SOURCE_TXT), encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""
