# -*- coding: utf-8 -*-
"""ขั้น 13: Calibrate พารามิเตอร์แบบจำลอง (ระดับอำเภอ = canonical)
A) β gravity: grid search แยก pax/frg — routing sweep เดียว (assign_multi)
   เทียบกับ AADT v2 (pax_pcu / frg_pcu แยกสาย) -> เลือก β ที่ R² สูงสุด + ได้ k แยกสาย
B) Mode choice: 2-segment VOT + ASC iterative fitting เข้าเป้าทางการปี 2565
   (ผู้โดยสารระหว่างเมือง สนข./NAM + สัดส่วนตันสินค้า สนข.)
out: config/calibrated_params.py, model/5_calibration/{calibration_search.csv,
     mode_share_calibrated.csv}, log -> output/_13.log
รันผ่าน qpy.bat (background)
"""
import os, sys, csv, math, heapq, traceback
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
LOG = None   # เปิดใน guard __main__ (กัน worker spawn มา truncate log)
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

BETA_PAX_GRID = [0.015, 0.025, 0.035, 0.045, 0.060, 0.080]
BETA_FRG_GRID = [0.008, 0.015, 0.025, 0.035, 0.050]
SNAP_TOL = 1500.0
# mode-choice segments
VOT_GEN, VOT_BIZ, BIZ_SHARE = 180.0/60.0, 600.0/60.0, 0.12
MC_MAX_MIN = 90.0     # จยย. ใช้ได้เฉพาะทริป <= 90 นาที (สมมติฐาน: โหมดระยะสั้น)
THETA = 0.020
ASC_FIT_ITER = 30

def read_targets():
    """เป้า 2565: pax interzonal shares (car,bus,rail,air) + freight (truck,rail,water)"""
    tp = {}
    rows = list(csv.DictReader(open(B + r"\inputs\calibration\targets\intercity_pt_share_otp6503.csv", encoding="utf-8-sig")))
    v = {'car': 0.0, 'bus': 0.0, 'rail': 0.0, 'air': 0.0}
    for r in rows:
        if r['ปี'] != '2565': continue
        m = r['รูปแบบการเดินทาง']; val = float(str(r['ปริมาณการเดินทาง']).replace(',', ''))
        if 'รถยนต์ส่วนบุคคล' in m: v['car'] += val
        elif 'รถโดยสารระหว่างเมือง' in m: v['bus'] += val
        elif m == 'รถไฟ': v['rail'] += val
        elif m == 'เครื่องบิน': v['air'] += val
    s = sum(v.values()); tp = {k: x/s for k, x in v.items()}
    tf = {}
    rows = list(csv.DictReader(open(B + r"\inputs\calibration\targets\freight_by_mode_2560_2565.csv", encoding="utf-8-sig")))
    w = {}
    for r in rows:
        if r['ปี'] != '2565': continue
        m = r['รูปแบบการขนส่ง']; val = float(str(r['สัดส่วนขนส่งในประเทศ']).replace(',', ''))
        if 'ถนน' in m: w['truck'] = val
        elif 'ราง' in m: w['rail'] = val
        elif 'น้ำ' in m: w['water'] = val
    s = sum(w.values()); tf = {k: x/s for k, x in w.items()}
    return tp, tf

# ---------------- PART A ----------------
def part_a():
    from qgis.core import QgsApplication, QgsVectorLayer, QgsSpatialIndex, QgsFeature, QgsGeometry, QgsPointXY
    from lib.transport_graph import build_road_graph, od_cost_matrix, gravity_furness, assign_multi, robust_tie, fit_stats
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    G = build_road_graph(net, directed=True)
    log("graph: nodes=%d edges=%d oneway=%.1f%% | %s" % (G.nN, G.nE, 100*G.Eoneway.mean(), _mem()))
    import lib.passign as passign
    from lib import scenario as _sc
    NW = _workers(_sc)
    os.environ["TT_DIJKSTRA_BATCH"] = str(_sc.get("dijkstra_batch", 32))

    cen = QgsVectorLayer(B + r"\data\zones_taz\district_centroids.gpkg|layername=district_centroids", "c", "ogr")
    dc = sorted([(f['district_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    dids = [d[0] for d in dc]; Z = len(dids); didx = {d: i for i, d in enumerate(dids)}
    log("centroids read: %d | %s" % (len(dc), _mem()))
    tn, reach = robust_tie(G, [p for _, p in dc], log=log)
    log("ties: %d districts | median first-tie reach=%.3f | repaired=%d | %s" % (
        Z, float(np.median(reach)), int((reach < 0.9).sum()), _mem()))

    log("start OD cost matrix | %s" % _mem())
    cost = od_cost_matrix(G, tn)
    log("OD cost: finite=%.3f | %s" % (np.isfinite(cost).mean(), _mem()))

    P = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}; A = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}
    for r in csv.DictReader(open(M + r"\1_trip_generation\district_tripgen.csv", encoding="utf-8")):
        i = didx[int(r['district_id'])]
        P['pax'][i] = float(r['P_pax']); A['pax'][i] = float(r['A_pax'])
        P['frg'][i] = float(r['P_frg']); A['frg'][i] = float(r['A_frg'])

    def to_demand(T):
        dem = {}
        for i in range(Z):
            row = T[i]; d = {}
            for j in range(Z):
                if row[j] > 0 and i != j: d[tn[j]] = d.get(tn[j], 0.0) + row[j]
            if d: dem.setdefault(tn[i], {}).update(
                {k: dem.get(tn[i], {}).get(k, 0.0) + v for k, v in d.items()})
        return dem

    demands = []; labels = []
    intra = {}
    for bp in BETA_PAX_GRID:
        T = gravity_furness(P['pax'], A['pax'], cost, bp)
        intra[('pax', bp)] = float(np.trace(T)/T.sum()*100)
        demands.append(to_demand(T)); labels.append(('pax', bp))
    for bf in BETA_FRG_GRID:
        T = gravity_furness(P['frg'], A['frg'], cost, bf)
        intra[('frg', bf)] = float(np.trace(T)/T.sum()*100)
        demands.append(to_demand(T)); labels.append(('frg', bf))
    log("gravity done for %d beta candidates | %s" % (len(labels), _mem()))

    # สร้าง pool ตรงนี้ (ไม่ใช่ตอนต้น) เพื่อไม่ให้ worker กินหน่วยความจำค้างไว้
    # ตลอดช่วง tie/od-cost/gravity ซึ่งเป็นช่วงที่ใช้ RAM สูงสุด
    pool, how = passign.make_pool(NW, G)
    log("parallel pool: %d workers (%s)" % (NW, how))
    flows = passign.run_assign(pool, NW, G.Ec, demands)   # ขนาน (free-flow beta search)
    pool.close(); pool.join()
    log("multi-assign sweep done (parallel)")

    # snap AADT v2 -> edge
    aadt = QgsVectorLayer(M + r"\5_calibration\aadt_points.gpkg|layername=aadt_points", "a", "ogr")
    eidx = QgsSpatialIndex()
    for e in range(G.nE):
        f = QgsFeature(e+1); f.setGeometry(G.Eg[e]); eidx.addFeature(f)
    st_edge = []; st_pax = []; st_frg = []; st_tot = []
    for f in aadt.getFeatures():
        p = f.geometry()
        best = None; bd = 1e18
        for fid in eidx.nearestNeighbor(p.asPoint(), 8):
            d = G.Eg[fid-1].distance(p)
            if d < bd: bd = d; best = fid-1
        if best is not None and bd <= SNAP_TOL:
            st_edge.append(best); st_pax.append(f['pax_pcu']); st_frg.append(f['frg_pcu']); st_tot.append(f['aadt'])
    st_edge = np.array(st_edge, dtype=np.int64); st_pax = np.array(st_pax, float); st_frg = np.array(st_frg, float)
    log("stations snapped to edges: %d" % len(st_edge))
    if st_edge.size == 0:
        raise SystemExit("ไม่มีสถานี AADT ติดโครงข่ายเลย — ตรวจ output/_geo.log (ขั้น 07a) ก่อนรัน 13")

    # score per beta (แยกสาย)
    curves = []
    best = {'pax': (None, None), 'frg': (None, None)}
    for (stream, b), fl in zip(labels, flows):
        m = fl[st_edge]
        obs = st_pax if stream == 'pax' else st_frg
        msk = m > 0
        stats = fit_stats(m[msk], obs[msk])
        stats.update({'stream': stream, 'beta': b, 'n_used': int(msk.sum()),
                      'intrazonal_pct': intra[(stream, b)]})
        curves.append(stats)
        log("  %s beta=%.3f -> R2=%.3f medGEH=%.1f k=%.4g intra=%.1f%%" % (
            stream, b, stats['r2'], stats['median_geh'], stats['k'], stats['intrazonal_pct']))
        cur = best[stream][1]
        if cur is None or stats['r2'] > cur['r2']:
            best[stream] = (b, stats)
    with open(M + r"\5_calibration\calibration_search.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(curves[0].keys())); w.writeheader()
        for c in curves: w.writerow(c)
    return best

# ---------------- PART B ----------------
def small_allpairs(edges):
    nodes = set()
    for a, b, c, dk in edges: nodes.add(a); nodes.add(b)
    adj = {n: [] for n in nodes}
    for a, b, c, dk in edges:
        adj[a].append((b, c, dk)); adj[b].append((a, c, dk))
    def dij(src, use):
        dist = {n: math.inf for n in nodes}; dist[src] = 0; pq = [(0.0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]: continue
            for v, c, dk in adj[u]:
                w = c if use == 0 else dk
                if d+w < dist[v]: dist[v] = d+w; heapq.heappush(pq, (d+w, v))
        return dist
    return {n: dij(n, 0) for n in nodes}, {n: dij(n, 1) for n in nodes}

def part_b(target_pax, target_frg):
    from qgis.core import QgsVectorLayer
    import model_params as mp
    from lib import scenario as sc
    sc.apply(mp)
    def read_matrix(path, vcol):
        d = {}
        for r in csv.DictReader(open(path, encoding="utf-8")):
            v = r[vcol]; d[(int(r['orig_zone']), int(r['dest_zone']))] = (float(v) if v != "" else None)
        return d
    def read_access(gpkg, ln, term=None):
        l = QgsVectorLayer(B + "\\" + gpkg + "|layername=" + ln, "a", "ogr")
        return {f['zone_id']: (f['access_min'], f[term] if term else None) for f in l.getFeatures()}
    road = read_matrix(M + r"\2_trip_distribution\od_cost_road.csv", "cost_min")
    rail = read_matrix(M + r"\3_mode_choice\linehaul_rail.csv", "min")
    water = read_matrix(M + r"\3_mode_choice\linehaul_water.csv", "min")
    acc_rail = read_access(r"data\zones_taz\access_rail.gpkg", "access_rail")
    acc_air = read_access(r"data\zones_taz\access_air.gpkg", "access_air", "terminal")
    acc_wat = read_access(r"data\zones_taz\access_water.gpkg", "access_water")
    acc_sea = read_access(r"data\zones_taz\access_seafreight.gpkg", "access_seafreight", "port")
    al = QgsVectorLayer(B + r"\data\multimodal\air_links.gpkg|layername=air_links", "al", "ogr")
    air_t, air_d = small_allpairs([(f['a'], f['b'], f['fly_min'], f['dist_km']) for f in al.getFeatures()])
    wl = QgsVectorLayer(B + r"\data\multimodal\water_freight_links.gpkg|layername=water_freight_links", "wl", "ogr")
    sea_t, sea_d = small_allpairs([(f['a'], f['b'], f['sail_min'], f['dist_km']) for f in wl.getFeatures()])
    T_pax = read_matrix(M + r"\2_trip_distribution\od_passenger.csv", "trips")
    T_frg = read_matrix(M + r"\2_trip_distribution\od_freight.csv", "trips")

    def fare_min(mode, dist_km, vot):
        fx, pk = mp.FARE[mode]; return (fx + pk*dist_km)/vot
    def gc_road(mode, t, vot, asc):
        ivt = t*mp.IVT_FACTOR[mode]; dist = t/60.0*mp.NOMINAL_KMH['road']
        return asc.get(mode, 0) + mp.TRANSFER_MIN[mode] + ivt + fare_min(mode, dist, vot)

    def pax_costs(i, j, t, vot, asc):
        g = {}
        for m in ('car', 'motorcycle', 'bus'):
            if m == 'motorcycle' and (i != j and t > MC_MAX_MIN): continue
            g[m] = gc_road(m, t, vot, asc)
        if i == j: return g
        lr = rail.get((i, j))
        if lr is not None:
            dist = lr/60.0*mp.NOMINAL_KMH['rail']
            g['rail'] = asc.get('rail', 0) + mp.TRANSFER_MIN['rail'] + acc_rail[i][0] + acc_rail[j][0] + lr + fare_min('rail', dist, vot)
        ai, aj = acc_air[i][1], acc_air[j][1]
        if ai != aj and air_t.get(ai, {}).get(aj, math.inf) < math.inf:
            g['air'] = asc.get('air', 0) + mp.TRANSFER_MIN['air'] + acc_air[i][0] + acc_air[j][0] + air_t[ai][aj] + fare_min('air', air_d[ai][aj], vot)
        lw = water.get((i, j))
        if lw is not None:
            dist = lw/60.0*mp.NOMINAL_KMH['water']
            g['water'] = asc.get('water', 0) + mp.TRANSFER_MIN['water'] + acc_wat[i][0] + acc_wat[j][0] + lw + fare_min('water', dist, vot)
        return g

    def frg_costs(i, j, t, asc):
        vot = VOT_GEN
        g = {'truck': gc_road('truck', t, vot, asc)}
        if i == j: return g
        lr = rail.get((i, j))
        if lr is not None:
            dist = lr/60.0*mp.NOMINAL_KMH['rail']
            g['rail'] = asc.get('rail', 0) + mp.TRANSFER_MIN['rail'] + acc_rail[i][0] + acc_rail[j][0] + lr + fare_min('rail', dist, vot)
        pi, pj = acc_sea[i][1], acc_sea[j][1]
        if pi != pj and sea_t.get(pi, {}).get(pj, math.inf) < math.inf:
            g['water'] = asc.get('water', 0) + mp.TRANSFER_MIN['water'] + acc_sea[i][0] + acc_sea[j][0] + sea_t[pi][pj] + fare_min('water', sea_d[pi][pj], vot)
        return g

    def logit_shares(g):
        mn = min(g.values()); ex = {m: math.exp(-THETA*(c-mn)) for m, c in g.items()}
        s = sum(ex.values()); return {m: e/s for m, e in ex.items()}

    # ---- fit pax ASC (interzonal shares to target over car/bus/rail/air) ----
    asc_p = dict(mp.ASC)
    for it in range(ASC_FIT_ITER):
        tot = {}
        for (i, j), tr in T_pax.items():
            if tr <= 0 or i == j: continue
            t = road.get((i, j))
            if t is None: continue
            for seg_vot, seg_sh in ((VOT_GEN, 1-BIZ_SHARE), (VOT_BIZ, BIZ_SHARE)):
                sh = logit_shares(pax_costs(i, j, t, seg_vot, asc_p))
                for m, s in sh.items(): tot[m] = tot.get(m, 0.0) + tr*seg_sh*s
        four = {m: tot.get(m, 0.0) for m in ('car', 'bus', 'rail', 'air')}
        ssum = sum(four.values())
        model_sh = {m: v/ssum for m, v in four.items()}
        maxdev = max(abs(model_sh[m]-target_pax[m]) for m in four)
        for m in ('bus', 'rail', 'air'):
            if model_sh[m] > 0 and target_pax[m] > 0:
                asc_p[m] += (1.0/THETA)*math.log(model_sh[m]/target_pax[m])
        if it % 5 == 0 or maxdev < 0.005:
            log("  pax ASC iter %d: model=%s maxdev=%.4f" % (
                it, {m: round(v, 4) for m, v in model_sh.items()}, maxdev))
        if maxdev < 0.005: break
    pax_final = {m: v/sum(tot.values()) for m, v in tot.items()}

    # ---- fit freight ASC ----
    asc_f = dict(mp.ASC)
    for it in range(ASC_FIT_ITER):
        tot_f = {}
        for (i, j), tr in T_frg.items():
            if tr <= 0 or i == j: continue
            t = road.get((i, j))
            if t is None: continue
            sh = logit_shares(frg_costs(i, j, t, asc_f))
            for m, s in sh.items(): tot_f[m] = tot_f.get(m, 0.0) + tr*s
        ssum = sum(tot_f.values())
        model_sh = {m: tot_f.get(m, 0.0)/ssum for m in ('truck', 'rail', 'water')}
        maxdev = max(abs(model_sh[m]-target_frg[m]) for m in model_sh)
        for m in ('rail', 'water'):
            if model_sh[m] > 0:
                asc_f[m + '_frg' if False else m] = asc_f.get(m, 0) + (1.0/THETA)*math.log(model_sh[m]/target_frg[m])
        if it % 5 == 0 or maxdev < 0.005:
            log("  frg ASC iter %d: model=%s maxdev=%.4f" % (
                it, {m: round(v, 4) for m, v in model_sh.items()}, maxdev))
        if maxdev < 0.005: break

    # ---- aggregate factors สำหรับโมเดลอำเภอ (จาก mode split สุดท้าย รวม intrazonal) ----
    tot_all = {}; trips_all = 0.0
    for (i, j), tr in T_pax.items():
        if tr <= 0: continue
        t = road.get((i, j))
        if t is None: continue
        trips_all += tr
        for seg_vot, seg_sh in ((VOT_GEN, 1-BIZ_SHARE), (VOT_BIZ, BIZ_SHARE)):
            sh = logit_shares(pax_costs(i, j, t, seg_vot, asc_p))
            for m, s in sh.items(): tot_all[m] = tot_all.get(m, 0.0) + tr*seg_sh*s
    pcu = {'car': 1.0, 'motorcycle': 0.33, 'bus': 2.5}
    fac_pax = sum(tot_all.get(m, 0)*pcu[m] for m in pcu)/trips_all
    sh_pax_all = {m: v/trips_all for m, v in tot_all.items()}

    tot_fall = {}; trips_fall = 0.0
    for (i, j), tr in T_frg.items():
        if tr <= 0: continue
        t = road.get((i, j))
        if t is None: continue
        trips_fall += tr
        sh = logit_shares(frg_costs(i, j, t, asc_f))
        for m, s in sh.items(): tot_fall[m] = tot_fall.get(m, 0.0) + tr*s
    fac_frg = tot_fall.get('truck', 0)*2.0/trips_fall
    sh_frg_all = {m: v/trips_fall for m, v in tot_fall.items()}

    with open(M + r"\5_calibration\mode_share_calibrated.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stream", "mode", "model_share_interzonal", "target_2565", "share_all_trips"])
        for m in ('car', 'bus', 'rail', 'air', 'motorcycle', 'water'):
            w.writerow(["passenger", m, round(pax_final.get(m, 0), 5),
                        target_pax.get(m, ""), round(sh_pax_all.get(m, 0), 5)])
        ssumf = sum(v for k, v in tot_f.items())
        for m in ('truck', 'rail', 'water'):
            w.writerow(["freight", m, round(tot_f.get(m, 0)/ssumf, 5),
                        target_frg.get(m, ""), round(sh_frg_all.get(m, 0), 5)])
    return asc_p, asc_f, fac_pax, fac_frg, sh_pax_all, sh_frg_all

def _mem():
    """หน่วยความจำสูงสุดที่โปรเซสนี้เคยใช้ (ไว้ไล่หาจุดที่ RAM พุ่งก่อนถูก kill)"""
    try:
        import resource
        return "peak RSS %.2f GB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576.0)
    except Exception:
        return "peak RSS n/a"


def _workers(sc):
    """จำนวน process ขนาน: scenario run.workers > จำนวนคอร์ (จำกัดไว้ที่ 4)

    worker แต่ละตัวได้สำเนากราฟผ่าน pickle เต็ม ๆ ตั้งค่าสูงเกินจำนวน RAM
    ของเครื่อง (เช่น runner ฟรีของ GitHub) จะโดน OOM kill เงียบ ๆ ระหว่างสร้าง pool
    """
    n = int(sc.get("workers", 0) or 0)
    if n <= 0:
        n = min(os.cpu_count() or 2, 4)
    return max(n, 1)


def main():
    from qgis.core import QgsApplication
    app = QgsApplication([], False); app.initQgis()
    target_pax, target_frg = read_targets()
    log("targets 2565 pax:", {k: round(v, 4) for k, v in target_pax.items()})
    log("targets 2565 frg:", {k: round(v, 4) for k, v in target_frg.items()})

    best = part_a()
    bp, sp = best['pax']; bf, sf = best['frg']
    log("BEST pax beta=%.3f (R2=%.3f k=%.4g) | frg beta=%.3f (R2=%.3f k=%.4g)" % (
        bp, sp['r2'], sp['k'], bf, sf['r2'], sf['k']))

    asc_p, asc_f, fac_pax, fac_frg, sh_p, sh_f = part_b(target_pax, target_frg)
    log("calibrated fac_pax=%.4f fac_frg=%.4f" % (fac_pax, fac_frg))

    # trip rate scaling: k จาก part A ใช้ fac เดิม (1.072/1.236) -> แปลงเป็น rate ใหม่ด้วย fac ใหม่
    import model_params as mp
    from lib import scenario as sc
    sc.apply(mp)
    k_p_flow = sp['k']            # scale ที่ต้องคูณ flow (raw trips) ให้ตรง obs pax_pcu
    k_f_flow = sf['k']
    rate_pax = mp.TRIP_RATE_PAX * k_p_flow / fac_pax
    ff_new = mp.FREIGHT_FACTOR * (k_f_flow/fac_frg) / (k_p_flow/fac_pax)
    log("calibrated TRIP_RATE_PAX=%.4f FREIGHT_FACTOR=%.4f" % (rate_pax, ff_new))

    with open(B + r"\config\calibrated_params.py", "w", encoding="utf-8") as fh:
        fh.write('# -*- coding: utf-8 -*-\n')
        fh.write('"""ค่าพารามิเตอร์ที่ผ่านการ calibrate (สร้างโดย 13_calibrate_params.py)\n')
        fh.write('วิธีได้มา: beta = grid search เทียบ AADT 2565 (พิกัด v2, PCU แยกสาย)\n')
        fh.write('trip rate/freight factor = least-squares scale ให้ k->1\n')
        fh.write('ASC = iterative fit เข้าเป้า mode share ทางการปี 2565 (สนข./NAM + สัดส่วนตันสินค้า)\n')
        fh.write('2-segment VOT: general %.0f baht/hr (%.0f%%) + business %.0f baht/hr (%.0f%%)"""\n' % (
            VOT_GEN*60, (1-BIZ_SHARE)*100, VOT_BIZ*60, BIZ_SHARE*100))
        fh.write('BETA_PAX = %.4f      # R2=%.3f medGEH=%.1f\n' % (bp, sp['r2'], sp['median_geh']))
        fh.write('BETA_FRG = %.4f      # R2=%.3f medGEH=%.1f\n' % (bf, sf['r2'], sf['median_geh']))
        fh.write('TRIP_RATE_PAX = %.4f # จาก 2.0 x k_flow(%.4g)/fac_pax(%.4f)\n' % (rate_pax, k_p_flow, fac_pax))
        fh.write('FREIGHT_FACTOR = %.4f\n' % ff_new)
        fh.write('VOT_GEN, VOT_BIZ, BIZ_SHARE = %.4f, %.4f, %.2f\n' % (VOT_GEN, VOT_BIZ, BIZ_SHARE))
        fh.write('MC_MAX_MIN = %.0f\n' % MC_MAX_MIN)
        fh.write('ASC_PAX = %r\n' % {k: round(v, 2) for k, v in asc_p.items()})
        fh.write('ASC_FRG = %r\n' % {k: round(v, 2) for k, v in asc_f.items()})
        fh.write('FAC_PAX_ROAD = %.4f  # PCU ถนนต่อ trip ผู้โดยสาร (ทุกทริป)\n' % fac_pax)
        fh.write('FAC_FRG_ROAD = %.4f\n' % fac_frg)
        fh.write('SHARE_PAX = %r  # สัดส่วนโหมดผู้โดยสาร (ทุกทริป)\n' % {k: round(v, 5) for k, v in sh_p.items()})
        fh.write('SHARE_FRG = %r\n' % {k: round(v, 5) for k, v in sh_f.items()})
    log("wrote config/calibrated_params.py")
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์

if __name__ == '__main__':
    import multiprocessing as _mpmain
    _mpmain.freeze_support()   # จำเป็นบน Windows (spawn)
    LOG = open(B + r"\output\_13.log", "w", encoding="utf-8")
    try: main()
    except Exception: log("ERR", traceback.format_exc()); raise
