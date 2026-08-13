# -*- coding: utf-8 -*-
"""ขั้น 2b: สร้าง TAZ ระดับจังหวัด + ประชากรรายโซน

เดิมสองไฟล์นี้ถูกสร้างด้วยมือใน QGIS (ดูหมายเหตุหัวไฟล์ 02_prep_network_taz.py)
และถูก gitignore ไว้ ทำให้รันใหม่บนเครื่องเปล่า/บน CI ไม่ได้ จึงย้ายมาเป็นสคริปต์

in : data/boundaries/gadm41_THA.gpkg (ADM_ADM_1) + data/raw/tha_pop_2020_100m.tif
out: data/zones_taz/taz_provinces.gpkg   (layer taz_provinces, EPSG:32647)
       fields: zone_id (1..77 เรียงตาม GID_1), GID_1, NAME_1, NL_NAME_1
     data/zones_taz/zone_population.gpkg (layer zone_population, EPSG:4326)
       fields: zone_id, GID_1, NAME_1, pop_sum

รันผ่าน qpy.bat (Windows) หรือ python3 (Linux/CI) ; log -> output/_02b.log
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.paths import ROOT as B, ensure          # noqa: E402

GADM = B + r"\data\boundaries\gadm41_THA.gpkg"
POP = B + r"\data\raw\tha_pop_2020_100m.tif"
OUT_TAZ = B + r"\data\zones_taz\taz_provinces.gpkg"
OUT_POP = B + r"\data\zones_taz\zone_population.gpkg"

LOG = open(str(B + r"\output\_02b.log"), "w", encoding="utf-8")


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.write(msg + "\n"); LOG.flush()
    print(msg)


def write(layer, path, name):
    from qgis.core import QgsVectorFileWriter, QgsCoordinateTransformContext
    if os.path.exists(str(path)):
        os.remove(str(path))
    o = QgsVectorFileWriter.SaveVectorOptions()
    o.driverName = "GPKG"
    o.layerName = name
    QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(path), QgsCoordinateTransformContext(), o)
    log("wrote", path, "|", layer.featureCount(), "features")


def main():
    from qgis.core import (QgsApplication, QgsVectorLayer, QgsField,
                           QgsCoordinateReferenceSystem)
    from qgis.PyQt.QtCore import QVariant
    import processing
    from processing.core.Processing import Processing

    app = QgsApplication([], False)
    app.initQgis()
    Processing.initialize()

    prov = QgsVectorLayer(str(GADM) + "|layername=ADM_ADM_1", "prov", "ogr")
    assert prov.isValid(), "ไม่พบ %s — รัน scripts/01_fetch_data.py gadm ก่อน" % GADM
    log("GADM ADM_1:", prov.featureCount(), "จังหวัด")

    fixed = processing.run("native:fixgeometries", {'INPUT': prov, 'OUTPUT': 'memory:'})['OUTPUT']

    # ── ประชากรรายจังหวัด (zonal sum จาก WorldPop, ทำใน 4326 เหมือนกับ raster) ──
    assert os.path.exists(str(POP)), "ไม่พบ %s — รัน scripts/01_fetch_data.py pop ก่อน" % POP
    zs = processing.run("native:zonalstatisticsfb", {
        'INPUT': fixed, 'INPUT_RASTER': str(POP), 'RASTER_BAND': 1,
        'COLUMN_PREFIX': 'pop_', 'STATISTICS': [1],          # 1 = sum
        'OUTPUT': 'memory:'})['OUTPUT']

    # ── zone_id เรียงตาม GID_1 เพื่อให้ลำดับโซนคงที่ทุกครั้งที่รัน ──
    gids = sorted({f['GID_1'] for f in zs.getFeatures()})
    zid = {g: i + 1 for i, g in enumerate(gids)}
    log("zones:", len(zid))

    zs.startEditing()
    if zs.fields().indexOf('zone_id') == -1:
        zs.addAttribute(QgsField('zone_id', QVariant.Int))
    zs.updateFields()
    i_zid = zs.fields().indexOf('zone_id')
    for f in zs.getFeatures():
        zs.changeAttributeValue(f.id(), i_zid, zid[f['GID_1']])
    zs.commitChanges()

    ensure(B + r"\data\zones_taz")
    write(zs, OUT_POP, "zone_population")

    # ── TAZ ใน 32647 (เมตร) สำหรับงานคำนวณระยะ/พื้นที่ ──
    taz = processing.run("native:reprojectlayer", {
        'INPUT': zs, 'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'),
        'OUTPUT': 'memory:'})['OUTPUT']
    write(taz, OUT_TAZ, "taz_provinces")

    tot = sum((f['pop_sum'] or 0) for f in zs.getFeatures())
    log("ประชากรรวม (WorldPop 2020): %.0f คน" % tot)
    app.exitQgis()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log("ERR", traceback.format_exc())
        sys.exit(1)
