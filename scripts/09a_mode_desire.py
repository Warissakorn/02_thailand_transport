# -*- coding: utf-8 -*-
"""ขั้น 9a: desire line แยกตามโหมด (อากาศ/น้ำ/ราง) และสาย (คน/สินค้า)
จาก mode_split_*.csv (province OD) ; เส้นระหว่าง centroid จังหวัด ; width ∝ trips
out: model/3_mode_choice/desire_<stream>_<mode>.gpkg ; log -> output/_md.log
รันผ่าน qpy.bat
"""
import os, csv, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_trip"  # placeholder fixed below
B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"; M = B + r"\model"
LOG = open(B + r"\output\_md.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

TARGETS = [  # (stream_csv, mode, outname)
    ("mode_split_passenger.csv", "rail",  "desire_pax_rail"),
    ("mode_split_passenger.csv", "air",   "desire_pax_air"),
    ("mode_split_passenger.csv", "water", "desire_pax_water"),
    ("mode_split_freight.csv",   "rail",  "desire_frg_rail"),
    ("mode_split_freight.csv",   "water", "desire_frg_water"),
]

def main():
    app = QgsApplication([], False); app.initQgis()
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    pt = {f['zone_id']: f.geometry().asPoint() for f in cen.getFeatures()}
    for csvf, mode, outname in TARGETS:
        agg = {}
        for r in csv.DictReader(open(M + r"\3_mode_choice\\" + csvf, encoding="utf-8")):
            if r['mode'] != mode: continue
            o = int(r['orig_zone']); d = int(r['dest_zone']); v = float(r['trips'])
            if o == d or v <= 0: continue
            k = (min(o, d), max(o, d)); agg[k] = agg.get(k, 0.0) + v
        lyr = QgsVectorLayer("LineString?crs=EPSG:32647", outname, "memory"); dp = lyr.dataProvider()
        dp.addAttributes([QgsField('o', QVariant.Int), QgsField('d', QVariant.Int), QgsField('trips', QVariant.Double)])
        lyr.updateFields()
        for (o, d), v in sorted(agg.items(), key=lambda x: -x[1]):
            if o not in pt or d not in pt: continue
            f = QgsFeature(lyr.fields()); f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(pt[o]), QgsPointXY(pt[d])]))
            f.setAttributes([o, d, round(v, 1)]); dp.addFeature(f)
        out = M + r"\3_mode_choice\\" + outname + ".gpkg"
        try:
            if os.path.exists(out): os.remove(out)
            opt = QgsVectorFileWriter.SaveVectorOptions(); opt.driverName = "GPKG"; opt.layerName = outname
            QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out, QgsCoordinateTransformContext(), opt)
            log("%s: %d OD pairs, total trips=%.0f" % (outname, lyr.featureCount(), sum(v for v in agg.values())))
        except Exception as e:
            log("%s SAVE FAIL: %s" % (outname, str(e)[:50]))
    app.exitQgis(); log("DONE")

try: main()
except Exception: log("ERR", traceback.format_exc())
