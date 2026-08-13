import sys, traceback, numpy as np
# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit
B = _ROOT
sys.path.insert(0, B + r"\scripts")
L = open(B + r"\output\_tl.log", "w", encoding="utf-8")
def log(*a): L.write(" ".join(str(x) for x in a)+"\n"); L.flush()
try:
    from qgis.core import QgsApplication, QgsVectorLayer
    app = QgsApplication([], False); app.initQgis()
    from lib.transport_graph import build_road_graph, od_cost_matrix
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    G = build_road_graph(net, directed=True)
    log("directed graph: nodes=%d edges=%d oneway=%.1f%%" % (G.nN, G.nE, 100*G.Eoneway.mean()))
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    pts = sorted([(f['zone_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    tn = [G.nearest(p) for _, p in pts]
    cost = od_cost_matrix(G, tn)
    off = cost[~np.eye(len(tn), dtype=bool)]
    fin = off[np.isfinite(off)]
    log("OD 77x77 directed: finite=%.3f min/mean/max=%.0f/%.0f/%.0f" % (
        np.isfinite(off).mean(), fin.min(), fin.mean(), fin.max()))
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์
except Exception: log("ERR", traceback.format_exc()); raise
L.close()
