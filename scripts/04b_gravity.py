# -*- coding: utf-8 -*-
"""ขั้น 4b: Gravity model (doubly-constrained / Furness) -> OD trip matrix
deterrence f(c)=exp(-beta*c) ; intrazonal cost = 0.5 * nearest interzonal
อ่าน P/A จาก trip_gen, cost จาก od_cost_road.csv ; รันผ่าน qpy.bat ; log -> output/_grav.log
out: model/2_trip_distribution/od_{passenger,freight}.csv
"""
import os, csv, sys, math, traceback
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
from qgis.core import QgsApplication, QgsVectorLayer

B = _ROOT
LOG = open(B + r"\output\_grav.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def read_pa(gpkg, ln, pcol, acol):
    l = QgsVectorLayer(gpkg + "|layername=" + ln, "x", "ogr")
    return {f['zone_id']: (f[pcol] or 0.0, f[acol] or 0.0) for f in l.getFeatures()}

def furness(zones, P, A, cost, beta, max_iter=50, tol=1e-3):
    n = len(zones); idx = {z: i for i, z in enumerate(zones)}
    # deterrence matrix
    f = [[0.0]*n for _ in range(n)]
    for i, zi in enumerate(zones):
        for j, zj in enumerate(zones):
            c = cost.get((zi, zj))
            f[i][j] = math.exp(-beta*c) if c is not None else 0.0
    Pv = [P[z] for z in zones]; Av = [A[z] for z in zones]
    # balance total A to total P
    tP = sum(Pv); tA = sum(Av)
    if tA > 0: Av = [a*tP/tA for a in Av]
    a = [1.0]*n; b = [1.0]*n
    for it in range(max_iter):
        # a_i = 1 / sum_j b_j A_j f_ij
        maxchg = 0.0
        for i in range(n):
            s = sum(b[j]*Av[j]*f[i][j] for j in range(n))
            na = 1.0/s if s > 0 else 0.0
            maxchg = max(maxchg, abs(na-a[i])/(a[i] or 1)); a[i] = na
        for j in range(n):
            s = sum(a[i]*Pv[i]*f[i][j] for i in range(n))
            b[j] = 1.0/s if s > 0 else 0.0
        if maxchg < tol: break
    T = [[a[i]*Pv[i]*b[j]*Av[j]*f[i][j] for j in range(n)] for i in range(n)]
    return T, it+1

def main():
    app = QgsApplication([], False); app.initQgis()
    # cost
    cost = {}; zones_set = set()
    with open(B + r"\model\2_trip_distribution\od_cost_road.csv", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        for row in r:
            o = int(row['orig_zone']); d = int(row['dest_zone']); zones_set.add(o)
            cost[(o, d)] = float(row['cost_min']) if row['cost_min'] != "" else None
    zones = sorted(zones_set)
    # intrazonal cost = 0.5 * nearest interzonal
    for zi in zones:
        nn = min((cost[(zi, zj)] for zj in zones if zj != zi and cost.get((zi, zj)) is not None), default=30.0)
        cost[(zi, zi)] = 0.5*nn
    log("zones:", len(zones))

    for stream, gpkg, ln, pcol, acol, beta in [
        ("passenger", B+r"\model\1_trip_generation\trip_gen_passenger.gpkg", "trip_gen_passenger", "P_pax", "A_pax", mp.GRAVITY_BETA_PAX),
        ("freight",   B+r"\model\1_trip_generation\trip_gen_freight.gpkg",   "trip_gen_freight",   "P_frg", "A_frg", mp.GRAVITY_BETA_FRG)]:
        pa = read_pa(gpkg, ln, pcol, acol)
        P = {z: pa[z][0] for z in zones}; A = {z: pa[z][1] for z in zones}
        T, iters = furness(zones, P, A, cost, beta, max_iter=mp.GRAVITY_MAX_ITER, tol=mp.GRAVITY_TOL)
        out = B + r"\model\2_trip_distribution\od_%s.csv" % stream
        tot = 0.0; intra = 0.0
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh); w.writerow(["orig_zone", "dest_zone", "trips"])
            for i, zi in enumerate(zones):
                for j, zj in enumerate(zones):
                    v = T[i][j]; tot += v
                    if i == j: intra += v
                    w.writerow([zi, zj, round(v, 2)])
        log("%s: iters=%d total_trips=%.0f intrazonal=%.1f%% beta=%.3f -> %s" % (
            stream, iters, tot, 100*intra/tot if tot else 0, beta, os.path.basename(out)))
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์

try:
    main()
except Exception:
    log("ERR", traceback.format_exc()); raise
