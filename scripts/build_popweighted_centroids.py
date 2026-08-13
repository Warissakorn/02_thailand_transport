# -*- coding: utf-8 -*-
"""centroid ถ่วงน้ำหนักประชากร (D3) จาก WorldPop:
  weighted centroid_z = ( Σ pop·lon / Σ pop , Σ pop·lat / Σ pop )  ต่อจังหวัด
แล้ว reproject 32647 + snap เข้าโครงข่ายถนน -> taz_centroids_snapped.gpkg (เขียนทับ)
รันผ่าน qpy.bat ; log -> output/_pwc.log
"""
import os, traceback, numpy as np
from osgeo import gdal, ogr
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsPointXY, QgsSpatialIndex, QgsVectorFileWriter, QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext, QgsProject, QgsCoordinateTransform)
from qgis.PyQt.QtCore import QVariant
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
LOG = open(B + r"\output\_pwc.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

try:
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()

    # 1) provinces -> 4326 with zone_id (taz_provinces เป็น 32647)
    taz = QgsVectorLayer(B + r"\data\zones_taz\taz_provinces.gpkg|layername=taz_provinces", "t", "ogr")
    taz4326 = processing.run("native:reprojectlayer", {'INPUT': taz,
        'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326'), 'OUTPUT': 'memory:'})['OUTPUT']
    tmp = B + r"\output\_taz4326.gpkg"
    if os.path.exists(tmp): os.remove(tmp)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "t"
    QgsVectorFileWriter.writeAsVectorFormatV3(taz4326, tmp, QgsCoordinateTransformContext(), o)
    names = {f['zone_id']: f['NAME_1'] for f in taz.getFeatures()}

    # 2) rasterize zone_id ลงกริดเดียวกับ pop
    pop = gdal.Open(B + r"\data\raw\tha_pop_2020_100m.tif")
    gt = pop.GetGeoTransform(); W = pop.RasterXSize; H = pop.RasterYSize
    nodata = pop.GetRasterBand(1).GetNoDataValue()
    zr = gdal.GetDriverByName('GTiff').Create(B + r"\output\_zone.tif", W, H, 1, gdal.GDT_Int16)
    zr.SetGeoTransform(gt); zr.SetProjection(pop.GetProjection()); zr.GetRasterBand(1).SetNoDataValue(0)
    src = ogr.Open(tmp); lyr = src.GetLayer(0)
    gdal.RasterizeLayer(zr, [1], lyr, options=["ATTRIBUTE=zone_id"]); zr.FlushCache()
    log("rasterized zones grid %dx%d" % (W, H))

    # 3) block accumulate Σpop, Σpop·lon, Σpop·lat
    pb = pop.GetRasterBand(1); zb = zr.GetRasterBand(1)
    N = 78
    spop = np.zeros(N); spx = np.zeros(N); spy = np.zeros(N)
    lon0 = gt[0] + 0.5*gt[1]; lat0 = gt[3] + 0.5*gt[5]
    lons = lon0 + np.arange(W)*gt[1]
    STEP = 500
    for r0 in range(0, H, STEP):
        nr = min(STEP, H-r0)
        p = pb.ReadAsArray(0, r0, W, nr).astype(np.float64)
        z = zb.ReadAsArray(0, r0, W, nr).astype(np.int32)
        if nodata is not None: p[p == nodata] = 0
        p[p < 0] = 0
        lats = lat0 + (np.arange(r0, r0+nr))*gt[5]
        LON = np.broadcast_to(lons, (nr, W))
        LAT = np.broadcast_to(lats[:, None], (nr, W))
        zf = z.ravel(); pf = p.ravel()
        m = (zf > 0) & (pf > 0)
        zf = zf[m]; pf = pf[m]
        spop += np.bincount(zf, weights=pf, minlength=N)
        spx  += np.bincount(zf, weights=pf*LON.ravel()[m], minlength=N)
        spy  += np.bincount(zf, weights=pf*LAT.ravel()[m], minlength=N)
    zr = None
    log("accumulated. total pop=%.0f" % spop.sum())

    # 4) centroids (4326) -> reproject 32647 -> snap to road
    ct = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),
                                QgsCoordinateReferenceSystem('EPSG:32647'), QgsProject.instance())
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    idx = QgsSpatialIndex(net.getFeatures()); nf = {f.id(): f for f in net.getFeatures()}

    snap = QgsVectorLayer("Point?crs=EPSG:32647", "taz_centroids_pw", "memory"); dp = snap.dataProvider()
    dp.addAttributes([QgsField('zone_id', QVariant.Int), QgsField('NAME_1', QVariant.String), QgsField('snap_m', QVariant.Double)])
    snap.updateFields()
    maxd = 0
    for z in range(1, N):
        if spop[z] <= 0: continue
        lon = spx[z]/spop[z]; lat = spy[z]/spop[z]
        pm = ct.transform(QgsPointXY(lon, lat))
        nn = idx.nearestNeighbor(pm, 5); bd = 1e18; bpt = None
        for nid in nn:
            d, mp, _, _ = nf[nid].geometry().closestSegmentWithContext(pm)
            if d < bd: bd = d; bpt = mp
        dist = bd**0.5; maxd = max(maxd, dist)
        f = QgsFeature(snap.fields()); f.setGeometry(QgsGeometry.fromPointXY(bpt))
        f.setAttributes([z, names.get(z, ""), round(dist, 1)]); dp.addFeature(f)
    out = B + r"\data\zones_taz\taz_centroids_pw.gpkg"
    if os.path.exists(out): os.remove(out)
    o2 = QgsVectorFileWriter.SaveVectorOptions(); o2.driverName = "GPKG"; o2.layerName = "taz_centroids_pw"
    QgsVectorFileWriter.writeAsVectorFormatV3(snap, out, QgsCoordinateTransformContext(), o2)
    log("wrote pop-weighted snapped centroids: %d | max snap m: %.0f" % (snap.featureCount(), maxd))
    for cleanup in [tmp, B + r"\output\_zone.tif"]:
        try: os.remove(cleanup)
        except: pass
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์
except Exception:
    log("ERR", traceback.format_exc()); raise
