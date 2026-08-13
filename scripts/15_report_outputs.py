# -*- coding: utf-8 -*-
"""ขั้น 15: ผลลัพธ์พร้อมใส่รายงาน -> output/report/{tables,figures}
ตาราง: T1 trip gen รายจังหวัด, T2 mode share vs เป้า, T3 เทียบ calibration ทุก variant,
       T4 พารามิเตอร์+ที่มา, T5 สถิติ assignment สุดท้าย
รูป (A4 300dpi + legend/scalebar/north/CRS): F1 พื้นที่ศึกษา, F2 โครงข่าย multimodal,
       F3 trip gen, F4 ปริมาณจราจรสุดท้าย, F5 components คน/สินค้า, F6 แผนที่ GEH
log -> output/_15.log ; รันผ่าน qpy.bat (background)
"""
import os, sys, csv, math, traceback
import numpy as np
# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit
B = _ROOT
sys.path.insert(0, B + r"\scripts"); sys.path.insert(0, B + r"\config")
M = B + r"\model"; RT = B + r"\output\report\tables"; RF = B + r"\output\report\figures"
LOG = open(B + r"\output\_15.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def geh(m, c): return math.sqrt(2*(m-c)**2/(m+c)) if (m+c) > 0 else 0.0

def make_layout(project, title, layers, extent, out_png,
                legend_layers=None, dpi=300):
    """A4 แนวตั้ง: แผนที่ + ชื่อ + legend + scalebar + ลูกศรเหนือ + CRS"""
    from qgis.core import (QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
        QgsLayoutItemScaleBar, QgsLayoutItemLabel, QgsLayoutPoint, QgsLayoutSize,
        QgsUnitTypes, QgsLayoutExporter, QgsLegendStyle)
    from qgis.PyQt.QtGui import QFont
    lay = QgsPrintLayout(project); lay.initializeDefaults()
    page = lay.pageCollection().page(0)
    page.setPageSize('A4', 1)  # portrait
    mp = QgsLayoutItemMap(lay); mp.setRect(20, 20, 20, 20)
    mp.setLayers(layers); mp.zoomToExtent(extent)
    mp.attemptMove(QgsLayoutPoint(10, 22, QgsUnitTypes.LayoutMillimeters))
    mp.attemptResize(QgsLayoutSize(190, 235, QgsUnitTypes.LayoutMillimeters))
    mp.setFrameEnabled(True); lay.addLayoutItem(mp)
    ti = QgsLayoutItemLabel(lay); ti.setText(title)
    ti.setFont(QFont('Tahoma', 15)); ti.adjustSizeToText()
    ti.attemptMove(QgsLayoutPoint(10, 8, QgsUnitTypes.LayoutMillimeters)); lay.addLayoutItem(ti)
    lg = QgsLayoutItemLegend(lay); lg.setLinkedMap(mp)
    lg.setAutoUpdateModel(False)
    root = lg.model().rootGroup(); root.clear()
    for l in (legend_layers or layers):
        root.addLayer(l)
    lg.setStyleFont(QgsLegendStyle.SymbolLabel, QFont('Tahoma', 8))
    lg.attemptMove(QgsLayoutPoint(12, 200, QgsUnitTypes.LayoutMillimeters))
    lg.setBackgroundEnabled(True); lay.addLayoutItem(lg)
    sb = QgsLayoutItemScaleBar(lay); sb.setLinkedMap(mp); sb.applyDefaultSize()
    sb.setStyle('Single Box'); sb.setUnits(QgsUnitTypes.DistanceKilometers)
    sb.setUnitLabel('กม.'); sb.setUnitsPerSegment(100); sb.setNumberOfSegments(2)
    sb.attemptMove(QgsLayoutPoint(120, 250, QgsUnitTypes.LayoutMillimeters)); lay.addLayoutItem(sb)
    na = QgsLayoutItemLabel(lay); na.setText('▲\nN'); na.setFont(QFont('Tahoma', 13))
    na.adjustSizeToText(); na.attemptMove(QgsLayoutPoint(185, 26, QgsUnitTypes.LayoutMillimeters))
    lay.addLayoutItem(na)
    cr = QgsLayoutItemLabel(lay); cr.setText('CRS: EPSG:32647 (WGS84/UTM 47N) · ข้อมูล: ดู DATA_SOURCES.md')
    cr.setFont(QFont('Tahoma', 7)); cr.adjustSizeToText()
    cr.attemptMove(QgsLayoutPoint(10, 262, QgsUnitTypes.LayoutMillimeters)); lay.addLayoutItem(cr)
    exp = QgsLayoutExporter(lay)
    st = QgsLayoutExporter.ImageExportSettings(); st.dpi = dpi
    exp.exportToImage(out_png, st)
    log("figure:", os.path.basename(out_png))

def main():
    from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsSpatialIndex,
        QgsFeature, QgsGraduatedSymbolRenderer, QgsClassificationQuantile, QgsClassificationJenks,
        QgsGradientColorRamp, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
        QgsRendererRange, QgsCoordinateReferenceSystem)
    from qgis.PyQt.QtGui import QColor
    import calibrated_params as cp
    app = QgsApplication([], False); app.initQgis()
    os.makedirs(RT, exist_ok=True); os.makedirs(RF, exist_ok=True)
    proj = QgsProject.instance()
    proj.setCrs(QgsCoordinateReferenceSystem('EPSG:32647'))

    def V(path, ln, title):
        l = QgsVectorLayer(path + "|layername=" + ln, title, "ogr")
        proj.addMapLayer(l, False); return l

    # ---------- T1 trip gen รายจังหวัด (scale calibrated) ----------
    dtaz = V(B + r"\data\zones_taz\district_taz.gpkg", "district_taz", "อำเภอ")
    d2prov = {f['district_id']: f['NAME_1'] for f in dtaz.getFeatures()}
    s_pax = cp.TRIP_RATE_PAX/2.0; s_frg = s_pax*(cp.FREIGHT_FACTOR/0.10)
    agg = {}
    for r in csv.DictReader(open(M + r"\1_trip_generation\district_tripgen.csv", encoding="utf-8")):
        pv = d2prov.get(int(r['district_id']), '?')
        a = agg.setdefault(pv, [0.0]*6)
        a[0] += float(r['pop']); a[1] += float(r['n_school']); a[2] += float(r['ind_km2'])
        a[3] += float(r['P_pax'])*s_pax; a[4] += float(r['P_frg'])*s_frg
        a[5] += 1
    with open(RT + r"\T1_trip_generation_by_province.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["province", "n_districts", "population", "schools", "industrial_km2",
                    "P_passenger_trips_day", "P_freight_trips_day"])
        for pv in sorted(agg):
            a = agg[pv]
            w.writerow([pv, int(a[5]), round(a[0]), int(a[1]), round(a[2], 1), round(a[3]), round(a[4])])
    log("T1 done")

    # ---------- T2 mode share (มีอยู่แล้วจาก 13 — คัดลอกเข้า report) ----------
    import shutil
    shutil.copy(M + r"\5_calibration\mode_share_calibrated.csv", RT + r"\T2_mode_share_vs_target.csv")
    shutil.copy(M + r"\5_calibration\calibration_search.csv", RT + r"\T3b_beta_search_curves.csv")

    # ---------- T4 parameters ----------
    with open(RT + r"\T4_parameters.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["parameter", "value", "unit", "source/method"])
        rows = [
            ("TRIP_RATE_PAX", cp.TRIP_RATE_PAX, "trips/person/day (strategic network)", "calibrated: LS scale vs AADT2565 pax-PCU"),
            ("FREIGHT_FACTOR", cp.FREIGHT_FACTOR, "-", "calibrated: LS scale vs AADT2565 frg-PCU"),
            ("BETA_PAX", cp.BETA_PAX, "1/min", "grid search vs AADT (R2 max)"),
            ("BETA_FRG", cp.BETA_FRG, "1/min", "grid search vs AADT"),
            ("VOT_GEN", cp.VOT_GEN*60, "baht/hr", "assumption (documented)"),
            ("VOT_BIZ", cp.VOT_BIZ*60, "baht/hr", "assumption; business segment"),
            ("BIZ_SHARE", cp.BIZ_SHARE, "-", "assumption"),
            ("THETA (logit)", 0.02, "1/min", "assumption"),
            ("K_FACTOR", 0.09, "-", "assumption (design-hour practice)"),
            ("BPR alpha/beta", "0.15 / 4.0", "-", "BPR (1964) standard"),
            ("MC_MAX_MIN", cp.MC_MAX_MIN, "min", "assumption: motorcycle short-trip mode"),
            ("PCU car/mc/bus/truck", "1.0/0.33/2.5/2.0", "-", "standard practice"),
        ]
        for m, asc in (('bus', cp.ASC_PAX), ('rail', cp.ASC_PAX), ('air', cp.ASC_PAX)):
            rows.append(("ASC_pax_" + m, round(asc[m], 1), "eq.min", "fitted to NAM 2565 shares"))
        rows.append(("ASC_frg_rail", round(cp.ASC_FRG['rail'], 1), "eq.min", "fitted to freight tonnage shares 2565"))
        rows.append(("ASC_frg_water", round(cp.ASC_FRG['water'], 1), "eq.min", "fitted"))
        for r in rows: w.writerow(r)
    log("T4 done")

    # ---------- final layer + T5 + GEH points ----------
    fin = V(M + r"\4_trip_assignment\assigned_final_dist.gpkg", "assigned_final_dist", "ปริมาณจราจร (PCU/วัน)")
    vols = [(f['vol_pcu'], f['voc'], f.geometry().length()) for f in fin.getFeatures()]
    va = np.array([v[0] for v in vols]); vc = np.array([v[1] for v in vols]); ln = np.array([v[2] for v in vols])
    with open(RT + r"\T5_assignment_stats.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["metric", "value"])
        w.writerow(["links_with_flow", len(va)])
        w.writerow(["daily_VKT_PCU_km", round(float((va*ln/1000).sum()))])
        w.writerow(["max_daily_PCU", round(float(va.max()))])
        w.writerow(["median_daily_PCU", round(float(np.median(va)))])
        w.writerow(["links_voc_over_0.8_peak", int((vc > 0.8).sum())])
        w.writerow(["links_voc_over_1.0_peak", int((vc > 1.0).sum())])
    log("T5 done")

    # GEH point layer จาก scatter_final
    from qgis.core import QgsGeometry, QgsPointXY, QgsField, QgsVectorFileWriter, QgsCoordinateTransformContext
    from qgis.PyQt.QtCore import QVariant
    aadt = V(M + r"\5_calibration\aadt_points.gpkg", "aadt_points", "AADT")
    # map (route,km) -> scatter row
    sc = {}
    for r in csv.DictReader(open(M + r"\5_calibration\scatter_final.csv", encoding="utf-8")):
        sc[(r['route'], round(float(r['km']), 3))] = r
    gl = QgsVectorLayer("Point?crs=EPSG:32647", "geh_points", "memory"); gp = gl.dataProvider()
    gp.addAttributes([QgsField('geh', QVariant.Double), QgsField('obs', QVariant.Double),
                      QgsField('model', QVariant.Double)]); gl.updateFields()
    k_t = None
    mt = []; ot = []
    for r in sc.values():
        mt.append(float(r['model_total_pcu'])); ot.append(float(r['obs_pax_pcu'])+float(r['obs_frg_pcu']))
    mt = np.array(mt); ot = np.array(ot)
    k_t = float((mt*ot).sum()/max((mt*mt).sum(), 1e-9))
    for f in aadt.getFeatures():
        key = (f['route'], round(f['km'], 3))
        r = sc.get(key)
        if not r: continue
        m = float(r['model_total_pcu'])*k_t; o = float(r['obs_pax_pcu'])+float(r['obs_frg_pcu'])
        ft = QgsFeature(gl.fields()); ft.setGeometry(f.geometry())
        ft.setAttributes([round(geh(m, o), 2), round(o), round(m)]); gp.addFeature(ft)
    out_geh = M + r"\5_calibration\geh_points_final.gpkg"
    if os.path.exists(out_geh): os.remove(out_geh)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "geh_points"
    QgsVectorFileWriter.writeAsVectorFormatV3(gl, out_geh, QgsCoordinateTransformContext(), o)
    gehl = V(out_geh, "geh_points", "GEH รายสถานี")
    log("GEH points: %d" % gl.featureCount())

    # ---------- styling ----------
    prov = V(B + r"\data\zones_taz\taz_provinces.gpkg", "taz_provinces", "ขอบเขตจังหวัด")
    prov.renderer().setSymbol(QgsFillSymbol.createSimple(
        {'color': '#fcfcfc', 'outline_color': '#9e9e9e', 'outline_width': '0.25'}))
    dtaz.renderer().setSymbol(QgsFillSymbol.createSimple(
        {'color': '0,0,0,0', 'outline_color': '#cccccc', 'outline_width': '0.08'}))
    ext = prov.extent(); ext.scale(1.04)

    def grad_line(l, fld, c0, c1, widths, method='quantile'):
        r = QgsGraduatedSymbolRenderer(fld)
        r.setSourceSymbol(QgsLineSymbol.createSimple({'color': '#888', 'width': '0.2'}))
        r.setClassificationMethod(QgsClassificationQuantile() if method == 'quantile' else QgsClassificationJenks())
        r.updateClasses(l, len(widths))
        r.updateColorRamp(QgsGradientColorRamp(QColor(c0), QColor(c1)))
        for i, rng in enumerate(r.ranges()):
            s = rng.symbol().clone(); s.setWidth(widths[min(i, len(widths)-1)])
            r.updateRangeSymbol(i, s)
        l.setRenderer(r)

    # F1 พื้นที่ศึกษา
    make_layout(proj, "รูปที่ 1 พื้นที่ศึกษาและระบบโซน (928 อำเภอ / 77 จังหวัด)",
                [dtaz, prov], ext, RF + r"\F1_study_area.png", legend_layers=[prov, dtaz])

    # F2 โครงข่าย multimodal
    road = V(B + r"\data\network\network_clean.gpkg", "network_clean", "ถนนสายหลัก")
    road.renderer().setSymbol(QgsLineSymbol.createSimple({'color': '#c9c9c9', 'width': '0.12'}))
    railn = V(B + r"\data\network\rail_clean.gpkg", "rail_clean", "ทางรถไฟ")
    railn.renderer().setSymbol(QgsLineSymbol.createSimple({'color': '#c62828', 'width': '0.4'}))
    airl = V(B + r"\data\multimodal\air_links.gpkg", "air_links", "เส้นทางบิน")
    airl.renderer().setSymbol(QgsLineSymbol.createSimple({'color': '#1565c0', 'width': '0.25'}))
    seal = V(B + r"\data\multimodal\water_freight_links.gpkg", "water_freight_links", "เดินเรือชายฝั่ง")
    seal.renderer().setSymbol(QgsLineSymbol.createSimple({'color': '#00838f', 'width': '0.5'}))
    make_layout(proj, "รูปที่ 2 โครงข่ายคมนาคมหลายรูปแบบ",
                [airl, seal, railn, road, prov], ext, RF + r"\F2_multimodal_network.png",
                legend_layers=[road, railn, airl, seal])

    # F3 trip generation (P_pax อำเภอ, scale calibrated)
    tg = V(B + r"\data\zones_taz\district_taz.gpkg", "district_taz", "การเกิดการเดินทาง (เที่ยว/วัน)")
    pdis = {int(r['district_id']): float(r['P_pax'])*s_pax
            for r in csv.DictReader(open(M + r"\1_trip_generation\district_tripgen.csv", encoding="utf-8"))}
    # ใส่ค่าเข้า memory copy เพื่อ render
    from qgis.core import QgsVectorLayer as _VL
    mem = _VL("Polygon?crs=EPSG:32647", "tripgen", "memory"); mp_ = mem.dataProvider()
    mp_.addAttributes([QgsField('P', QVariant.Double)]); mem.updateFields()
    fs = []
    for f in tg.getFeatures():
        ft = QgsFeature(mem.fields()); ft.setGeometry(f.geometry())
        ft.setAttributes([pdis.get(f['district_id'], 0)]); fs.append(ft)
    mp_.addFeatures(fs); proj.addMapLayer(mem, False)
    mem.setName("การเกิดการเดินทางผู้โดยสาร (เที่ยว/วัน)")
    r = QgsGraduatedSymbolRenderer('P')
    r.setSourceSymbol(QgsFillSymbol.createSimple({'color': '#ccc', 'outline_color': '#ffffff', 'outline_width': '0.06'}))
    r.setClassificationMethod(QgsClassificationQuantile()); r.updateClasses(mem, 6)
    r.updateColorRamp(QgsGradientColorRamp(QColor('#fff3e0'), QColor('#bf360c')))
    mem.setRenderer(r)
    make_layout(proj, "รูปที่ 3 การเกิดการเดินทางผู้โดยสารรายอำเภอ",
                [mem, prov], ext, RF + r"\F3_trip_generation.png", legend_layers=[mem])

    # F4 ปริมาณจราจรสุดท้าย
    grad_line(fin, 'vol_pcu', '#ffd54f', '#b71c1c', [0.12, 0.3, 0.6, 1.0, 1.6, 2.6])
    make_layout(proj, "รูปที่ 4 ปริมาณจราจรบนโครงข่าย (PCU/วัน) — แบบจำลองปรับเทียบแล้ว",
                [fin, prov], ext, RF + r"\F4_assigned_volume.png", legend_layers=[fin])

    # F5 components คน/สินค้า
    fp = V(M + r"\4_trip_assignment\flowf_d2d_pax.gpkg", "flowf_d2d_pax", "ผู้โดยสาร (PCU/วัน)")
    ff = V(M + r"\4_trip_assignment\flowf_d2d_frg.gpkg", "flowf_d2d_frg", "สินค้า (PCU/วัน)")
    grad_line(fp, 'vol_pcu', '#ffe0b2', '#e65100', [0.1, 0.25, 0.5, 0.9, 1.4, 2.2])
    grad_line(ff, 'vol_pcu', '#c8e6c9', '#1b5e20', [0.1, 0.25, 0.5, 0.9, 1.4, 2.2])
    make_layout(proj, "รูปที่ 5 องค์ประกอบจราจร: ผู้โดยสาร (ส้ม) และสินค้า (เขียว)",
                [ff, fp, prov], ext, RF + r"\F5_flow_components.png", legend_layers=[fp, ff])

    # F6 GEH map
    from qgis.core import QgsRendererRange as RR
    def mk(c):
        return QgsMarkerSymbol.createSimple({'name': 'circle', 'color': c,
                                             'outline_color': 'white', 'outline_width': '0.15', 'size': '1.8'})
    rngs = [RR(0, 5, mk('#2e7d32'), 'GEH < 5'), RR(5, 10, mk('#f9a825'), '5–10'),
            RR(10, 1e9, mk('#c62828'), '> 10')]
    gehl.setRenderer(QgsGraduatedSymbolRenderer('geh', rngs))
    make_layout(proj, "รูปที่ 6 ผลการปรับเทียบรายสถานี (GEH, k-scaled)",
                [gehl, road, prov], ext, RF + r"\F6_geh_map.png", legend_layers=[gehl])

    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์

try: main()
except Exception: log("ERR", traceback.format_exc()); raise
