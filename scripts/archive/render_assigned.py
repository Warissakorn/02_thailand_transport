# -*- coding: utf-8 -*-
"""เรนเดอร์แผนที่ปริมาณจราจร (assigned_eq) — เส้นหนา/สี ∝ vol_pcu
รันผ่าน qpy.bat ; out: output/assigned_eq_traffic.png ; log -> output/_ra.log
"""
import os, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsMapSettings, QgsMapRendererCustomPainterJob,
    QgsCoordinateReferenceSystem, QgsLineSymbol, QgsFillSymbol, QgsProperty, QgsSymbolLayer,
    QgsGraduatedSymbolRenderer, QgsClassificationQuantile, QgsGradientColorRamp)
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtCore import QSize

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_ra.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

try:
    app = QgsApplication([], False); app.initQgis()
    taz = QgsVectorLayer(B + r"\data\zones_taz\taz_provinces.gpkg|layername=taz_provinces", "t", "ogr")
    taz.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '#fafafa', 'outline_color': '#eeeeee', 'outline_width': '0.15'}))
    asg = QgsVectorLayer(B + r"\model\4_trip_assignment\assigned_eq.gpkg|layername=assigned_eq", "a", "ogr")
    log("assigned feats:", asg.featureCount())
    # graduated: width + color by vol_pcu (quantile)
    r = QgsGraduatedSymbolRenderer('vol_pcu')
    r.setSourceSymbol(QgsLineSymbol.createSimple({'color': '#888', 'width': '0.2'}))
    r.setClassificationMethod(QgsClassificationQuantile())
    r.updateClasses(asg, 6)
    r.updateColorRamp(QgsGradientColorRamp(QColor('#ffd54f'), QColor('#b71c1c')))
    widths = [0.1, 0.3, 0.6, 1.0, 1.6, 2.6]
    for i, rng in enumerate(r.ranges()):
        s = rng.symbol().clone(); s.setWidth(widths[min(i, len(widths)-1)]); r.updateRangeSymbol(i, s)
    asg.setRenderer(r)

    ms = QgsMapSettings(); ms.setLayers([asg, taz]); ms.setBackgroundColor(QColor('white'))
    ms.setOutputSize(QSize(800, 820)); ms.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32647'))
    ext = taz.extent(); ext.scale(1.05); ms.setExtent(ext)
    img = QImage(QSize(800, 820), QImage.Format_ARGB32); img.fill(QColor('white'))
    p = QPainter(img); job = QgsMapRendererCustomPainterJob(ms, p); job.renderSynchronously(); p.end()
    img.save(B + r"\output\assigned_eq_traffic.png"); log("rendered")
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
