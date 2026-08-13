# -*- coding: utf-8 -*-
"""(a) clean rail network -> data/network/rail_clean.gpkg (EPSG:32647 + speed/travel_min)
   (b) render multimodal overview -> output/multimodal_overview.png
รันผ่าน qpy.bat ; log -> output/_mm.log
"""
import os, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsProject,
    QgsMapSettings, QgsMapRendererCustomPainterJob, QgsLineSymbol, QgsMarkerSymbol, QgsFillSymbol)
from qgis.PyQt.QtCore import QVariant, QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter
import processing
from processing.core.Processing import Processing

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit
B = _ROOT
LOG = open(B + r"\output\_mm.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

RAIL_SPD = {'rail':80,'light_rail':40,'narrow_gauge':60}

try:
    app = QgsApplication([], False); app.initQgis()
    Processing.initialize()

    # (a) rail clean
    rail = QgsVectorLayer(B+r"\inputs\multimodal\rail_lines.gpkg|layername=rail_lines","rail","ogr")
    rep = processing.run("native:reprojectlayer",{'INPUT':rail,
        'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:32647'),'OUTPUT':'memory:'})['OUTPUT']
    rep.startEditing()
    for n,t in [('length_m',QVariant.Double),('speed_kmh',QVariant.Double),('travel_min',QVariant.Double)]:
        rep.addAttribute(QgsField(n,t))
    rep.updateFields()
    fi={n:rep.fields().indexOf(n) for n in ['length_m','speed_kmh','travel_min']}
    rwi=rep.fields().indexOf('railway')
    for f in rep.getFeatures():
        L=f.geometry().length(); spd=RAIL_SPD.get(f['railway'],70)
        rep.changeAttributeValue(f.id(),fi['length_m'],round(L,1))
        rep.changeAttributeValue(f.id(),fi['speed_kmh'],spd)
        rep.changeAttributeValue(f.id(),fi['travel_min'],round(L/1000.0/spd*60.0,4))
    rep.commitChanges()
    out=B+r"\data\network\rail_clean.gpkg"
    if os.path.exists(out): os.remove(out)
    o=QgsVectorFileWriter.SaveVectorOptions(); o.driverName="GPKG"; o.layerName="rail_clean"
    QgsVectorFileWriter.writeAsVectorFormatV3(rep,out,QgsCoordinateTransformContext(),o)
    log("rail_clean:",rep.featureCount())

    # (b) render multimodal overview
    def L(rel,ln):
        l=QgsVectorLayer(B+"\\"+rel+"|layername="+ln,ln,"ogr"); log(ln,l.isValid(),l.featureCount()); return l
    taz=L(r"data\zones_taz\taz_provinces.gpkg","taz_provinces")
    road=L(r"data\network\network_clean.gpkg","network_clean")
    railc=QgsVectorLayer(out+"|layername=rail_clean","rail_clean","ogr")
    ferry=L(r"inputs\multimodal\ferry_routes.gpkg","ferry_routes")
    alink=L(r"data\multimodal\air_links.gpkg","air_links")
    anode=L(r"data\multimodal\air_nodes.gpkg","air_nodes")
    ports=L(r"inputs\multimodal\ports.gpkg","ports")

    taz.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'0,0,0,0','outline_color':'#bdbdbd','outline_width':'0.2'}))
    road.renderer().setSymbol(QgsLineSymbol.createSimple({'color':'#e0e0e0','width':'0.1'}))
    railc.renderer().setSymbol(QgsLineSymbol.createSimple({'color':'#c62828','width':'0.5'}))
    ferry.renderer().setSymbol(QgsLineSymbol.createSimple({'color':'#0097a7','width':'0.4'}))
    alink.renderer().setSymbol(QgsLineSymbol.createSimple({'color':'#1565c0','width':'0.3'}))
    anode.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':'circle','color':'#1565c0','outline_color':'white','outline_width':'0.3','size':'2.4'}))
    ports.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':'circle','color':'#0097a7','outline_color':'white','outline_width':'0.1','size':'0.9'}))

    layers=[anode,ports,alink,railc,ferry,road,taz]  # draw order top->bottom
    ms=QgsMapSettings(); ms.setLayers(layers); ms.setBackgroundColor(QColor('white'))
    ms.setOutputSize(QSize(850,650)); ms.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32647'))
    ext=taz.extent(); ext.scale(1.05); ms.setExtent(ext)
    img=QImage(QSize(850,650),QImage.Format_ARGB32); img.fill(QColor('white'))
    pt=QPainter(img); job=QgsMapRendererCustomPainterJob(ms,pt); job.renderSynchronously(); pt.end()
    img.save(B+r"\output\multimodal_overview.png"); log("rendered overview")
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์
except Exception:
    log("ERR",traceback.format_exc())
