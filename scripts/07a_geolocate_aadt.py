# -*- coding: utf-8 -*-
"""ขั้น 7a (v2): geolocate สถานี AADT ลงโครงข่าย OSM
วิธี v2 (chainage ทั้งสาย):
  1) รวมทุก segment ของสาย (ref) ทั่วประเทศ -> mergeLines -> ใช้ part ยาวสุดเป็นแนวสายหลัก
  2) วางสถานีตามระยะ กม. สัมบูรณ์ (chainage) โดย scale ให้พอดีความยาว OSM
  3) เลือกทิศ (ไป/กลับ) ที่ทำให้สถานีตกใน "จังหวัดที่ระบุ" มากที่สุด = การ validate ในตัว
  4) สถานีที่ยังไม่ตกจังหวัดถูกต้อง -> fallback วิธี v1 (interpolate รายจังหวัด)
เพิ่มฟิลด์ PCU แยกสาย: aadt_pax_pcu (รถยนต์นั่ง+โดยสาร+จยย.) / aadt_frg_pcu (รถบรรทุกทุกประเภท)
out: model/5_calibration/aadt_points.gpkg (ทับเดิม; field: route,prov,km,aadt,pax_pcu,frg_pcu,method)
log -> output/_geo.log ; รันผ่าน qpy.bat
"""
import os, csv, re, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsVectorFileWriter, QgsCoordinateTransformContext, QgsPointXY)
from qgis.PyQt.QtCore import QVariant

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit, ensure_parent
B = _ROOT
LOG = open(B + r"\output\_geo.log", "w", encoding="utf-8")
def log(*a):
    # พิมพ์ออก stdout ด้วย: บน CI ขั้นดัมป์ log ท้าย job หยิบมาแค่ 3 ไฟล์ล่าสุด
    # _geo.log จึงมองไม่เห็นเลยเวลาไปพังที่ขั้น 13 ทีหลัง
    msg = " ".join(str(x) for x in a)
    LOG.write(msg + "\n"); LOG.flush()
    print(msg, flush=True)

# PCU ต่อชนิดรถ (คอลัมน์ AADT กรมทางหลวง) — mapping ระบุใน DATA_SOURCES/METHODOLOGY
PCU_PAX = {4: 1.0, 5: 1.0, 6: 1.5, 7: 2.0, 8: 2.5, 17: 0.33}  # นั่ง<=7, นั่ง>7, โดยสารเล็ก/กลาง/ใหญ่, สามล้อ+จยย.
PCU_FRG = {9: 1.5, 10: 2.0, 11: 2.5, 12: 3.0, 13: 3.0}        # บรรทุก 4ล้อ/6ล้อ/10ล้อ/พ่วง/กึ่งพ่วง

def norm_prov(s):
    s = (s or "")
    for w in ("อำเภอเมือง", "จังหวัด", "จ.", "มหานคร"):
        s = s.replace(w, "")
    return s.replace(" ", "").strip()
def norm_ref(s):
    m = re.match(r"\s*(\d+)", str(s or "")); return m.group(1) if m else None
def parse_km(s):
    m = re.match(r"\s*(\d+)\+(\d+)", str(s or ""))
    return (int(m.group(1)) + int(m.group(2))/1000.0) if m else None
def fnum(s):
    try: return float(str(s).replace(",", ""))
    except Exception: return 0.0

def longest_part(geom):
    """คืน (polyline_geom, length) ของ part ยาวสุด"""
    if geom.isMultipart():
        best = None; bl = -1
        for part in geom.asMultiPolyline():
            g = QgsGeometry.fromPolylineXY(part)
            if g.length() > bl: bl = g.length(); best = g
        return best, bl
    return geom, geom.length()

try:
    app = QgsApplication([], False); app.initQgis()
    taz = QgsVectorLayer(B + r"\data\zones_taz\taz_provinces.gpkg|layername=taz_provinces", "t", "ogr")
    # ลงทะเบียนหลายคีย์ต่อจังหวัด: ชื่อไทยและชื่ออังกฤษสะกดต่างกันระหว่าง GADM กับ OSM
    # (เดิมผูกกับสตริงของ GADM ตรง ๆ พอใช้ขอบเขต OSM จึงจับคู่ไม่ได้เลยสักจังหวัด)
    prov_geom = {}
    nprov = 0
    for f in taz.getFeatures():
        g = f.geometry(); nprov += 1
        th = str(f['NL_NAME_1'] or ""); en = str(f['NAME_1'] or "")
        for k in (norm_prov(th), norm_prov(en)):
            if k:
                prov_geom.setdefault(k, g)
        if en.startswith("Bangkok") or "กรุงเทพ" in th:
            for k in ("กรุงเทพ", "กรุงเทพฯ", "กทม"):
                prov_geom.setdefault(k, g)
    log("provinces: %d (คีย์ชื่อ %d แบบ)" % (nprov, len(prov_geom)))

    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    by_ref = {}
    for f in net.getFeatures():
        r = norm_ref(f['ref'])
        if r: by_ref.setdefault(r, []).append(f.geometry())
    log("distinct refs in net:", len(by_ref))

    rows = list(csv.reader(open(B + r"\data\calibration\aadt_current.csv", encoding="utf-8-sig")))[1:]  # projected 2569 (สร้างโดย build_aadt_projection.py)
    stations = []
    for r in rows:
        route = norm_ref(r[0]); km = parse_km(r[3]); prov = norm_prov(r[19])
        aadt = fnum(r[14])
        if not (route and km is not None and aadt > 0): continue
        pax = sum(fnum(r[i])*p for i, p in PCU_PAX.items())
        frg = sum(fnum(r[i])*p for i, p in PCU_FRG.items())
        stations.append((route, prov, km, aadt, pax, frg))
    log("stations parsed:", len(stations))

    # ชื่อที่ยังจับคู่ไม่ได้: ลองแบบชื่อหนึ่งเป็นสับสเตตริงของอีกชื่อ (ทำครั้งเดียว ไม่ใช่ต่อสถานี)
    want = {s[1] for s in stations}
    miss = sorted(p for p in want if p and p not in prov_geom)
    for p in list(miss):
        hit = [k for k in prov_geom if k and (k in p or p in k)]
        if len(hit) == 1:
            prov_geom[p] = prov_geom[hit[0]]
            miss.remove(p)
    log("จังหวัดใน AADT: %d | จับคู่ได้ %d | ยังไม่ได้ %d%s"
        % (len(want), len(want) - len(miss), len(miss),
           (": " + ", ".join(miss[:10])) if miss else ""))

    by_route = {}
    for s in stations: by_route.setdefault(s[0], []).append(s)

    out = QgsVectorLayer("Point?crs=EPSG:32647", "aadt_points", "memory"); dp = out.dataProvider()
    dp.addAttributes([QgsField('route', QVariant.String), QgsField('prov', QVariant.String),
                      QgsField('km', QVariant.Double), QgsField('aadt', QVariant.Double),
                      QgsField('pax_pcu', QVariant.Double), QgsField('frg_pcu', QVariant.Double),
                      QgsField('method', QVariant.String)])
    out.updateFields()

    n_chain = 0; n_fb = 0; n_skip = 0
    for route, sts in by_route.items():
        placed = {}  # idx -> (pt, method)
        geoms = by_ref.get(route)
        if geoms:
            merged = QgsGeometry.unaryUnion(geoms)
            try: merged = merged.mergeLines()
            except Exception: pass
            main, L = longest_part(merged)
            kms = [s[2] for s in sts]
            km_min, km_max = min(kms), max(kms); span_m = (km_max - km_min)*1000.0
            if main is not None and L > 0 and span_m > 0:
                scale = L/span_m
                if 0.4 <= scale <= 2.5:  # แนว OSM ครอบช่วงสถานีพอสมควร
                    best_dir = None; best_score = -1; best_pts = None
                    for rev in (False, True):
                        pts = []; score = 0
                        for s in sts:
                            chain = (s[2]-km_min)*1000.0*scale
                            if rev: chain = L - chain
                            chain = min(max(chain, 0.0), L)
                            p = main.interpolate(chain)
                            ok = (s[1] in prov_geom and not p.isEmpty()
                                  and prov_geom[s[1]].contains(p))
                            pts.append((p, ok)); score += ok
                        if score > best_score:
                            best_score = score; best_pts = pts; best_dir = rev
                    for i, (p, ok) in enumerate(best_pts):
                        if ok: placed[i] = (p, 'chainage')
        # fallback v1: interpolate รายจังหวัดสำหรับที่เหลือ
        rem = [i for i in range(len(sts)) if i not in placed]
        if rem and geoms:
            grp = {}
            for i in rem: grp.setdefault(sts[i][1], []).append(i)
            for prov, idxs in grp.items():
                pg = prov_geom.get(prov)
                if pg is None: continue
                clipped = []
                for g in geoms:
                    if g.boundingBoxIntersects(pg):
                        inter = g.intersection(pg)
                        if inter and not inter.isEmpty() and inter.length() > 0:
                            clipped.append(inter)
                if not clipped: continue
                m = QgsGeometry.unaryUnion(clipped)
                try: m = m.mergeLines()
                except Exception: pass
                Lp = m.length()
                if Lp <= 0: continue
                kms = sorted(sts[i][2] for i in idxs)
                kmin, kmax = kms[0], kms[-1]; span = (kmax-kmin) or 1.0
                for i in idxs:
                    frac = 0.5 if len(idxs) == 1 else (sts[i][2]-kmin)/span
                    p = m.interpolate(frac*Lp)
                    if not p.isEmpty(): placed[i] = (p, 'fallback')
        for i, s in enumerate(sts):
            if i in placed:
                p, meth = placed[i]
                ft = QgsFeature(out.fields()); ft.setGeometry(p)
                ft.setAttributes([s[0], s[1], round(s[2], 3), s[3], round(s[4], 1), round(s[5], 1), meth])
                dp.addFeature(ft)
                if meth == 'chainage': n_chain += 1
                else: n_fb += 1
            else:
                n_skip += 1

    # model/ ถูก gitignore จึงไม่มีบนเครื่องที่ clone ใหม่ — ถ้าไม่สร้างโฟลเดอร์ก่อน
    # writer จะไม่เขียนอะไรเลยโดยไม่โยน error ทำให้ขั้น 13/14 อ่านได้ 0 สถานี
    o = ensure_parent(B + r"\model\5_calibration\aadt_points.gpkg")
    if os.path.exists(o): os.remove(o)
    opt = QgsVectorFileWriter.SaveVectorOptions(); opt.driverName = "GPKG"; opt.layerName = "aadt_points"
    res = QgsVectorFileWriter.writeAsVectorFormatV3(out, o, QgsCoordinateTransformContext(), opt)
    if (isinstance(res, (tuple, list)) and res[0] != QgsVectorFileWriter.NoError) or not os.path.exists(o):
        raise RuntimeError("เขียน %s ไม่สำเร็จ: %r" % (o, res))
    tot = n_chain + n_fb
    log("PLACED %d/%d | chainage(validated-in-province)=%d (%.1f%%) fallback=%d skip=%d" % (
        tot, len(stations), n_chain, 100.0*n_chain/max(tot, 1), n_fb, n_skip))
    if tot == 0:
        # ปล่อยผ่านไม่ได้: ขั้น 13 จะรันไปอีกชั่วโมงกว่าแล้วค่อยพังเพราะไม่มีสถานีให้เทียบ
        log("ERR: วางสถานีลงโครงข่ายไม่ได้เลย — ตรวจการจับคู่ชื่อจังหวัดด้านบน "
            "และฟิลด์ ref ของ network_clean (refs=%d)" % len(by_ref))
        hard_exit(1)
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์
except Exception:
    log("ERR", traceback.format_exc()); raise
