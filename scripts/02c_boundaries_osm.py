# -*- coding: utf-8 -*-
"""ขั้น 2c (สำรอง): สร้างขอบเขตการปกครองจาก OSM pbf เมื่อ GADM ดาวน์โหลดไม่ได้

ต้นทาง GADM (geodata.ucdavis.edu) ล่มเป็นช่วง ๆ ทำให้ขั้น 01 ล้มทั้งรอบ
แต่ไฟล์ OSM ของไทยที่ดาวน์โหลดอยู่แล้วมีขอบเขตครบ:
  admin_level=4 -> จังหวัด (77) ; admin_level=6 -> อำเภอ/เขต
จึงสกัดออกมาเป็นชั้นที่มีฟิลด์เหมือน GADM ให้สคริปต์ปลายน้ำใช้ได้ทันที

in : data/raw/thailand-latest.osm.pbf + config/osmconf.ini
out: data/boundaries/osm_adm1.gpkg (layer adm1) GID_1, NAME_1, NL_NAME_1
     data/boundaries/osm_adm2.gpkg (layer adm2) GID_2, NAME_2, NL_NAME_2, NAME_1
     ทั้งคู่ EPSG:4326 เหมือน GADM (ปลายน้ำเป็นฝ่าย reproject เอง)

หมายเหตุ: ขอบเขต/ลำดับไม่ตรงกับ GADM เป๊ะ ๆ -> zone_id/district_id เปลี่ยน
และค่าที่ calibrate ไว้เดิม fit มาจากโซนแบบ GADM (ดู docs/DATA_SOURCES.md)

log -> output/_02c.log
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.paths import ROOT as B, ensure, hard_exit   # noqa: E402
from lib import boundaries as bd                     # noqa: E402

SRC = B + r"\data\raw\thailand-latest.osm.pbf"
CONF = B + r"\config\osmconf.ini"
TMP = B + r"\output\_osm_admin.gpkg"

N_PROV = 77          # จำนวนจังหวัดของไทย (รวมกรุงเทพฯ) — ใช้เป็นด่านตรวจ
N_DIST_EXPECT = 928  # จำนวนอำเภอ/เขตตาม GADM ADM_2 (OSM อาจต่างเล็กน้อย)

LOG = open(str(B + r"\output\_02c.log"), "w", encoding="utf-8")


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.write(msg + "\n"); LOG.flush()
    print(msg)


def extract_admin():
    """ดึง multipolygon ที่เป็นเขตปกครอง (level 4 และ 6) จาก pbf ครั้งเดียว"""
    from osgeo import gdal
    gdal.UseExceptions()
    gdal.SetConfigOption("OSM_CONFIG_FILE", str(CONF))
    gdal.SetConfigOption("OGR_INTERLEAVED_READING", "YES")
    gdal.SetConfigOption("OSM_MAX_TMPFILE_SIZE", "4000")

    ensure(B + r"\output")
    if os.path.exists(str(TMP)):
        os.remove(str(TMP))

    log("extracting admin boundaries from", SRC)
    gdal.VectorTranslate(
        str(TMP), str(SRC),
        options=gdal.VectorTranslateOptions(
            format="GPKG", layers=["multipolygons"], layerName="admin",
            where="boundary = 'administrative' AND admin_level IN ('4', '6')",
            selectFields=["osm_id", "osm_way_id", "name", "name_en", "admin_level"],
            dstSRS="EPSG:4326", reproject=False))


def write(layer, path, name):
    from qgis.core import QgsVectorFileWriter, QgsCoordinateTransformContext
    if os.path.exists(str(path)):
        os.remove(str(path))
    o = QgsVectorFileWriter.SaveVectorOptions()
    o.driverName = "GPKG"
    o.layerName = name
    QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), o)
    log("wrote", path, "|", layer.featureCount(), "features")


def _name(f):
    """ชื่ออังกฤษ (ถ้าไม่มีใช้ชื่อไทยแทน เพื่อให้เรียงลำดับได้เสมอ)"""
    for k in ("name_en", "name:en"):
        try:
            v = f[k]
        except KeyError:
            continue
        if v:
            return str(v)
    return str(f["name"] or "")


def build_layer(feats, fields, name, crs="EPSG:4326"):
    """สร้าง memory layer จาก [(geom, {field: value})]"""
    from qgis.core import QgsVectorLayer, QgsField, QgsFeature
    from qgis.PyQt.QtCore import QVariant
    lyr = QgsVectorLayer("MultiPolygon?crs=" + crs, name, "memory")
    dp = lyr.dataProvider()
    dp.addAttributes([QgsField(f, QVariant.String) for f in fields])
    lyr.updateFields()
    out = []
    for geom, attrs in feats:
        nf = QgsFeature(lyr.fields())
        nf.setGeometry(geom)
        for f in fields:
            nf[f] = attrs.get(f)
        out.append(nf)
    dp.addFeatures(out)
    lyr.updateExtents()
    return lyr


def main():
    from qgis.core import QgsApplication, QgsVectorLayer, QgsSpatialIndex
    import processing
    from processing.core.Processing import Processing

    if not os.path.exists(str(SRC)):
        log("ERR: ไม่พบ %s — รัน scripts/01_fetch_data.py osm ก่อน" % SRC)
        return 1

    extract_admin()

    app = QgsApplication([], False)
    app.initQgis()
    Processing.initialize()

    src = QgsVectorLayer(str(TMP) + "|layername=admin", "admin", "ogr")
    if not src.isValid():
        log("ERR: สกัดขอบเขตจาก pbf ไม่สำเร็จ (%s ใช้ไม่ได้)" % TMP)
        return 1
    fixed = processing.run("native:fixgeometries", {'INPUT': src, 'OUTPUT': 'memory:'})['OUTPUT']

    lv4, lv6 = [], []
    for f in fixed.getFeatures():
        lvl = str(f['admin_level'] or "")
        nm = _name(f)
        if not nm or f.geometry().isEmpty():
            continue
        rec = (f.geometry(), nm, str(f['name'] or nm))
        (lv4 if lvl == '4' else lv6 if lvl == '6' else []).append(rec)
    log("จาก OSM: admin_level=4 -> %d, admin_level=6 -> %d" % (len(lv4), len(lv6)))

    # ── จังหวัด: GID_1 = THA.<n>_1 โดย n เรียงตามชื่ออังกฤษ (ให้ลำดับคงที่ทุกรอบ) ──
    lv4.sort(key=lambda r: r[1])
    prov_feats = []
    for i, (geom, en, th) in enumerate(lv4, 1):
        prov_feats.append((geom, {"GID_1": "THA.%d_1" % i, "NAME_1": en, "NL_NAME_1": th}))
    adm1 = build_layer(prov_feats, ["GID_1", "NAME_1", "NL_NAME_1"], "adm1")

    ensure(B + r"\data\boundaries")
    if len(prov_feats) != N_PROV:
        log("ERR: ได้จังหวัด %d แห่ง (ต้องเป็น %d) — ข้อมูล OSM ไม่ครบหรือ tag เปลี่ยน"
            % (len(prov_feats), N_PROV))
        return 1
    write(adm1, bd.OSM_ADM1, "adm1")

    # ── อำเภอ: หาจังหวัดแม่จาก centroid ที่ตกในโพลิกอนจังหวัด ──
    idx = QgsSpatialIndex(adm1.getFeatures())
    prov_by_id = {f.id(): f for f in adm1.getFeatures()}

    def parent(geom):
        c = geom.centroid()
        if c.isEmpty():
            return None
        for fid in idx.intersects(c.boundingBox()):
            if prov_by_id[fid].geometry().contains(c):
                return prov_by_id[fid]
        near = idx.nearestNeighbor(c.asPoint(), 1)     # centroid ตกนอกรูป (รูปเว้า/เกาะ)
        return prov_by_id[near[0]] if near else None

    lv6.sort(key=lambda r: r[1])
    by_prov = {}
    orphan = 0
    for geom, en, th in lv6:
        p = parent(geom)
        if p is None:
            orphan += 1
            continue
        by_prov.setdefault(p["GID_1"], []).append((geom, en, th, p["NAME_1"]))

    dist_feats = []
    for gid1 in sorted(by_prov, key=lambda g: int(g.split(".")[1].split("_")[0])):
        pi = int(gid1.split(".")[1].split("_")[0])
        for j, (geom, en, th, pname) in enumerate(by_prov[gid1], 1):
            dist_feats.append((geom, {"GID_2": "THA.%d.%d_1" % (pi, j), "NAME_2": en,
                                      "NL_NAME_2": th, "NAME_1": pname, "GID_1": gid1}))
    adm2 = build_layer(dist_feats, ["GID_2", "NAME_2", "NL_NAME_2", "NAME_1", "GID_1"], "adm2")
    if not dist_feats:
        log("ERR: ไม่ได้อำเภอสักแห่ง — ตรวจ admin_level=6 ใน pbf")
        return 1
    if orphan:
        log("เตือน: อำเภอ %d แห่งหาจังหวัดแม่ไม่ได้ จึงถูกข้าม" % orphan)
    if len(dist_feats) != N_DIST_EXPECT:
        log("เตือน: ได้อำเภอ %d แห่ง (GADM มี %d) — ผลรายอำเภอจะเทียบกันตรง ๆ ไม่ได้"
            % (len(dist_feats), N_DIST_EXPECT))
    write(adm2, bd.OSM_ADM2, "adm2")

    bd.write_source("(adm1=%d adm2=%d)" % (len(prov_feats), len(dist_feats)))
    log("ที่มาของขอบเขตรอบนี้:", bd.read_source())
    log("DONE")
    hard_exit(0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log("ERR", traceback.format_exc())
        sys.exit(1)
