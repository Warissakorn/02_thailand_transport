# -*- coding: utf-8 -*-
"""scenario — โหลดพารามิเตอร์ "ชุดสมมติฐาน" จาก inputs/scenarios/<name>.yaml

แนวคิด (ดู docs/PIPELINE_IO.md): ค่าตั้งต้นอยู่ใน config/model_params.py และค่าที่ calibrate แล้ว
อยู่ใน config/calibrated_params.py — ผู้ใช้ **ไม่ต้องแก้โค้ด** แต่แก้ไฟล์ scenario ใน inputs/ แทน
แล้ว commit; workflow จะรันใหม่ให้อัตโนมัติ

เลือก scenario ด้วยตัวแปรสภาพแวดล้อม TT_SCENARIO (ค่าเริ่มต้น "base")

โครงไฟล์ scenario มี 3 หมวด (แยกกันเพราะบาง key ชื่อซ้ำกันแต่คนละความหมาย เช่น
trip_rate_pax ใน model = ค่าดิบ 2.0, ใน calibrated = ค่าหลังปรับ 0.0792):
    model:       ทับค่าใน config/model_params.py
    calibrated:  ทับค่าใน config/calibrated_params.py
    run:         ค่าที่สคริปต์อ่านตรง (k_factor, eq_iter, ...)

การใช้งานในสคริปต์:
    import model_params as mp
    from lib import scenario as sc
    sc.apply(mp)                      # ทับค่าใน mp ด้วยหมวด model ของ scenario
    k = sc.get("k_factor", 0.09)      # ค่าจากหมวด run

รูปแบบไฟล์: YAML แบบเรียบง่าย (หมวด + key: value ย่อยหนึ่งชั้น) — ใช้ PyYAML ถ้ามี
ไม่มีก็ใช้ตัวอ่านสำรองในไฟล์นี้ เพื่อไม่ต้องเพิ่ม dependency ให้ image ของ QGIS
"""
import os

from .paths import ROOT

_CACHE = {}


def name():
    """ชื่อ scenario ที่กำลังใช้"""
    return os.environ.get("TT_SCENARIO", "base").strip() or "base"


def path(scen=None):
    return os.path.join(str(ROOT), "inputs", "scenarios", (scen or name()) + ".yaml")


# ── ตัวอ่าน YAML สำรอง (flat + dict ย่อยหนึ่งชั้น) ───────────────────
def _coerce(v):
    v = v.strip()
    if not v or v in ("~", "null"):
        return None
    if v[0] in "\"'" and v[-1] == v[0]:
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if v.startswith("{") and v.endswith("}"):        # inline dict: {car: 0, bus: 25}
        out = {}
        for part in v[1:-1].split(","):
            if not part.strip():
                continue
            k, _, val = part.partition(":")
            out[k.strip()] = _coerce(val)
        return out
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def _parse_simple(text):
    data, cur = {}, None
    for raw in text.split("\n"):
        line = raw.split("#", 1)[0].rstrip() if "#" in raw and not _in_quotes(raw) else raw.rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        key = key.strip()
        if indent == 0:
            if val.strip() == "":
                cur = data.setdefault(key, {})
            else:
                data[key] = _coerce(val)
                cur = None
        elif cur is not None:
            cur[key] = _coerce(val)
    return data


def _in_quotes(line):
    # "#" ที่อยู่ในเครื่องหมายคำพูดไม่ใช่คอมเมนต์ (พบน้อย แต่กันพลาด)
    before = line.split("#", 1)[0]
    return before.count('"') % 2 == 1 or before.count("'") % 2 == 1


def load(scen=None):
    """คืน dict ของ scenario (cache ไว้ต่อชื่อ); ไม่มีไฟล์ = dict ว่าง"""
    scen = scen or name()
    if scen in _CACHE:
        return _CACHE[scen]
    p = path(scen)
    data = {}
    if os.path.exists(p):
        text = open(p, encoding="utf-8").read()
        try:
            import yaml                              # ถ้ามี PyYAML ใช้ตัวจริง
            data = yaml.safe_load(text) or {}
        except ImportError:
            data = _parse_simple(text)
    _CACHE[scen] = data
    return data


def section(sec):
    """คืน dict ของหมวดหนึ่งใน scenario ('model' / 'calibrated' / 'run')"""
    v = load().get(sec)
    return v if isinstance(v, dict) else {}


def get(key, default=None):
    """ค่าจากหมวด run"""
    v = section("run").get(key)
    return default if v is None else v


_SECTION_OF = {"model_params": "model", "calibrated_params": "calibrated"}


def apply(*modules, **kw):
    """ทับค่าใน config module ด้วยหมวดที่ตรงกัน (key ตัวพิมพ์เล็ก -> ตัวพิมพ์ใหญ่)

    เฉพาะ key ที่โมดูลนั้นมีอยู่แล้วเท่านั้น เพื่อกันการพิมพ์ผิดเงียบ ๆ
    คืน list ของ (module, KEY, old, new) ที่เปลี่ยนจริง — เอาไปเขียน log ได้
    """
    forced = kw.get("sec")
    changes = []
    for mod in modules:
        sec = forced or _SECTION_OF.get(mod.__name__.rsplit(".", 1)[-1])
        if not sec:
            continue
        for k, v in section(sec).items():
            if v is None:
                continue
            KEY = k.upper()
            if hasattr(mod, KEY):
                old = getattr(mod, KEY)
                if old != v:
                    setattr(mod, KEY, v)
                    changes.append((mod.__name__, KEY, old, v))
    return changes


def describe():
    """ข้อความสรุป scenario สำหรับใส่ log / รายงาน"""
    d = load()
    if not d:
        return "scenario=%s (ไม่มีไฟล์ %s — ใช้ค่าตั้งต้นทั้งหมด)" % (name(), path())
    parts = []
    for sec in ("model", "calibrated", "run"):
        vals = section(sec)
        if vals:
            parts.append("%s{%s}" % (sec, ", ".join("%s=%s" % kv for kv in sorted(vals.items()))))
    return "scenario=%s: %s" % (name(), " ".join(parts) or "(ว่าง)")
