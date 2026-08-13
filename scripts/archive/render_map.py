# -*- coding: utf-8 -*-
"""Standalone PyQGIS renderer — รันผ่าน qpy.bat (เลี่ยง MCP ที่เปราะ)
ใช้: qpy.bat render_map.py <field> <gpkg> <layername> <out.png> <c0> <c1>
"""
import sys, os, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsGraduatedSymbolRenderer,
    QgsClassificationJenks, QgsGradientColorRamp, QgsMapSettings,
    QgsMapRendererCustomPainterJob)
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtCore import QSize

LOG = open(os.path.join(os.path.dirname(__file__), "..", "output", "_render.log"), "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

try:
    app = QgsApplication([], False)
    app.initQgis()
    log("argv:", sys.argv[1:])
    field, gpkg, layername, out, c0, c1 = sys.argv[1:7]
    lyr = QgsVectorLayer(gpkg + "|layername=" + layername, "l", "ogr")
    assert lyr.isValid(), "invalid layer: " + gpkg
    log("features:", lyr.featureCount())

    from qgis.core import QgsFillSymbol
    r = QgsGraduatedSymbolRenderer(field)
    r.setSourceSymbol(QgsFillSymbol.createSimple({'color': '#cccccc', 'outline_color': '#ffffff', 'outline_width': '0.2'}))
    r.setClassificationMethod(QgsClassificationJenks())
    log("classifying...")
    r.updateClasses(lyr, 5)
    log("classes:", len(r.ranges()))
    log("applying ramp")
    r.updateColorRamp(QgsGradientColorRamp(QColor(c0), QColor(c1)))
    log("ramp applied")
    lyr.setRenderer(r)
    log("renderer set, starting render")

    ms = QgsMapSettings(); ms.setLayers([lyr]); ms.setBackgroundColor(QColor('white'))
    ms.setOutputSize(QSize(850, 650)); ms.setDestinationCrs(lyr.crs())
    ext = lyr.extent(); ext.scale(1.05); ms.setExtent(ext)
    img = QImage(QSize(850, 650), QImage.Format_ARGB32)
    img.fill(QColor('white'))
    painter = QPainter(img)
    job = QgsMapRendererCustomPainterJob(ms, painter)
    job.renderSynchronously()
    painter.end()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    ok = img.save(out)
    log("saved:", ok, "->", out)
    app.exitQgis()
    log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
