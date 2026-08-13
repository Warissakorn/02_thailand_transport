# -*- coding: utf-8 -*-
"""ประกอบ thailand_transport.qgz ให้ครบทุกเลเยอร์ จัดเป็นกลุ่ม (รันผ่าน qpy.bat, headless)
log -> output/_build.log
"""
import os, traceback
from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer,
    QgsCoordinateReferenceSystem, QgsGraduatedSymbolRenderer, QgsClassificationJenks,
    QgsGradientColorRamp, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer, QgsRendererCategory)
from qgis.PyQt.QtGui import QColor

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_build.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

try:
    app = QgsApplication([], False); app.initQgis()
    p = QgsProject.instance(); p.clear()
    p.setCrs(QgsCoordinateReferenceSystem('EPSG:32647'))
    root = p.layerTreeRoot()

    def add(group, rel, ln, title, vis=True):
        l = QgsVectorLayer(B + "\\" + rel + "|layername=" + ln, title, "ogr")
        if not l.isValid(): log("INVALID", title); return None
        p.addMapLayer(l, False); node = group.addLayer(l); node.setItemVisibilityChecked(vis)
        return l
    def line(l, c, w): l.renderer().setSymbol(QgsLineSymbol.createSimple({'color': c, 'width': w}))
    def mark(l, c, s, ow='0.3'): l.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':'circle','color':c,'outline_color':'white','outline_width':ow,'size':s}))
    def fillout(l, c, w): l.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'0,0,0,0','outline_color':c,'outline_width':w}))
    def grad(l, fld, c0, c1):
        r = QgsGraduatedSymbolRenderer(fld)
        r.setSourceSymbol(QgsFillSymbol.createSimple({'color':'#ccc','outline_color':'#fff','outline_width':'0.15'}))
        r.setClassificationMethod(QgsClassificationJenks()); r.updateClasses(l, 5)
        r.updateColorRamp(QgsGradientColorRamp(QColor(c0), QColor(c1))); l.setRenderer(r)
    def grad_line(l, fld, c0, c1, widths):
        from qgis.core import QgsClassificationQuantile
        r = QgsGraduatedSymbolRenderer(fld)
        r.setSourceSymbol(QgsLineSymbol.createSimple({'color':'#888','width':'0.2'}))
        r.setClassificationMethod(QgsClassificationQuantile()); r.updateClasses(l, len(widths))
        r.updateColorRamp(QgsGradientColorRamp(QColor(c0), QColor(c1)))
        for i, rng in enumerate(r.ranges()):
            s = rng.symbol().clone(); s.setWidth(widths[min(i, len(widths)-1)]); r.updateRangeSymbol(i, s)
        l.setRenderer(r)

    # === groups: บนสุด=ผลลัพธ์/เส้น flow, ล่างสุด=ฐาน polygon (draw order ถูกต้อง) ===
    g_res  = root.addGroup("★ ผลลัพธ์หลัก (จราจรถนนรวม + AADT)")
    g_fcd  = root.addGroup("Flow components — final calibrated (คน/สินค้า)")
    g_fcp  = root.addGroup("Flow components — จังหวัด (คน/สินค้า)")
    g_sq   = root.addGroup("Sequence paths (เส้นทางต่อเนื่อง)")
    g_dm   = root.addGroup("Desire รายโหมด (อากาศ/น้ำ/ราง)")
    g_term = root.addGroup("Terminal (สถานี/สนามบิน/ท่าเรือ)")
    g_net  = root.addGroup("โครงข่าย multimodal")
    g_tg   = root.addGroup("Trip Generation (P/A)")
    g_zone = root.addGroup("โซน TAZ / ฐาน")
    g_acc  = root.addGroup("Access connectors")

    # Results — canonical: final assignment (calibrated, directed, congestion-aware)
    fin = add(g_res, r"model\4_trip_assignment\assigned_final_dist.gpkg", "assigned_final_dist", "★ ปริมาณจราจรสุดท้าย calibrated (PCU/วัน)", True)
    if fin: grad_line(fin, 'vol_pcu', '#ffd54f', '#b71c1c', [0.1, 0.3, 0.6, 1.0, 1.6, 2.6])
    gehp = add(g_res, r"model\5_calibration\geh_points_final.gpkg", "geh_points", "GEH รายสถานี (final)", False)
    if gehp: mark(gehp, '#6d4c41', '1.6', '0.2')
    rd = add(g_res, r"model\4_trip_assignment\assigned_road_total_dist.gpkg", "assigned_road_total_dist", "จราจรถนนรวม v1 อำเภอ (อ้างอิง)", False)
    if rd: grad_line(rd, 'vol_pcu', '#ffd54f', '#b71c1c', [0.1, 0.3, 0.6, 1.0, 1.6, 2.6])
    rp = add(g_res, r"model\4_trip_assignment\assigned_road_total_prov.gpkg", "assigned_road_total_prov", "จราจรถนนรวม v1 จังหวัด (อ้างอิง)", False)
    if rp: grad_line(rp, 'vol_pcu', '#ffd54f', '#b71c1c', [0.1, 0.3, 0.6, 1.0, 1.6, 2.6])
    cmp = add(g_res, r"model\5_calibration\aadt_compare_dist_total.gpkg", "aadt_compare", "AADT เทียบโมเดล (GEH, อำเภอ)", False)
    if cmp: mark(cmp, '#6d4c41', '1.6', '0.2')

    # === Desire by mode (แยกโหมด/สาย) ===
    dmode = [("desire_pax_rail", "Desire ผู้โดยสาร-ราง", '#6a1b9a'),
             ("desire_pax_air",  "Desire ผู้โดยสาร-อากาศ", '#1565c0'),
             ("desire_pax_water","Desire ผู้โดยสาร-น้ำ", '#00838f'),
             ("desire_frg_rail", "Desire สินค้า-ราง", '#ad1457'),
             ("desire_frg_water","Desire สินค้า-น้ำ", '#00695c')]
    for fn, title, col in dmode:
        l = add(g_dm, r"model\3_mode_choice\\" + fn + ".gpkg", fn, title, False)
        if l: grad_line(l, 'trips', col, col, [0.2, 0.5, 0.9, 1.4, 2.2])

    # (กลุ่ม "Assignment รายโหมด" เดิมถูกลบออก — ใช้ sequence paths + จราจรถนนรวมแทน)

    # === Flow components — จังหวัด (แตกจราจรถนนรวม แยกโหมด×สาย; รวม = ตัวรวม) ===
    fcomp = [("flow_d2d_pax",      "ถนน d2d-ผู้โดยสาร", '#ffa726'),
             ("flow_d2d_frg",      "ถนน d2d-สินค้า", '#bf360c'),
             ("flow_ae_rail_pax",  "ราง a/e-ผู้โดยสาร", '#ba68c8'),
             ("flow_ae_rail_frg",  "ราง a/e-สินค้า", '#6a1b9a'),
             ("flow_ae_air_pax",   "อากาศ a/e-ผู้โดยสาร", '#1565c0'),
             ("flow_ae_water_pax", "น้ำ a/e-ผู้โดยสาร", '#4db6ac'),
             ("flow_ae_water_frg", "น้ำ a/e-สินค้า", '#00695c')]
    for fn, title, col in fcomp:
        l = add(g_fcp, r"model\4_trip_assignment\\" + fn + ".gpkg", fn, title, False)
        if l: grad_line(l, 'vol_pcu', col, col, [0.15, 0.4, 0.7, 1.1, 1.7, 2.6])

    # === Flow components — final (calibrated อำเภอ) ===
    fcompd = [("flowf_d2d_pax",      "ถนน d2d-ผู้โดยสาร", '#ffa726'),
              ("flowf_d2d_frg",      "ถนน d2d-สินค้า", '#bf360c'),
              ("flowf_ae_rail_pax",  "ราง a/e-ผู้โดยสาร", '#ba68c8'),
              ("flowf_ae_rail_frg",  "ราง a/e-สินค้า", '#6a1b9a'),
              ("flowf_ae_air_pax",   "อากาศ a/e-ผู้โดยสาร", '#1565c0'),
              ("flowf_ae_water_pax", "น้ำ a/e-ผู้โดยสาร", '#4db6ac'),
              ("flowf_ae_water_frg", "น้ำ a/e-สินค้า", '#00695c')]
    for fn, title, col in fcompd:
        l = add(g_fcd, r"model\4_trip_assignment\\" + fn + ".gpkg", fn, title, fn == "flowf_d2d_pax")
        if l: grad_line(l, 'vol_pcu', col, col, [0.15, 0.4, 0.7, 1.1, 1.7, 2.6])

    # === Sequence paths (เส้นทางต่อเนื่อง access->linehaul->egress) ===
    def seq_style(l, lh_col):
        sr = QgsLineSymbol.createSimple({'color': '#9e9e9e', 'width': '0.3'})
        sl = QgsLineSymbol.createSimple({'color': lh_col, 'width': '0.9'})
        l.setRenderer(QgsCategorizedSymbolRenderer('leg', [
            QgsRendererCategory('road', sr, 'access/egress (ถนน)'),
            QgsRendererCategory('linehaul', sl, 'line-haul')]))
    seqs = [("seq_rail_pax", "Seq ผู้โดยสาร-ราง", '#6a1b9a'),
            ("seq_rail_frg", "Seq สินค้า-ราง", '#ad1457'),
            ("seq_air_pax",  "Seq ผู้โดยสาร-อากาศ", '#1565c0'),
            ("seq_water_pax","Seq ผู้โดยสาร-น้ำ", '#00838f'),
            ("seq_sea_frg",  "Seq สินค้า-เรือ", '#00695c')]
    for fn, title, col in seqs:
        l = add(g_sq, r"model\4_trip_assignment\\" + fn + ".gpkg", fn, title, False)
        if l: seq_style(l, col)

    # Trip generation
    pax = add(g_tg, r"model\1_trip_generation\trip_gen_passenger.gpkg", "trip_gen_passenger", "Trip Gen ผู้โดยสาร (P_pax)", True)
    frg = add(g_tg, r"model\1_trip_generation\trip_gen_freight.gpkg", "trip_gen_freight", "Trip Gen สินค้า (P_frg)", False)
    grad(pax, 'P_pax', '#fff3e0', '#bf360c'); grad(frg, 'P_frg', '#e8f5e9', '#1b5e20')

    # zones
    cen = add(g_zone, r"data\zones_taz\taz_centroids_pw.gpkg", "taz_centroids_pw", "centroid (ถ่วงประชากร)", True)
    dcen = add(g_zone, r"data\zones_taz\district_centroids.gpkg", "district_centroids", "centroid อำเภอ (928)", False)
    if dcen: mark(dcen, '#ef6c00', '1.0', '0.1')
    taz = add(g_zone, r"data\zones_taz\taz_provinces.gpkg", "taz_provinces", "TAZ จังหวัด (77)", True)
    dtaz = add(g_zone, r"data\zones_taz\district_taz.gpkg", "district_taz", "โซนอำเภอ (928)", False)
    if dtaz: fillout(dtaz, '#b0bec5', '0.1')
    mark(cen, '#e53935', '2.4'); fillout(taz, '#5d4037', '0.26')

    # terminals
    anode = add(g_term, r"data\multimodal\air_nodes.gpkg", "air_nodes", "สนามบิน (41)", True)
    sea   = add(g_term, r"data\multimodal\seaport_nodes.gpkg", "seaport_nodes", "ท่าเรือใหญ่ (10)", True)
    rsta  = add(g_term, r"data\multimodal\rail_stations.gpkg", "rail_stations", "สถานีรถไฟ (855)", False)
    ports = add(g_term, r"data\multimodal\ports.gpkg", "ports", "ท่าเรือ/ท่าเทียบ (529)", False)
    mark(anode, '#1565c0', '3.0', '0.4'); mark(sea, '#00838f', '3.2', '0.4')
    mark(rsta, '#6a1b9a', '1.4', '0.2'); mark(ports, '#0097a7', '1.0', '0.1')

    # access connectors (hidden group)
    ar = add(g_acc, r"data\zones_taz\access_rail.gpkg", "access_rail", "access ราง", True)
    aa = add(g_acc, r"data\zones_taz\access_air.gpkg", "access_air", "access อากาศ", True)
    aw = add(g_acc, r"data\zones_taz\access_water.gpkg", "access_water", "access น้ำ", True)
    af = add(g_acc, r"data\zones_taz\access_seafreight.gpkg", "access_seafreight", "access ท่าเรือสินค้า", True)
    line(ar, '#9e9e9e', '0.25'); line(aa, '#9e9e9e', '0.25'); line(aw, '#9e9e9e', '0.25'); line(af, '#9e9e9e', '0.25')
    root.findGroup("Access connectors").setItemVisibilityChecked(False)

    # networks
    alink = add(g_net, r"data\multimodal\air_links.gpkg", "air_links", "เส้นทางบิน", True)
    wflink= add(g_net, r"data\multimodal\water_freight_links.gpkg", "water_freight_links", "เดินเรือชายฝั่ง (สินค้า)", True)
    railc = add(g_net, r"data\network\rail_clean.gpkg", "rail_clean", "ราง", True)
    waterc= add(g_net, r"data\network\water_clean.gpkg", "water_clean", "เรือ/ferry", True)
    road  = add(g_net, r"data\network\network_clean.gpkg", "network_clean", "ถนนสายหลัก (141k)", True)
    line(alink, '#1565c0', '0.3'); line(wflink, '#00838f', '0.6'); line(railc, '#c62828', '0.4')
    line(waterc, '#26a69a', '0.3'); line(road, '#cfd8dc', '0.1')

    out = B + r"\thailand_transport.qgz"
    p.write(out); log("SAVED ->", out)
    log("groups:", [g.name() for g in root.findGroups()])
    log("layers:", len(p.mapLayers()))
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
