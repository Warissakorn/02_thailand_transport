# -*- coding: utf-8 -*-
"""ตรวจความถูกต้องของชั้น INPUT ก่อนรันจริง (ใช้เป็น required check ของ branch main)

    python3 scripts/_check_inputs.py

ตรวจ 4 อย่าง (ไม่ต้องใช้ QGIS จึงรันได้ในไม่กี่วินาที):
  1. ไฟล์ข้อมูลนำเข้าที่จำเป็นใน inputs/ มีครบ
  2. ทุก inputs/scenarios/*.yaml อ่านได้ และหมวดถูกต้อง (model/calibrated/run)
  3. ทุก key ในหมวด model/calibrated มีอยู่จริงใน config/*.py (กันพิมพ์ผิดแล้วเงียบ)
     และ key ในหมวด run อยู่ในรายการที่สคริปต์อ่านจริง
  4. ค่าที่ต้องเป็นตัวเลขเป็นตัวเลข และอยู่ในช่วงที่สมเหตุสมผล

exit 0 = ผ่าน, 1 = มีปัญหา (พิมพ์รายการปัญหาทั้งหมด ไม่หยุดที่ข้อแรก)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"))

from lib.paths import ROOT           # noqa: E402
from lib import scenario as sc       # noqa: E402

# ไฟล์นำเข้าที่ pipeline ต้องใช้ (relative ต่อ ROOT)
REQUIRED_INPUTS = [
    "inputs/scenarios/base.yaml",
    "inputs/calibration/aadt_2565.csv",
    "inputs/calibration/history/aadt_2566.csv",
    "inputs/calibration/targets/intercity_pt_share_otp6503.csv",
    "inputs/calibration/targets/freight_by_mode_2560_2565.csv",
    "inputs/landuse/schools_pts.gpkg",
    "inputs/landuse/schools_poly.gpkg",
    "inputs/landuse/industrial.gpkg",
    "inputs/multimodal/rail_lines.gpkg",
    "inputs/multimodal/rail_stations.gpkg",
    "inputs/multimodal/ports.gpkg",
    "inputs/multimodal/ferry_routes.gpkg",
    "inputs/multimodal/airports_pts.gpkg",
    "inputs/multimodal/openflights_airports.dat",
    "inputs/multimodal/openflights_routes.dat",
]

# key ในหมวด run ที่สคริปต์อ่านจริง (ดู 13/14 และ docs/PIPELINE_IO.md)
RUN_KEYS = {"k_factor", "eq_iter", "workers", "dijkstra_batch", "local_trip_km"}

# ช่วงค่าที่ยอมรับ (นอกช่วงนี้แปลว่าน่าจะพิมพ์ผิด)
RANGES = {
    "trip_rate_pax": (0.0, 20.0), "freight_factor": (0.0, 5.0),
    "gravity_beta_pax": (0.0, 1.0), "gravity_beta_frg": (0.0, 1.0),
    "beta_pax": (0.0, 1.0), "beta_frg": (0.0, 1.0),
    "logit_theta": (0.0, 1.0), "vot_thb_per_min": (0.0, 100.0),
    "gravity_max_iter": (1, 100000), "gravity_tol": (0.0, 1.0),
    "aadt_year": (2500, 2700), "geh_target": (0.0, 100.0), "geh_pass_pct": (0.0, 1.0),
    "k_factor": (0.0, 1.0), "eq_iter": (1, 100), "workers": (0, 64),
    "dijkstra_batch": (1, 1000), "local_trip_km": (0.0, 100.0),
}

SECTIONS = ("model", "calibrated", "run")


def check_files(problems):
    for rel in REQUIRED_INPUTS:
        if not os.path.exists(os.path.join(str(ROOT), rel)):
            problems.append("ไม่พบไฟล์นำเข้า: %s" % rel)


def known_keys():
    import model_params as mp
    import calibrated_params as cp
    low = lambda mod: {a.lower() for a in dir(mod) if a.isupper()}   # noqa: E731
    return low(mp), low(cp)


def check_scenario(path, problems):
    name = os.path.splitext(os.path.basename(path))[0]
    data = sc.load(name)
    if not isinstance(data, dict) or not data:
        problems.append("%s: อ่านไม่ได้หรือว่างเปล่า" % path)
        return
    mp_keys, cp_keys = known_keys()
    for section, values in data.items():
        if section not in SECTIONS:
            problems.append("%s: ไม่รู้จักหมวด '%s' (ใช้ได้: %s)" % (path, section, ", ".join(SECTIONS)))
            continue
        if not isinstance(values, dict):
            problems.append("%s: หมวด '%s' ต้องเป็น key: value" % (path, section))
            continue
        allowed = {"model": mp_keys, "calibrated": cp_keys, "run": RUN_KEYS}[section]
        for k, v in values.items():
            if k not in allowed:
                problems.append("%s: %s.%s ไม่มีผลกับแบบจำลอง (สะกดผิด?)" % (path, section, k))
                continue
            if k in RANGES:
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    problems.append("%s: %s.%s ต้องเป็นตัวเลข (ได้ %r)" % (path, section, k, v))
                    continue
                lo, hi = RANGES[k]
                if not (lo <= v <= hi):
                    problems.append("%s: %s.%s = %r อยู่นอกช่วงที่คาด [%s, %s]"
                                    % (path, section, k, v, lo, hi))


def main():
    problems = []
    check_files(problems)

    scen_dir = os.path.join(str(ROOT), "inputs", "scenarios")
    files = sorted(f for f in os.listdir(scen_dir) if f.endswith((".yaml", ".yml"))) \
        if os.path.isdir(scen_dir) else []
    if not files:
        problems.append("ไม่พบ scenario ใด ๆ ใน inputs/scenarios/")
    for f in files:
        check_scenario(os.path.join("inputs", "scenarios", f), problems)

    print("ตรวจไฟล์นำเข้า %d รายการ | scenario %d ไฟล์: %s"
          % (len(REQUIRED_INPUTS), len(files), ", ".join(files) or "-"))
    if problems:
        print("\nพบปัญหา %d ข้อ:" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    print("ผ่านทั้งหมด")
    return 0


if __name__ == "__main__":
    sys.exit(main())
