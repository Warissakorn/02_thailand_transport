# -*- coding: utf-8 -*-
"""ขั้น 7b: เทียบโมเดลกับ AADT + ปรับสเกล + GEH
snap สถานี AADT -> assigned_network ใกล้สุด -> modeled PCU
fit k (least-squares through origin) ; calibrated = k*modeled ; GEH per station
out: model/5_calibration/aadt_compare.gpkg + calibration_report.txt ; log -> output/_cal.log
รันผ่าน qpy.bat
"""
import os, sys, math, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsPointXY, QgsSpatialIndex, QgsVectorFileWriter, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant

# argv: [gpkg_rel, layername, tag]   default = all-or-nothing
ASSIGN_REL = sys.argv[1] if len(sys.argv) > 1 else r"4_trip_assignment\assigned_network.gpkg"
ASSIGN_LN  = sys.argv[2] if len(sys.argv) > 2 else "assigned_network"
TAG        = sys.argv[3] if len(sys.argv) > 3 else "aon"

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_cal.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
TOL = 1500.0  # ม. ระยะ snap สูงสุด

def geh(m, c):
    return math.sqrt(2*(m-c)**2/(m+c)) if (m+c) > 0 else 0.0

try:
    app = QgsApplication([], False); app.initQgis()
    aadt = QgsVectorLayer(B + r"\model\5_calibration\aadt_points.gpkg|layername=aadt_points", "a", "ogr")
    asg = QgsVectorLayer(B + "\\model\\" + ASSIGN_REL + "|layername=" + ASSIGN_LN, "s", "ogr")
    idx = QgsSpatialIndex(asg.getFeatures()); amap = {f.id(): f for f in asg.getFeatures()}
    log("aadt:", aadt.featureCount(), "assigned:", asg.featureCount())

    pairs = []  # (modeled, observed, feature)
    snapped = 0
    out = QgsVectorLayer("Point?crs=EPSG:32647", "aadt_compare", "memory"); dp = out.dataProvider()
    dp.addAttributes([QgsField('route', QVariant.String), QgsField('aadt', QVariant.Double),
                      QgsField('modeled', QVariant.Double), QgsField('calibrated', QVariant.Double),
                      QgsField('geh', QVariant.Double)])
    out.updateFields()
    tmp = []
    for f in aadt.getFeatures():
        p = f.geometry().asPoint()
        nn = idx.nearestNeighbor(QgsPointXY(p), 1)
        if not nn: continue
        seg = amap[nn[0]]
        d = seg.geometry().distance(f.geometry())
        if d > TOL: continue
        m = seg['vol_pcu']
        if m and m > 0:
            pairs.append((m, f['aadt'])); snapped += 1
            tmp.append((f['route'], f['aadt'], m, p))
    log("snapped within %dm with modeled>0: %d" % (TOL, snapped))

    # fit k (least squares through origin): k = ΣMC/ΣM²
    SMC = sum(m*c for m, c in pairs); SMM = sum(m*m for m, c in pairs)
    k = SMC/SMM if SMM > 0 else 0.0
    ratios = sorted(c/m for m, c in pairs)
    k_med = ratios[len(ratios)//2]
    log("scale k (LS)=%.5g | k (median ratio)=%.5g" % (k, k_med))

    # GEH with calibrated = k*modeled
    gehs = []
    for route, c, m, p in tmp:
        cal = k*m; g = geh(cal, c); gehs.append(g)
        ft = QgsFeature(out.fields()); ft.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(p)))
        ft.setAttributes([route, round(c), round(cal), round(g, 2)]); dp.addFeature(ft)
    o = B + r"\model\5_calibration\aadt_compare_%s.gpkg" % TAG
    if os.path.exists(o): os.remove(o)
    opt = QgsVectorFileWriter.SaveVectorOptions(); opt.driverName = "GPKG"; opt.layerName = "aadt_compare"
    QgsVectorFileWriter.writeAsVectorFormatV3(out, o, QgsCoordinateTransformContext(), opt)

    import statistics
    pass5 = sum(1 for g in gehs if g < 5)/len(gehs)*100
    pass10 = sum(1 for g in gehs if g < 10)/len(gehs)*100
    # R^2 of calibrated vs observed
    obs = [c for m, c in pairs]; cal = [k*m for m, c in pairs]
    mo = statistics.mean(obs); sstot = sum((c-mo)**2 for c in obs); ssres = sum((c-ca)**2 for c, ca in zip(obs, cal))
    r2 = 1 - ssres/sstot if sstot > 0 else 0
    rmse = (ssres/len(obs))**0.5
    rep = ("=== Calibration report (AADT %d) ===\n"
           "stations compared: %d\n"
           "scale factor k (least-squares) = %.5g\n"
           "GEH < 5  : %.1f%%   (target 85%%)\n"
           "GEH < 10 : %.1f%%\n"
           "median GEH: %.1f\n"
           "R^2 = %.3f | RMSE = %.0f veh/day\n" % (
            2565, len(gehs), k, pass5, pass10, statistics.median(gehs), r2, rmse))
    open(B + r"\model\5_calibration\calibration_report_%s.txt" % TAG, "w", encoding="utf-8").write(rep)
    log(rep)
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
