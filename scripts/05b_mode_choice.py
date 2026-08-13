# -*- coding: utf-8 -*-
"""ขั้น 5b: Mode Choice (multinomial logit) — door-to-door generalized cost
GC_m = ASC + transfer + access + egress + IVT + fare/VOT  (นาที-เทียบเท่า)
P_m = exp(-θ·GC_m)/Σ ; โหมดที่ใช้ได้เท่านั้น ; intrazonal = ถนนเท่านั้น
รันผ่าน qpy.bat ; log -> output/_mc.log
out: model/3_mode_choice/mode_split_{passenger,freight}.csv + mode_share_summary.csv
"""
import os, csv, sys, math, heapq, traceback
sys.path.insert(0, r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport\config")
import model_params as mp
from qgis.core import QgsApplication, QgsVectorLayer

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
M = B + r"\model"
LOG = open(B + r"\output\_mc.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def read_matrix(path, vcol):
    d = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        v = r[vcol]
        d[(int(r['orig_zone']), int(r['dest_zone']))] = float(v) if v != "" else None
    return d

def read_access(gpkg, ln, termfield):
    l = QgsVectorLayer(B + "\\" + gpkg + "|layername=" + ln, "a", "ogr")
    return {f['zone_id']: (f['access_min'], f[termfield] if termfield else None) for f in l.getFeatures()}

def small_allpairs(nodes, edges):
    """Dijkstra all-pairs บนกราฟเล็ก (edges: list (a,b,cost,dist)) -> (timeAP, distAP)"""
    adj = {n: [] for n in nodes}
    for a, b, c, dk in edges:
        if a in adj and b in adj:
            adj[a].append((b, c, dk)); adj[b].append((a, c, dk))
    def dij(src, useidx):
        dist = {n: math.inf for n in nodes}; dist[src] = 0; pq = [(0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]: continue
            for v, c, dk in adj[u]:
                w = c if useidx == 0 else dk
                nd = d + w
                if nd < dist[v]: dist[v] = nd; heapq.heappush(pq, (nd, v))
        return dist
    tAP = {n: dij(n, 0) for n in nodes}; dAP = {n: dij(n, 1) for n in nodes}
    return tAP, dAP

def main():
    app = QgsApplication([], False); app.initQgis()
    road = read_matrix(M + r"\2_trip_distribution\od_cost_road.csv", "cost_min")
    rail = read_matrix(M + r"\3_mode_choice\linehaul_rail.csv", "min")
    water = read_matrix(M + r"\3_mode_choice\linehaul_water.csv", "min")
    acc_rail = read_access(r"data\zones_taz\access_rail.gpkg", "access_rail", None)
    acc_air  = read_access(r"data\zones_taz\access_air.gpkg", "access_air", "terminal")
    acc_wat  = read_access(r"data\zones_taz\access_water.gpkg", "access_water", None)
    acc_sea  = read_access(r"data\zones_taz\access_seafreight.gpkg", "access_seafreight", "port")

    # air all-pairs (เวลา/กม.) บน 41 สนามบิน
    al = QgsVectorLayer(B + r"\data\multimodal\air_links.gpkg|layername=air_links", "al", "ogr")
    air_edges = [(f['a'], f['b'], f['fly_min'], f['dist_km']) for f in al.getFeatures()]
    air_nodes = set([e[0] for e in air_edges] + [e[1] for e in air_edges])
    air_t, air_d = small_allpairs(air_nodes, air_edges)
    # seafreight all-pairs บน 10 ท่าเรือ
    wl = QgsVectorLayer(B + r"\data\multimodal\water_freight_links.gpkg|layername=water_freight_links", "wl", "ogr")
    sea_edges = [(f['a'], f['b'], f['sail_min'], f['dist_km']) for f in wl.getFeatures()]
    sea_nodes = set([e[0] for e in sea_edges] + [e[1] for e in sea_edges])
    sea_t, sea_d = small_allpairs(sea_nodes, sea_edges)

    VOT = mp.VOT_THB_PER_MIN
    def fare_min(mode, dist_km):
        fx, pk = mp.FARE[mode]; return (fx + pk*dist_km)/VOT
    def gc_road(mode, t):
        ivt = t*mp.IVT_FACTOR[mode]; dist = t/60.0*mp.NOMINAL_KMH['road']
        return mp.ASC[mode] + mp.TRANSFER_MIN[mode] + ivt + fare_min(mode, dist)

    def costs(i, j, freight=False):
        """คืน dict mode->GC สำหรับโหมดที่ใช้ได้"""
        g = {}
        t = road.get((i, j))
        if t is None: return g
        if i == j:  # intrazonal: ถนนเท่านั้น
            if freight: g['truck'] = gc_road('truck', t)
            else:
                for m in ('car', 'motorcycle', 'bus'): g[m] = gc_road(m, t)
            return g
        if freight:
            g['truck'] = gc_road('truck', t)
            lr = rail.get((i, j))
            if lr is not None:
                dist = lr/60.0*mp.NOMINAL_KMH['rail']
                g['rail'] = mp.ASC['rail'] + mp.TRANSFER_MIN['rail'] + acc_rail[i][0] + acc_rail[j][0] + lr + fare_min('rail', dist)
            pi, pj = acc_sea[i][1], acc_sea[j][1]
            if pi != pj and sea_t.get(pi, {}).get(pj, math.inf) < math.inf:
                lh = sea_t[pi][pj]; dk = sea_d[pi][pj]
                g['water'] = mp.ASC['water'] + mp.TRANSFER_MIN['water'] + acc_sea[i][0] + acc_sea[j][0] + lh + fare_min('water', dk)
        else:
            for m in ('car', 'motorcycle', 'bus'): g[m] = gc_road(m, t)
            lr = rail.get((i, j))
            if lr is not None:
                dist = lr/60.0*mp.NOMINAL_KMH['rail']
                g['rail'] = mp.ASC['rail'] + mp.TRANSFER_MIN['rail'] + acc_rail[i][0] + acc_rail[j][0] + lr + fare_min('rail', dist)
            ai, aj = acc_air[i][1], acc_air[j][1]
            if ai != aj and air_t.get(ai, {}).get(aj, math.inf) < math.inf:
                lh = air_t[ai][aj]; dk = air_d[ai][aj]
                g['air'] = mp.ASC['air'] + mp.TRANSFER_MIN['air'] + acc_air[i][0] + acc_air[j][0] + lh + fare_min('air', dk)
            lw = water.get((i, j))
            if lw is not None:
                dist = lw/60.0*mp.NOMINAL_KMH['water']
                g['water'] = mp.ASC['water'] + mp.TRANSFER_MIN['water'] + acc_wat[i][0] + acc_wat[j][0] + lw + fare_min('water', dist)
        return g

    th = mp.LOGIT_THETA
    for stream, odfile, freight in [("passenger", "od_passenger.csv", False), ("freight", "od_freight.csv", True)]:
        T = read_matrix(M + r"\2_trip_distribution\\" + odfile, "trips")
        out = M + r"\3_mode_choice\mode_split_%s.csv" % stream
        totals = {}
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["orig_zone", "dest_zone", "mode", "trips"])
            for (i, j), trips in T.items():
                if trips <= 0: continue
                g = costs(i, j, freight)
                if not g: continue
                mn = min(g.values())
                exps = {m: math.exp(-th*(c-mn)) for m, c in g.items()}
                s = sum(exps.values())
                for m, e in exps.items():
                    fl = trips*e/s
                    if fl > 0.01:
                        w.writerow([i, j, m, round(fl, 2)]); totals[m] = totals.get(m, 0)+fl
        tot = sum(totals.values())
        log("=== %s mode share ===" % stream)
        for m, v in sorted(totals.items(), key=lambda x: -x[1]):
            log("  %-11s %12s  %5.1f%%" % (m, format(int(v), ","), 100*v/tot))
        # summary csv
        with open(M + r"\3_mode_choice\mode_share_%s.csv" % stream, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["mode", "trips", "share_pct"])
            for m, v in sorted(totals.items(), key=lambda x: -x[1]): w.writerow([m, round(v), round(100*v/tot, 2)])
    app.exitQgis(); log("DONE")

try:
    main()
except Exception:
    log("ERR", traceback.format_exc())
