# -*- coding: utf-8 -*-
"""Diagnostic: ทำไมสายความจุสูงถึง flow=0 (directed reachability กับ centroid จริง)
สร้าง super-source เชื่อม 0-cost ไปทุก district centroid tie-node:
  fwd[v]  = v เข้าถึงได้จาก centroid ใด ๆ (directed)
  back[v] = จาก v ไปถึง centroid ใด ๆ ได้ (dijkstra บนกราฟกลับทิศ)
edge (u->v) จะรับ flow ได้ก็ต่อเมื่อ fwd[u] และ back[v] (อยู่บนเส้นทาง centroid->..->centroid)
สายที่ fwd[u]&back[v] = False -> "รับ flow ไม่ได้แน่นอน" = bug (directed one-way trap)
รายงานเป็น กม. รวม + เฉพาะสายความจุสูง (cap>=p90) ; log output/_conn.log ; qpy.bat
"""
import os, sys, traceback
import numpy as np
B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
sys.path.insert(0, B + r"\scripts")
LOG = open(B + r"\output\_conn.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()


def main():
    from qgis.core import QgsApplication, QgsVectorLayer
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    from lib.transport_graph import build_road_graph, robust_tie
    app = QgsApplication([], False); app.initQgis()
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    G = build_road_graph(net, directed=True)
    km = G.Elen/1000.0
    hc = G.Ecap_hr >= np.percentile(G.Ecap_hr, 90)
    log("graph nodes=%d edges=%d oneway=%.1f%% | high-cap(cap>=p90) %.0f km" % (
        G.nN, G.nE, 100*G.Eoneway.mean(), km[hc].sum()))

    cen = QgsVectorLayer(B + r"\data\zones_taz\district_centroids.gpkg|layername=district_centroids", "c", "ogr")
    pts = [f.geometry().asPoint() for f in cen.getFeatures()]
    cnodes, _ = robust_tie(G, pts)
    cnodes = np.unique(np.array(cnodes))
    log("centroid tie-nodes: %d" % len(cnodes))

    S = G.nN
    def aug(mat):
        co = mat.tocoo()
        r = np.concatenate([co.row, np.full(len(cnodes), S)])
        c = np.concatenate([co.col, cnodes])
        d = np.concatenate([co.data, np.zeros(len(cnodes))])
        return csr_matrix((d, (r, c)), shape=(S+1, S+1))
    fwd = np.isfinite(dijkstra(aug(G.csr), indices=S))[:S]           # reach จาก centroid
    back = np.isfinite(dijkstra(aug(G.csr.T.tocsr()), indices=S))[:S]  # ไปถึง centroid ได้
    log("nodes fwd-reachable=%.2f%% | back-reachable=%.2f%%" % (100*fwd.mean(), 100*back.mean()))

    usable = fwd[G.Eu] & back[G.Ev]
    bad = ~usable
    log("--- ทั้งกราฟ: edges รับ flow ไม่ได้ (directed) = %.0f km / %.0f km (%.1f%%) ---" % (
        km[bad].sum(), km.sum(), 100*km[bad].sum()/km.sum()))
    log("--- สายความจุสูง (cap>=p90, %.0f km) ---" % km[hc].sum())
    log("  รับ flow ไม่ได้ (directed one-way trap/unreachable) = %.0f km (%.1f%%)" % (
        km[hc & bad].sum(), 100*km[hc & bad].sum()/km[hc].sum()))
    log("  เชื่อมต่อครบ (zero flow = AON ไม่เลือก)              = %.0f km (%.1f%%)" % (
        km[hc & usable].sum(), 100*km[hc & usable].sum()/km[hc].sum()))
    app.exitQgis(); log("DONE")


if __name__ == '__main__':
    try: main()
    except Exception: log("ERR", traceback.format_exc())
