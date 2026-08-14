# -*- coding: utf-8 -*-
"""ทดสอบความถูกต้อง: passign.run_assign (ขนาน) == assign_multi (serial) == reference
บนกราฟสุ่มเล็ก (directed + oneway ผสม) -> เขียนผล output/_testpa.log

reference คือวิธีเดิมที่วนทุก node ในกราฟ เก็บไว้ในไฟล์ทดสอบเพื่อยืนยันว่าการเปลี่ยนมาไล่
เฉพาะ node บนเส้นทาง (lib/*.ancestors) ให้ flow เท่าเดิม — ถ้าแก้ทั้งสองทางผิดพร้อมกัน
การเทียบขนาน-กับ-serial อย่างเดียวจะจับไม่ได้

exit 1 เมื่อ FAIL (ใช้เป็นด่านใน workflow ก่อนขั้น district ที่ใช้เวลานาน)"""
import os, sys, traceback
import numpy as np
# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT
B = _ROOT
sys.path.insert(0, B + r"\scripts")
LOG = open(B + r"\output\_testpa.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()


def build_random():
    from lib.transport_graph import Graph
    rng = np.random.default_rng(42)
    nN = 300
    nxy = rng.random((nN, 2)) * 1000
    # สร้าง edge เชื่อมเพื่อนบ้านใกล้ ๆ ให้กราฟค่อนข้างต่อกัน
    Eu = []; Ev = []; Ec = []; Eow = []
    for u in range(nN):
        d = ((nxy[:, 0]-nxy[u, 0])**2 + (nxy[:, 1]-nxy[u, 1])**2)
        for v in np.argsort(d)[1:5]:
            Eu.append(u); Ev.append(int(v))
            Ec.append(float(rng.uniform(1.0, 20.0)))   # ต้นทุนสุ่มต่อเนื่อง (เลี่ยง tie)
            Eow.append(int(rng.random() < 0.3))         # ~30% oneway
    Eg = [None] * len(Eu)
    G = Graph(nxy, Eu, Ev, Ec, Eg, Eow)
    return G, rng


def make_demands(G, rng, K=3):
    dems = []
    nodes = list(range(G.nN))
    for _ in range(K):
        d = {}
        origins = rng.choice(nodes, size=60, replace=False)
        for o in origins:
            dests = rng.choice(nodes, size=8, replace=False)
            dd = {int(x): float(rng.uniform(1, 100)) for x in dests if int(x) != int(o)}
            if dd:
                d[int(o)] = dd
        dems.append(d)
    return dems


def assign_multi_reference(G, demands):
    """วิธีเดิม: วนทุก node ในกราฟเรียงระยะทางมาก->น้อย (ช้าแต่ตรงไปตรงมา)"""
    from scipy.sparse.csgraph import dijkstra
    K = len(demands)
    flows = [np.zeros(G.nE) for _ in range(K)]
    all_origins = sorted(set().union(*[set(d.keys()) for d in demands]))
    dmat, pred = dijkstra(G.csr, directed=G.directed, indices=all_origins,
                          return_predecessors=True)
    nodes = np.arange(G.nN)
    for bi, on in enumerate(all_origins):
        ds = dmat[bi]; ps = pred[bi]
        e_of = G.edge_lookup(ps, nodes)
        for ki in range(K):
            dd = demands[ki].get(on)
            if not dd:
                continue
            acc = np.zeros(G.nN)
            for dn, v in dd.items():
                acc[dn] += v
            for node in np.argsort(ds)[::-1]:
                if not np.isfinite(ds[node]):
                    continue
                e = e_of[node]
                if e >= 0:
                    flows[ki][e] += acc[node]; acc[ps[node]] += acc[node]
    return flows


def main():
    import multiprocessing as mp
    from lib.transport_graph import assign_multi
    import lib.passign as passign
    G, rng = build_random()
    log("graph: nN=%d nE=%d directed=%s oneway=%.0f%%" % (
        G.nN, G.nE, G.directed, 100*G.Eoneway.mean()))
    dems = make_demands(G, rng, K=3)

    ref = assign_multi_reference(G, dems)
    log("reference done: totals=%s" % [round(f.sum(), 3) for f in ref])

    serial = assign_multi(G, dems)
    log("serial done: totals=%s" % [round(f.sum(), 3) for f in serial])

    pool = mp.Pool(4, initializer=passign.init,
                   initargs=(G.Eu, G.Ev, G.Eoneway, G.lk_key, G.lk_edge, G.nN, G.nE, G.directed))
    par = passign.run_assign(pool, 4, G.Ec, dems)
    pool.close(); pool.join()
    log("parallel done: totals=%s" % [round(f.sum(), 3) for f in par])

    ok = True
    for ki in range(len(dems)):
        d_par = float(np.abs(ref[ki] - par[ki]).max())
        d_ser = float(np.abs(ref[ki] - serial[ki]).max())
        log("  K=%d max_abs_diff vs reference: serial=%.3e parallel=%.3e" % (ki, d_ser, d_par))
        if d_par > 1e-6 or d_ser > 1e-6:
            ok = False
    log("RESULT: %s" % ("PASS (pruned == serial == reference)" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == '__main__':
    import multiprocessing as mp
    mp.freeze_support()
    try:
        rc = main()
    except Exception:
        log("ERR", traceback.format_exc()); raise
    log("DONE")
    print(open(B + r"\output\_testpa.log", encoding="utf-8").read())
    sys.exit(rc)
