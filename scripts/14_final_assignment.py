# -*- coding: utf-8 -*-
"""ขั้น 14: Final assignment (อำเภอ 928, directed, congestion-aware, multi-path)
วิธี: 1) trip gen อำเภอ scale ด้วยพารามิเตอร์ calibrated  2) gravity ด้วย beta calibrated
3) demand ถนนรวม = d2d (FAC_*_ROAD) + access/egress ราง/น้ำ/อากาศ (SHARE_*)
4) peak-hour = K x รายวัน -> **multi-path MSA ต่อ component** (BPR): แต่ละรอบ assign 7
   component ที่เวลาแออัดปัจจุบัน (sweep เดียว) แล้ว MSA-average -> flow กระจายหลายเส้น
   ตามสมดุล (มอเตอร์เวย์/ทางเลี่ยงได้ flow จริง แทน AON snapshot เดิมที่ให้สายขนาน=0)
5) sum(component)=total เป๊ะ (linear ทุกรอบ -> additivity แน่นอน) -> /K กลับรายวัน
6) เทียบ AADT (pax/frg/total) + เขียน scatter CSV
out: model/4_trip_assignment/assigned_final_dist.gpkg, flowf_*.gpkg (7 components),
     model/5_calibration/{calibration_report_final.txt, scatter_final.csv}
log -> output/_14.log ; รันผ่าน qpy.bat (background)
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
M = B + r"\model"
LOG = None   # เปิดใน guard __main__ เท่านั้น (กัน worker process spawn มา truncate log)
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

from lib import scenario as sc
K_FACTOR = sc.get("k_factor", 0.09)   # สัดส่วนชั่วโมงเร่งด่วนของปริมาณรายวัน (สมมติฐานตามแนวปฏิบัติ; ดู METHODOLOGY)
EQ_ITER = int(sc.get("eq_iter", 8))  # multi-path MSA ต่อ component (แต่ละรอบ assign 7 สาย -> หนักกว่ารอบละ ~4x)
ALPHA, BETA_BPR = 0.15, 4.0
SNAP_TOL = 1500.0
# ค่าที่ใช้ตอนสร้าง district_tripgen.csv (ขั้น 08a อ่านจาก model_params/scenario หมวด model)
_m = sc.section("model")
BASE_RATE, BASE_FF = _m.get("trip_rate_pax", 2.0), _m.get("freight_factor", 0.10)

def workers():
    """จำนวน process ขนาน: scenario run.workers > จำนวนคอร์ (จำกัดไว้ที่ 4)

    worker แต่ละตัวได้สำเนากราฟผ่าน pickle เต็ม ๆ ตั้งค่าสูงเกินจำนวน RAM
    ของเครื่อง (เช่น runner ฟรีของ GitHub) จะโดน OOM kill เงียบ ๆ ระหว่างสร้าง pool
    """
    n = int(sc.get("workers", 0) or 0)
    if n <= 0:
        n = min(os.cpu_count() or 2, 4)
    return max(n, 1)


def main():
    from qgis.core import (QgsApplication, QgsVectorLayer, QgsSpatialIndex, QgsFeature,
                           QgsCoordinateReferenceSystem)
    import processing
    from processing.core.Processing import Processing
    from lib.transport_graph import (build_road_graph, od_cost_matrix, gravity_furness,
        assign_multi, robust_tie, fit_stats, write_flow_gpkg)
    import calibrated_params as cp
    sc.apply(cp)      # ทับด้วย inputs/scenarios/<TT_SCENARIO>.yaml
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()

    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    G = build_road_graph(net, directed=True)
    log("graph: nodes=%d edges=%d" % (G.nN, G.nE))
    t0 = G.Ec.copy(); cap_hr = G.Ecap_hr.copy()

    # ---- pool ขนาน: แบ่ง origins ไปหลาย process (flow บวกกันได้ -> ผลเท่า serial) ----
    import multiprocessing as _mp
    import lib.passign as passign
    NW = workers()
    os.environ["TT_DIJKSTRA_BATCH"] = str(sc.get("dijkstra_batch", 32))
    pool = _mp.Pool(NW, initializer=passign.init,
                    initargs=(G.Eu, G.Ev, G.Eoneway, G.edge_of, G.nN, G.nE, G.directed))
    log("parallel pool: %d workers" % NW)

    cen = QgsVectorLayer(B + r"\data\zones_taz\district_centroids.gpkg|layername=district_centroids", "c", "ogr")
    dc = sorted([(f['district_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    dids = [d[0] for d in dc]; Z = len(dids); didx = {d: i for i, d in enumerate(dids)}
    cnode, reach = robust_tie(G, [p for _, p in dc])
    log("ties done (repaired=%d)" % int((np.asarray(reach) < 0.9).sum()))

    # terminal road-nodes ต่ออำเภอ
    def term_nodes(gpkg, ln):
        t = processing.run("native:reprojectlayer", {'INPUT': QgsVectorLayer(B + "\\" + gpkg + "|layername=" + ln, "t", "ogr"),
            'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']
        tp = np.array([[f.geometry().asPoint().x(), f.geometry().asPoint().y()] for f in t.getFeatures()])
        out = []
        for did, p in dc:
            d = (tp[:, 0]-p.x())**2 + (tp[:, 1]-p.y())**2
            k = int(np.argmin(d)); out.append(G.nearest(tp[k][0], tp[k][1]))
        return out
    rail_n = term_nodes(r"inputs\multimodal\rail_stations.gpkg", "rail_stations")
    air_n = term_nodes(r"inputs\multimodal\airports_pts.gpkg", "airports_pts")
    port_n = term_nodes(r"inputs\multimodal\ports.gpkg", "ports")
    sea_n = term_nodes(r"data\multimodal\seaport_nodes.gpkg", "seaport_nodes")
    log("terminal nodes tied")

    # trip gen (scale calibrated) + gravity
    P = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}; A = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}
    for r in csv.DictReader(open(M + r"\1_trip_generation\district_tripgen.csv", encoding="utf-8")):
        i = didx[int(r['district_id'])]
        P['pax'][i] = float(r['P_pax']); A['pax'][i] = float(r['A_pax'])
        P['frg'][i] = float(r['P_frg']); A['frg'][i] = float(r['A_frg'])
    s_pax = cp.TRIP_RATE_PAX/BASE_RATE
    s_frg = s_pax * (cp.FREIGHT_FACTOR/BASE_FF)
    for k in ('pax',): P[k] *= s_pax; A[k] *= s_pax
    for k in ('frg',): P[k] *= s_frg; A[k] *= s_frg
    log("scaled tripgen: total pax=%.0f frg=%.0f" % (P['pax'].sum(), P['frg'].sum()))

    cost = od_cost_matrix(G, cnode)
    T_pax = gravity_furness(P['pax'], A['pax'], cost, cp.BETA_PAX)
    T_frg = gravity_furness(P['frg'], A['frg'], cost, cp.BETA_FRG)
    log("gravity done: pax=%.0f (intra %.1f%%) frg=%.0f (intra %.1f%%)" % (
        T_pax.sum(), 100*np.trace(T_pax)/T_pax.sum(), T_frg.sum(), 100*np.trace(T_frg)/T_frg.sum()))

    # ---- 7 component demands (รายวัน) ----
    shp, shf = cp.SHARE_PAX, cp.SHARE_FRG
    def d2d(T, fac):
        dem = {}
        for i in range(Z):
            row = T[i]*fac; d = dem.setdefault(cnode[i], {})
            for j in range(Z):
                if row[j] > 0 and i != j: d[cnode[j]] = d.get(cnode[j], 0.0) + row[j]
        return dem
    def ae(T, tnodes, share, pcu):
        dem = {}; oi = T.sum(1)*share*pcu; ii = T.sum(0)*share*pcu
        for i in range(Z):
            if oi[i] > 0: dem.setdefault(cnode[i], {}).setdefault(tnodes[i], 0.0)
            if oi[i] > 0: dem[cnode[i]][tnodes[i]] += oi[i]
            if ii[i] > 0: dem.setdefault(tnodes[i], {}).setdefault(cnode[i], 0.0)
            if ii[i] > 0: dem[tnodes[i]][cnode[i]] += ii[i]
        return dem
    comp = [
        ("flowf_d2d_pax",      d2d(T_pax, cp.FAC_PAX_ROAD)),
        ("flowf_d2d_frg",      d2d(T_frg, cp.FAC_FRG_ROAD)),
        ("flowf_ae_rail_pax",  ae(T_pax, rail_n, shp.get('rail', 0), 1.0)),
        ("flowf_ae_rail_frg",  ae(T_frg, rail_n, shf.get('rail', 0), 2.0)),
        ("flowf_ae_air_pax",   ae(T_pax, air_n, shp.get('air', 0), 1.0)),
        ("flowf_ae_water_pax", ae(T_pax, port_n, shp.get('water', 0), 1.0)),
        ("flowf_ae_water_frg", ae(T_frg, sea_n, shf.get('water', 0), 2.0)),
    ]
    # ---- component demands (peak = รายวัน x K) สำหรับ multi-path MSA ----
    def scale_dem(dem, k):
        return {o: {d: v*k for d, v in dd.items()} for o, dd in dem.items()}
    peak_dems = [scale_dem(dem, K_FACTOR) for _, dem in comp]   # 7 demand (peak)
    def total_of(xs):
        s = np.zeros(G.nE)
        for a in xs: s += a
        return s
    log("demand built: components=%d (multi-path per-component MSA)" % len(comp))

    # ---- Multi-path MSA ต่อ component (ขนาน) ----
    # แต่ละรอบ: assign 7 component ที่เวลาแออัดปัจจุบัน (routing sweep เดียว) -> MSA-average
    # flow กระจายหลายเส้นตามสมดุล (มอเตอร์เวย์/เลี่ยงเมืองได้ flow) และ sum(component)=total เป๊ะ
    # (แทน final AON snapshot เดิมที่โยนทุก OD ลงเส้นเดียว -> สายขนานเป็น 0)
    xk = passign.run_assign(pool, NW, t0, peak_dems)   # 7 peak-flow arrays (free-flow)
    tot = total_of(xk)
    log("mp iter 1 maxpeak=%.0f" % tot.max())
    for n in range(2, EQ_ITER+1):
        t = t0*(1.0 + ALPHA*np.power(np.maximum(tot, 0)/np.maximum(cap_hr, 1), BETA_BPR))
        yk = passign.run_assign(pool, NW, t, peak_dems)
        xk = [xk[i] + (1.0/n)*(yk[i]-xk[i]) for i in range(len(xk))]
        tot = total_of(xk)
        gap = np.abs(total_of(yk)-tot).sum()/max(tot.sum(), 1)
        log("mp iter %d gap=%.4f maxpeak=%.0f" % (n, gap, tot.max()))

    # ---- แปลง peak -> รายวัน (flow กระจายหลายเส้นแล้ว) แยก component (additive เป๊ะ) ----
    flows = [xi/K_FACTOR for xi in xk]        # daily component flows
    total = total_of(flows)
    for (name, _), fl in zip(comp, flows):
        nlk = write_flow_gpkg(G, {'vol_pcu': fl}, M + r"\4_trip_assignment\\" + name + ".gpkg", name)
        log("%s: links=%d total=%.0f" % (name, nlk, fl.sum()))
    vol_peak = tot                            # peak converged (= total*K)
    voc = vol_peak/np.maximum(cap_hr, 1)
    write_flow_gpkg(G, {'vol_pcu': total, 'vol_peak': vol_peak, 'voc': voc},
                    M + r"\4_trip_assignment\assigned_final_dist.gpkg", "assigned_final_dist")
    log("assigned_final_dist written | additivity diff = %.6f%%" % (
        100*abs(sum(f.sum() for f in flows)-total.sum())/max(total.sum(), 1)))

    # ---- เทียบ AADT ----
    aadt = QgsVectorLayer(M + r"\5_calibration\aadt_points.gpkg|layername=aadt_points", "a", "ogr")
    eidx = QgsSpatialIndex()
    for e in range(G.nE):
        f = QgsFeature(e+1); f.setGeometry(G.Eg[e]); eidx.addFeature(f)
    F_pax = flows[0] + flows[2] + flows[4] + flows[5]   # pax components
    F_frg = flows[1] + flows[3] + flows[6]
    rows_out = []; mt = []; ot = []; mp_ = []; op_ = []; mf = []; of_ = []
    for f in aadt.getFeatures():
        p = f.geometry(); best = None; bd = 1e18
        for fid in eidx.nearestNeighbor(p.asPoint(), 8):
            d = G.Eg[fid-1].distance(p)
            if d < bd: bd = d; best = fid-1
        if best is None or bd > SNAP_TOL: continue
        if total[best] <= 0: continue
        rows_out.append([f['route'], f['prov'], f['km'], f['method'],
                         round(f['aadt']), round(f['pax_pcu']), round(f['frg_pcu']),
                         round(total[best], 1), round(F_pax[best], 1), round(F_frg[best], 1)])
        mt.append(total[best]); ot.append(f['pax_pcu']+f['frg_pcu'])
        mp_.append(F_pax[best]); op_.append(f['pax_pcu'])
        mf.append(F_frg[best]); of_.append(f['frg_pcu'])
    with open(M + r"\5_calibration\scatter_final.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["route", "prov", "km", "geoloc_method", "obs_aadt_veh", "obs_pax_pcu", "obs_frg_pcu",
                    "model_total_pcu", "model_pax_pcu", "model_frg_pcu"])
        w.writerows(rows_out)
    st_t = fit_stats(mt, ot); st_p = fit_stats(mp_, op_); st_f = fit_stats(mf, of_)
    rep = ("=== Final calibration (district, directed, multi-path) vs AADT project 2569 ===\n"
           "stations: %d\n"
           "TOTAL : k=%.4g GEH<5=%.1f%% GEH<10=%.1f%% medGEH=%.1f R2=%.3f RMSE=%.0f\n"
           "PAX   : k=%.4g GEH<5=%.1f%% GEH<10=%.1f%% medGEH=%.1f R2=%.3f RMSE=%.0f\n"
           "FRG   : k=%.4g GEH<5=%.1f%% GEH<10=%.1f%% medGEH=%.1f R2=%.3f RMSE=%.0f\n" % (
        len(rows_out),
        st_t['k'], st_t['geh5'], st_t['geh10'], st_t['median_geh'], st_t['r2'], st_t['rmse'],
        st_p['k'], st_p['geh5'], st_p['geh10'], st_p['median_geh'], st_p['r2'], st_p['rmse'],
        st_f['k'], st_f['geh5'], st_f['geh10'], st_f['median_geh'], st_f['r2'], st_f['rmse']))
    open(M + r"\5_calibration\calibration_report_final.txt", "w", encoding="utf-8").write(rep)
    log(rep)
    pool.close(); pool.join()
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์

if __name__ == '__main__':
    import multiprocessing as _mpmain
    _mpmain.freeze_support()   # จำเป็นบน Windows (spawn)
    LOG = open(B + r"\output\_14.log", "w", encoding="utf-8")
    try: main()
    except Exception: log("ERR", traceback.format_exc()); raise
