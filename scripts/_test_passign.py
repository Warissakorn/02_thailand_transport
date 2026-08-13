# -*- coding: utf-8 -*-
"""ทดสอบความถูกต้อง: passign.run_assign (ขนาน) == transport_graph.assign_multi (serial)
บนกราฟสุ่มเล็ก (directed + oneway ผสม) -> เขียนผล output/_testpa.log
รันผ่าน qpy.bat"""
import os, sys, traceback
import numpy as np
B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
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


def main():
    import multiprocessing as mp
    from lib.transport_graph import assign_multi
    import lib.passign as passign
    G, rng = build_random()
    log("graph: nN=%d nE=%d directed=%s oneway=%.0f%%" % (
        G.nN, G.nE, G.directed, 100*G.Eoneway.mean()))
    dems = make_demands(G, rng, K=3)

    serial = assign_multi(G, dems)
    log("serial done: totals=%s" % [round(f.sum(), 3) for f in serial])

    pool = mp.Pool(4, initializer=passign.init,
                   initargs=(G.Eu, G.Ev, G.Eoneway, G.edge_of, G.nN, G.nE, G.directed))
    par = passign.run_assign(pool, 4, G.Ec, dems)
    pool.close(); pool.join()
    log("parallel done: totals=%s" % [round(f.sum(), 3) for f in par])

    ok = True
    for ki in range(len(dems)):
        diff = float(np.abs(serial[ki] - par[ki]).max())
        rel = diff / max(serial[ki].max(), 1e-9)
        log("  K=%d max_abs_diff=%.3e rel=%.3e" % (ki, diff, rel))
        if diff > 1e-6:
            ok = False
    log("RESULT: %s" % ("PASS (parallel == serial)" if ok else "FAIL"))


if __name__ == '__main__':
    import multiprocessing as mp
    mp.freeze_support()
    try:
        main()
    except Exception:
        log("ERR", traceback.format_exc())
    log("DONE")
