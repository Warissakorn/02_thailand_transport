# -*- coding: utf-8 -*-
"""report_data — อ่านผลลัพธ์ของแบบจำลองเพื่อนำไปแสดง (ใช้ร่วมกันโดย 16_summary / 17_build_site)

ออกแบบให้ทนต่อผลลัพธ์ที่ยังไม่ครบ: ไม่มีไฟล์ = คืนค่าว่าง ไม่ throw
ไม่พึ่ง QGIS/numpy จึงรันได้แม้ขั้นโมเดลจะล้ม
"""
import csv
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta

from .paths import ROOT, REPORT, MODEL
from . import scenario as sc
from . import boundaries as bd

TABLES = REPORT + r"\tables"
FIGURES = REPORT + r"\figures"

# ชื่อที่แสดงของแต่ละตาราง/รูป (ตามที่ 15_report_outputs.py สร้าง)
TABLE_TITLES = {
    "T1_trip_generation_by_province.csv": "T1 — การเกิดการเดินทางรายจังหวัด",
    "T2_mode_share_vs_target.csv":        "T2 — สัดส่วนรายโหมด เทียบเป้าหมาย",
    "T3b_beta_search_curves.csv":         "T3b — ผลการค้นหาค่า beta",
    "T4_parameters.csv":                  "T4 — พารามิเตอร์และที่มา",
    "T5_assignment_stats.csv":            "T5 — สถิติการ assignment",
    "T6_capacity_utilization.csv":        "T6 — การใช้ความจุถนน",
}
FIGURE_TITLES = {
    "F1_study_area.png":          "F1 — พื้นที่ศึกษา",
    "F2_multimodal_network.png":  "F2 — โครงข่ายหลายรูปแบบ",
    "F3_trip_generation.png":     "F3 — การเกิดการเดินทาง",
    "F4_assigned_volume.png":     "F4 — ปริมาณจราจรที่กำหนดลงโครงข่าย",
    "F5_flow_components.png":     "F5 — องค์ประกอบกระแสจราจร (คน/สินค้า)",
    "F6_geh_map.png":             "F6 — แผนที่ค่า GEH",
}

# ขั้นตอน -> ไฟล์ผลลัพธ์ที่ควรมี (relative ต่อ ROOT)
STAGES = [
    ("03/08a trip generation", "model/1_trip_generation/district_tripgen.csv"),
    ("13 calibration",         "model/5_calibration/calibration_report_final.txt"),
    ("14 assignment",          "model/4_trip_assignment/assigned_final_dist.gpkg"),
    ("15 ตารางรายงาน",          "output/report/tables/T5_assignment_stats.csv"),
    ("15 รูปแผนที่",            "output/report/figures/F4_assigned_volume.png"),
    ("build_project (.qgz)",   "thailand_transport.qgz"),
]


def _git(*args):
    try:
        return subprocess.check_output(("git",) + args, cwd=str(ROOT),
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def run_meta():
    """ข้อมูลประจำรอบการรัน (scenario, commit, เวลา)"""
    tz = timezone(timedelta(hours=7))             # เวลาไทย
    sha = os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD")
    meta = {
        "scenario": sc.name(),
        "เวลาที่สร้างรายงาน": datetime.now(tz).strftime("%Y-%m-%d %H:%M น. (ICT)"),
    }
    # ที่มาของขอบเขตการปกครอง: gadm (ปกติ) หรือ osm (สำรองตอนต้นทาง GADM ล่ม)
    # ผลจากขอบเขตสองชุดเทียบกันตรง ๆ ไม่ได้ จึงต้องติดมากับรายงานเสมอ
    src = bd.read_source()
    if src:
        meta["ขอบเขตการปกครอง"] = src
    if sha:
        meta["commit"] = sha[:8]
    msg = _git("log", "-1", "--pretty=%s")
    if msg:
        meta["ข้อความ commit"] = msg
    if os.environ.get("GITHUB_RUN_ID"):
        meta["run"] = "#%s (%s)" % (os.environ.get("GITHUB_RUN_NUMBER", "?"),
                                    os.environ.get("GITHUB_WORKFLOW", "workflow"))
    return meta


def scenario_values():
    """คืน [(หมวด, key, ค่า)] ของ scenario ที่ใช้ในรอบนี้"""
    rows = []
    for secname in ("model", "calibrated", "run"):
        for k, v in sorted(sc.section(secname).items()):
            rows.append((secname, k, v))
    return rows


def status():
    """[(ชื่อขั้น, path, มีไฟล์ไหม)]"""
    return [(s, rel, os.path.exists(os.path.join(str(ROOT), rel))) for s, rel in STAGES]


def read_table(fname, limit=None):
    """อ่าน CSV เป็น list-of-list (แถวแรก = หัวตาราง); ไม่มีไฟล์ -> []"""
    p = os.path.join(str(TABLES), fname)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.reader(fh) if r]
    return rows[:limit + 1] if limit else rows


def tables():
    """[(ชื่อไฟล์, ชื่อแสดงผล, จำนวนแถวข้อมูล)] เรียงตามชื่อ"""
    if not os.path.isdir(str(TABLES)):
        return []
    out = []
    for fn in sorted(os.listdir(str(TABLES))):
        if fn.endswith(".csv"):
            n = max(len(read_table(fn)) - 1, 0)
            out.append((fn, TABLE_TITLES.get(fn, fn), n))
    return out


def figures():
    """[(ชื่อไฟล์, ชื่อแสดงผล)] เรียงตามชื่อ"""
    if not os.path.isdir(str(FIGURES)):
        return []
    return [(fn, FIGURE_TITLES.get(fn, fn))
            for fn in sorted(os.listdir(str(FIGURES))) if fn.lower().endswith(".png")]


_FIT = re.compile(r"(pax|frg|passenger|freight|total)[^\n]*?"
                  r"R2\s*=\s*(-?[\d.]+)[^\n]*?(?:med)?GEH\s*=\s*([\d.]+)", re.I)


def calibration_fit():
    """ดึง R2 / median GEH จาก calibration_report_final.txt -> ตาราง [[หัว],[แถว]]

    รูปแบบไฟล์อาจต่างกันไปตามรุ่นของสคริปต์ จึงใช้ regex แบบหลวม ๆ
    ถ้าจับไม่ได้เลยจะคืน [] แล้วผู้เรียกข้ามส่วนนี้ไป
    """
    p = os.path.join(str(MODEL), "5_calibration", "calibration_report_final.txt")
    if not os.path.exists(p):
        return []
    text = open(p, encoding="utf-8", errors="replace").read()
    rows = [["สาย", "R²", "median GEH"]]
    for m in _FIT.finditer(text):
        rows.append([m.group(1).lower(), m.group(2), m.group(3)])
    return rows if len(rows) > 1 else []


def calibration_report_text(max_chars=8000):
    p = os.path.join(str(MODEL), "5_calibration", "calibration_report_final.txt")
    if not os.path.exists(p):
        return ""
    return open(p, encoding="utf-8", errors="replace").read()[:max_chars]
