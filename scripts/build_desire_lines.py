# -*- coding: utf-8 -*-
"""สร้าง desire lines จาก OD trip matrix + เรนเดอร์แผนที่ (เส้นหนา ∝ จำนวนเที่ยว)
out: model/2_trip_distribution/desire_{passenger,freight}.gpkg + output/desire_*.png
รันผ่าน qpy.bat ; log -> output/_dl.log
"""
import os, csv, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsPointXY, QgsVectorFileWriter, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,
    QgsMapSettings, QgsMapRendererCustomPainterJob, QgsLineSymbol, QgsFillSymbol,
    QgsProperty, QgsSymbolLayer)
from qgis.PyQt.QtCore import QVariant, QSize
from qgis.PyQt.QtGui import QColor, QImage, QPainter

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT
B = _ROOT
LOG = open(B + r"\output\_dl.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

try:
    app = QgsApplication([], False); app.initQgis()
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    pt = {f['zone_id']: f.geometry().asPoint() for f in cen.getFeatures()}
    taz = QgsVectorLayer(B + r"\data\zones_taz\taz_provinces.gpkg|layername=taz_provinces", "t", "ogr")
    taz.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'#fafafa','outline_color':'#e0e0e0','outline_width':'0.2'}))

    for stream, col in [("passenger", "#1565c0"), ("freight", "#2e7d32")]:
        flows = []
        for r in csv.DictReader(open(B + r"\model\2_trip_distribution\od_%s.csv" % stream, encoding="utf-8")):
            o = int(r['orig_zone']); d = int(r['dest_zone']); v = float(r['trips'])
            if o < d:  # undirected, รวมสองทาง
                pass
            if o != d and v > 0:
                flows.append((o, d, v))
        # รวมสองทิศ (o,d)+(d,o)
        agg = {}
        for o, d, v in flows:
            k = (min(o, d), max(o, d)); agg[k] = agg.get(k, 0) + v
        items = sorted(agg.items(), key=lambda x: -x[1])
        top = items[:300]   # 300 เส้นหนาสุด (เห็นการเชื่อมโยงครบขึ้น)
        mx = top[0][1]
        lyr = QgsVectorLayer("LineString?crs=EPSG:32647", "desire_%s" % stream, "memory"); dp = lyr.dataProvider()
        dp.addAttributes([QgsField('o', QVariant.Int), QgsField('d', QVariant.Int), QgsField('trips', QVariant.Double)])
        lyr.updateFields()
        for (o, d), v in top:
            f = QgsFeature(lyr.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(pt[o]), QgsPointXY(pt[d])]))
            f.setAttributes([o, d, round(v)]); dp.addFeature(f)
        out = B + r"\model\2_trip_distribution\desire_%s.gpkg" % stream
        try:
            if os.path.exists(out): os.remove(out)
            opt = QgsVectorFileWriter.SaveVectorOptions(); opt.driverName = "GPKG"; opt.layerName = "desire_%s" % stream
            QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out, QgsCoordinateTransformContext(), opt)
            log("saved", os.path.basename(out))
        except Exception as e:
            log("save SKIPPED (locked?):", str(e)[:60])

        # style: width ∝ trips (data-defined), สี + โปร่งแสง
        sym = QgsLineSymbol.createSimple({'color': col, 'width': '0.3'})
        sl = sym.symbolLayer(0)
        sl.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeWidth,
            QgsProperty.fromExpression('0.2 + "trips"/%f*4.0' % mx))
        c = QColor(col); c.setAlpha(150); sym.setColor(c)
        lyr.renderer().setSymbol(sym)

        ms = QgsMapSettings(); ms.setLayers([lyr, taz]); ms.setBackgroundColor(QColor('white'))
        ms.setOutputSize(QSize(760, 820)); ms.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:32647'))
        ext = taz.extent(); ext.scale(1.05); ms.setExtent(ext)
        img = QImage(QSize(760, 820), QImage.Format_ARGB32); img.fill(QColor('white'))
        p = QPainter(img); job = QgsMapRendererCustomPainterJob(ms, p); job.renderSynchronously(); p.end()
        img.save(B + r"\output\desire_%s.png" % stream)
        log("%s: %d OD pairs, top120 max trips=%s -> rendered" % (stream, len(items), format(int(mx), ',')))
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
