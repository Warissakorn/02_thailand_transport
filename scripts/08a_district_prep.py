# -*- coding: utf-8 -*-
"""ขั้น B-1: เตรียมโมเดลระดับอำเภอ (GADM ADM_2 = 928)
- district TAZ (32647) + district_id
- centroid ถ่วงประชากร (WorldPop) + snap backbone
- trip generation P/A (pax+freight) ต่ออำเภอ
out: data/zones_taz/district_taz.gpkg, district_centroids.gpkg ; model/1_trip_generation/district_tripgen.csv
รันผ่าน qpy.bat ; log -> output/_d8a.log
"""
import os, sys, csv, traceback, numpy as np
from osgeo import gdal, ogr
# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit
sys.path.insert(0, (_ROOT + r"\config"))
import model_params as mp
from lib import scenario as sc
sc.apply(mp)      # ทับด้วย inputs/scenarios/<TT_SCENARIO>.yaml
import processing
from processing.core.Processing import Processing
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsSpatialIndex, QgsVectorFileWriter, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,
    QgsProject, QgsCoordinateTransform, QgsFeatureRequest)
from qgis.PyQt.QtCore import QVariant

B = _ROOT
LOG = open(B + r"\output\_d8a.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
BACKBONE = ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link')

def main():
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()
    from lib import boundaries as bd     # GADM หลัก / OSM สำรอง

    # 1) district TAZ 32647 + district_id
    adm2 = QgsVectorLayer(bd.adm2_uri(), "d", "ogr")
    assert adm2.isValid(), "ไม่พบชั้นอำเภอ: %s" % bd.adm2_uri()
    log("ที่มาขอบเขต:", bd.read_source() or bd.source())
    rep = processing.run("native:reprojectlayer", {'INPUT': adm2, 'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']
    rep.startEditing(); rep.addAttribute(QgsField('district_id', QVariant.Int)); rep.updateFields()
    di = rep.fields().indexOf('district_id')
    feats = sorted(rep.getFeatures(), key=lambda f: f['GID_2'])
    gid2did = {}
    for i, f in enumerate(feats, 1):
        rep.changeAttributeValue(f.id(), di, i); gid2did[f['GID_2']] = i
    rep.commitChanges()
    out_taz = B + r"\data\zones_taz\district_taz.gpkg"
    if os.path.exists(out_taz): os.remove(out_taz)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "district_taz"
    QgsVectorFileWriter.writeAsVectorFormatV3(rep, out_taz, QgsCoordinateTransformContext(), o)
    N = len(feats); log("districts:", N)

    # 2) pop-weighted centroid via raster accumulation (rasterize district_id onto pop grid)
    adm2_4326 = processing.run("native:reprojectlayer", {'INPUT': rep, 'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:4326'), 'OUTPUT': 'memory:'})['OUTPUT']
    tmp = B + r"\output\_d4326.gpkg"
    if os.path.exists(tmp): os.remove(tmp)
    QgsVectorFileWriter.writeAsVectorFormatV3(adm2_4326, tmp, QgsCoordinateTransformContext(), o)
    pop = gdal.Open(B + r"\data\raw\tha_pop_2020_100m.tif"); gt = pop.GetGeoTransform(); W = pop.RasterXSize; H = pop.RasterYSize
    nodata = pop.GetRasterBand(1).GetNoDataValue()
    zr = gdal.GetDriverByName('GTiff').Create(B + r"\output\_dzone.tif", W, H, 1, gdal.GDT_Int32)
    zr.SetGeoTransform(gt); zr.SetProjection(pop.GetProjection()); zr.GetRasterBand(1).SetNoDataValue(0)
    src = ogr.Open(tmp); gdal.RasterizeLayer(zr, [1], src.GetLayer(0), options=["ATTRIBUTE=district_id"]); zr.FlushCache()
    pb = pop.GetRasterBand(1); zb = zr.GetRasterBand(1)
    NA = N + 1; spop = np.zeros(NA); spx = np.zeros(NA); spy = np.zeros(NA)
    lons = (gt[0] + 0.5*gt[1]) + np.arange(W)*gt[1]; lat0 = gt[3] + 0.5*gt[5]
    for r0 in range(0, H, 500):
        nr = min(500, H-r0)
        p = pb.ReadAsArray(0, r0, W, nr).astype(np.float64); z = zb.ReadAsArray(0, r0, W, nr).astype(np.int32)
        if nodata is not None: p[p == nodata] = 0
        p[p < 0] = 0
        lats = lat0 + np.arange(r0, r0+nr)*gt[5]
        LON = np.broadcast_to(lons, (nr, W)); LAT = np.broadcast_to(lats[:, None], (nr, W))
        zf = z.ravel(); pf = p.ravel(); m = (zf > 0) & (pf > 0); zf = zf[m]; pf = pf[m]
        spop += np.bincount(zf, weights=pf, minlength=NA); spx += np.bincount(zf, weights=pf*LON.ravel()[m], minlength=NA); spy += np.bincount(zf, weights=pf*LAT.ravel()[m], minlength=NA)
    zr = None
    log("pop accumulated, total=%.0f" % spop.sum())

    # snap centroids to backbone
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    req = QgsFeatureRequest().setFilterExpression("highway IN ('%s')" % "','".join(BACKBONE))
    bb = [f for f in net.getFeatures(req)]; bidx = QgsSpatialIndex(); bidx.addFeatures(bb); bmap = {f.id(): f for f in bb}
    ct = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'), QgsCoordinateReferenceSystem('EPSG:32647'), QgsProject.instance())
    cen = QgsVectorLayer("Point?crs=EPSG:32647", "district_centroids", "memory"); dp = cen.dataProvider()
    dp.addAttributes([QgsField('district_id', QVariant.Int)]); cen.updateFields()
    # fallback: geometric centroid for districts with 0 pop
    geomc = {f['district_id']: f.geometry().centroid().asPoint() for f in rep.getFeatures()}
    for d in range(1, NA):
        if spop[d] > 0:
            pm = ct.transform(QgsPointXY(spx[d]/spop[d], spy[d]/spop[d]))
        else:
            pm = QgsPointXY(geomc[d])
        bd = 1e18; bpt = pm
        for fid in bidx.nearestNeighbor(pm, 5):
            dd, mp_, _, _ = bmap[fid].geometry().closestSegmentWithContext(pm)
            if dd < bd: bd = dd; bpt = mp_
        f = QgsFeature(cen.fields()); f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(bpt))); f.setAttributes([d]); dp.addFeature(f)
    out_cen = B + r"\data\zones_taz\district_centroids.gpkg"
    if os.path.exists(out_cen): os.remove(out_cen)
    ocen = QgsVectorFileWriter.SaveVectorOptions(); ocen.driverName = "GPKG"; ocen.layerName = "district_centroids"
    QgsVectorFileWriter.writeAsVectorFormatV3(cen, out_cen, QgsCoordinateTransformContext(), ocen)
    log("centroids written:", cen.featureCount())

    # 3) trip generation: schools + industrial per district
    def cnt(points):
        res = processing.run("native:countpointsinpolygon", {'POLYGONS': rep, 'POINTS': points, 'FIELD': 'NP', 'OUTPUT': 'memory:'})['OUTPUT']
        return {f['district_id']: (f['NP'] or 0) for f in res.getFeatures()}
    spoly = processing.run("native:fixgeometries", {'INPUT': QgsVectorLayer(B + r"\inputs\landuse\schools_poly.gpkg|layername=schools_poly", "sp", "ogr"), 'OUTPUT': 'memory:'})['OUTPUT']
    scen = processing.run("native:centroids", {'INPUT': spoly, 'OUTPUT': 'memory:'})['OUTPUT']
    spts = QgsVectorLayer(B + r"\inputs\landuse\schools_pts.gpkg|layername=schools_pts", "spt", "ogr")
    sc1 = cnt(scen); sc2 = cnt(spts); sch = {d: sc1.get(d, 0)+sc2.get(d, 0) for d in range(1, NA)}
    ind_src = processing.run("native:fixgeometries", {'INPUT': QgsVectorLayer(B + r"\inputs\landuse\industrial.gpkg|layername=industrial", "ind", "ogr"), 'OUTPUT': 'memory:'})['OUTPUT']
    ind_src = processing.run("native:reprojectlayer", {'INPUT': ind_src, 'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']
    inter = processing.run("native:intersection", {'INPUT': ind_src, 'OVERLAY': rep, 'OUTPUT': 'memory:'})['OUTPUT']
    ind = {d: 0.0 for d in range(1, NA)}
    for f in inter.getFeatures(): ind[f['district_id']] = ind.get(f['district_id'], 0.0) + f.geometry().area()/1e6

    pop = {d: spop[d] for d in range(1, NA)}
    Spop = sum(pop.values()) or 1; Ssch = sum(sch.values()) or 1; Sind = sum(ind.values()) or 1
    RP = mp.TRIP_RATE_PAX; FF = mp.FREIGHT_FACTOR
    SP = sum(pop[d]*RP for d in pop); T_F = FF*SP
    out_csv = B + r"\model\1_trip_generation\district_tripgen.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["district_id", "pop", "n_school", "ind_km2", "P_pax", "A_pax", "P_frg", "A_frg"])
        for d in range(1, NA):
            ps = pop[d]/Spop; ss = sch[d]/Ssch; isr = ind[d]/Sind
            P_pax = pop[d]*RP; A_pax = SP*(0.7*ps+0.3*ss); P_frg = T_F*(0.8*isr+0.2*ps); A_frg = T_F*(0.5*isr+0.5*ps)
            w.writerow([d, round(pop[d]), sch[d], round(ind[d], 3), round(P_pax, 1), round(A_pax, 1), round(P_frg, 1), round(A_frg, 1)])
    log("tripgen written | totals: pop=%.0f schools=%d ind=%.0f P_pax=%.0f T_F=%.0f" % (Spop, sum(sch.values()), Sind, SP, T_F))
    for c in [tmp, B + r"\output\_dzone.tif"]:
        try: os.remove(c)
        except: pass
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์

try: main()
except Exception: log("ERR", traceback.format_exc()); raise
