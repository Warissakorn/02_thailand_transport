# -*- coding: utf-8 -*-
"""clean ferry/water network -> data/network/water_clean.gpkg (EPSG:32647 + travel_min)
boat speed ~ 30 กม/ชม (เฉลี่ยเรือข้ามฟาก/ชายฝั่ง) ; รันผ่าน qpy.bat ; log -> output/_water.log
"""
import os, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant
import processing
from processing.core.Processing import Processing

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_water.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
BOAT_KMH = 30.0

try:
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()
    f = QgsVectorLayer(B + r"\data\multimodal\ferry_routes.gpkg|layername=ferry_routes", "f", "ogr")
    rep = processing.run("native:reprojectlayer", {'INPUT': f,
        'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']
    rep.startEditing()
    for n, t in [('length_m', QVariant.Double), ('speed_kmh', QVariant.Double), ('travel_min', QVariant.Double)]:
        rep.addAttribute(QgsField(n, t))
    rep.updateFields()
    fi = {n: rep.fields().indexOf(n) for n in ['length_m', 'speed_kmh', 'travel_min']}
    for ft in rep.getFeatures():
        L = ft.geometry().length()
        rep.changeAttributeValue(ft.id(), fi['length_m'], round(L, 1))
        rep.changeAttributeValue(ft.id(), fi['speed_kmh'], BOAT_KMH)
        rep.changeAttributeValue(ft.id(), fi['travel_min'], round(L/1000.0/BOAT_KMH*60.0, 4))
    rep.commitChanges()
    out = B + r"\data\network\water_clean.gpkg"
    if os.path.exists(out): os.remove(out)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "water_clean"
    QgsVectorFileWriter.writeAsVectorFormatV3(rep, out, QgsCoordinateTransformContext(), o)
    log("water_clean:", rep.featureCount(), "| total km:", round(sum(ft['length_m'] for ft in rep.getFeatures())/1000))
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
