# -*- coding: utf-8 -*-
"""ขั้น 2a: สกัดโครงข่ายถนนจาก OSM pbf -> data/network/roads_raw_4326.gpkg

เดิมขั้นนี้ทำด้วยมือด้วย ogr2ogr นอกสคริปต์ ทำให้รันใหม่บนเครื่องเปล่า/บน CI ไม่ได้
(ขั้น 02 จะฟ้อง "roads_raw not found/valid") จึงย้ายมาเป็นสคริปต์ในไปป์ไลน์

in : data/raw/thailand-latest.osm.pbf (จาก 01_fetch_data.py) + config/osmconf.ini
out: data/network/roads_raw_4326.gpkg (layer roads_raw, EPSG:4326)
     fields: osm_id, name, highway, oneway, maxspeed, ref, lanes

ใช้ GDAL python เท่านั้น (ไม่ต้องเปิด QgsApplication) ; log -> output/_02a.log
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.paths import ROOT as B, ensure          # noqa: E402

# ชั้นถนนที่ใช้ในแบบจำลอง (ตรงกับตาราง DEFAULT ใน 02_prep_network_taz.py)
HIGHWAY = ['motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link',
           'secondary', 'secondary_link', 'tertiary', 'tertiary_link',
           'unclassified', 'residential', 'living_street', 'road']

SRC = B + r"\data\raw\thailand-latest.osm.pbf"
OUT = B + r"\data\network\roads_raw_4326.gpkg"
CONF = B + r"\config\osmconf.ini"

LOG = open(str(B + r"\output\_02a.log"), "w", encoding="utf-8")


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.write(msg + "\n"); LOG.flush()
    print(msg)


def main():
    from osgeo import gdal, ogr
    gdal.UseExceptions()

    if not os.path.exists(str(SRC)):
        log("ERR: ไม่พบ %s — รัน scripts/01_fetch_data.py osm ก่อน" % SRC)
        return 1

    # osmconf.ini กำหนดว่า tag ไหนถูกยกขึ้นเป็นคอลัมน์ (oneway/maxspeed/ref/lanes/...)
    gdal.SetConfigOption("OSM_CONFIG_FILE", str(CONF))
    gdal.SetConfigOption("OGR_INTERLEAVED_READING", "YES")
    gdal.SetConfigOption("OSM_MAX_TMPFILE_SIZE", "4000")     # MB — pbf ทั้งประเทศ

    ensure(B + r"\data\network")
    if os.path.exists(str(OUT)):
        os.remove(str(OUT))

    where = "highway IN (%s)" % ", ".join("'%s'" % h for h in HIGHWAY)
    log("extracting roads from", SRC)
    gdal.VectorTranslate(
        str(OUT), str(SRC),
        options=gdal.VectorTranslateOptions(
            format="GPKG", layers=["lines"], layerName="roads_raw",
            where=where,
            selectFields=["osm_id", "name", "highway", "oneway", "maxspeed", "ref", "lanes"],
            dstSRS="EPSG:4326", reproject=False,
            callback=None))

    ds = ogr.Open(str(OUT))
    n = ds.GetLayerByName("roads_raw").GetFeatureCount()
    ds = None
    log("wrote %s | features: %d" % (OUT, n))
    if n == 0:
        log("ERR: ไม่ได้ถนนสักเส้น — ตรวจ config/osmconf.ini หรือไฟล์ pbf")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log("ERR", traceback.format_exc())
        sys.exit(1)
