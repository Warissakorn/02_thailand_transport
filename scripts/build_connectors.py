# -*- coding: utf-8 -*-
"""สร้าง access/egress connector: โซน(centroid) -> terminal ใกล้สุด ของแต่ละโหมด
rail = rail_stations(855) | air = air_nodes(41) | water = ports(529)
access โดยรถยนต์: access_min = dist_km * detour(1.3) / speed(50 กม/ชม) * 60
connector เดียวกันใช้ทั้ง access(ต้นทาง) และ egress(ปลายทาง) เพราะ symmetric
out: data/zones_taz/access_{rail,air,water}.gpkg ; log -> output/_conn.log
รันผ่าน qpy.bat
"""
import os, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsPointXY, QgsSpatialIndex, QgsVectorFileWriter, QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant
import processing
from processing.core.Processing import Processing

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_conn.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
DETOUR, ACCESS_KMH = 1.3, 50.0

def reproj(path, ln):
    l = QgsVectorLayer(B + "\\" + path + "|layername=" + ln, ln, "ogr")
    return processing.run("native:reprojectlayer", {'INPUT': l,
        'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']

try:
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zones = [(f['zone_id'], f['NAME_1'], f.geometry().asPoint()) for f in cen.getFeatures()]
    log("zones:", len(zones))

    modes = {
        'rail':  (r"data\multimodal\rail_stations.gpkg", "rail_stations", "name"),
        'air':   (r"data\multimodal\air_nodes.gpkg",     "air_nodes",     "iata"),
        'water': (r"data\multimodal\ports.gpkg",         "ports",         "name"),
    }
    for mode, (path, ln, namefield) in modes.items():
        term = reproj(path, ln)
        idx = QgsSpatialIndex(term.getFeatures())
        tf = {f.id(): f for f in term.getFeatures()}
        out_lyr = QgsVectorLayer("LineString?crs=EPSG:32647", "access_"+mode, "memory")
        dp = out_lyr.dataProvider()
        dp.addAttributes([QgsField('zone_id', QVariant.Int), QgsField('NAME_1', QVariant.String),
                          QgsField('terminal', QVariant.String), QgsField('access_km', QVariant.Double),
                          QgsField('access_min', QVariant.Double)])
        out_lyr.updateFields()
        far = []
        for zid, nm, pt in zones:
            nn = idx.nearestNeighbor(QgsPointXY(pt), 1)
            tfeat = tf[nn[0]]; tpt = tfeat.geometry().asPoint()
            d_km = (QgsGeometry.fromPointXY(QgsPointXY(pt)).distance(QgsGeometry.fromPointXY(QgsPointXY(tpt)))) / 1000.0
            acc = d_km * DETOUR / ACCESS_KMH * 60.0
            tname = tfeat[namefield] if namefield in [fl.name() for fl in term.fields()] else ""
            f = QgsFeature(out_lyr.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(pt), QgsPointXY(tpt)]))
            f.setAttributes([zid, nm, tname, round(d_km, 1), round(acc, 1)]); dp.addFeature(f)
            if d_km > 60: far.append((nm, round(d_km)))
        out = B + r"\data\zones_taz\access_%s.gpkg" % mode
        if os.path.exists(out): os.remove(out)
        o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "access_"+mode
        QgsVectorFileWriter.writeAsVectorFormatV3(out_lyr, out, QgsCoordinateTransformContext(), o)
        log("access_%s: 77 connectors | zones >60km from terminal: %d %s" % (mode, len(far), far[:5]))
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
