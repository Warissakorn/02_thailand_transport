# -*- coding: utf-8 -*-
"""ขั้น 4a: OD cost matrix (road) 77x77 — เวลาเดินทาง centroid->centroid
ใช้ QgsGraph + Dijkstra (travel_min). รันผ่าน qpy.bat ; log -> output/_od.log
out: model/2_trip_distribution/od_cost_road.csv  (orig,dest,cost_min)
"""
import os, csv, math, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsPointXY, QgsGeometry, QgsSpatialIndex,
    QgsFeatureRequest)
from qgis.analysis import (QgsVectorLayerDirector, QgsNetworkStrategy, QgsGraphBuilder, QgsGraphAnalyzer)

BACKBONE = ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link')

def snap_to_backbone(net, pts):
    """snap จุดเข้าหาถนนสายหลัก (backbone) ที่เชื่อมต่อกันแน่นอน"""
    req = QgsFeatureRequest().setFilterExpression("highway IN ('%s')" % "','".join(BACKBONE))
    feats = [f for f in net.getFeatures(req)]
    idx = QgsSpatialIndex(); idx.addFeatures(feats)
    fmap = {f.id(): f for f in feats}
    out = []
    for p in pts:
        nn = idx.nearestNeighbor(p, 5); bd = 1e18; bpt = p
        for nid in nn:
            d, mp, _, _ = fmap[nid].geometry().closestSegmentWithContext(p)
            if d < bd: bd = d; bpt = mp
        out.append(QgsPointXY(bpt))
    return out

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit
B = _ROOT
LOG = open(B + r"\output\_od.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

class TimeStrategy(QgsNetworkStrategy):
    """cost = เวลา(นาที) ของ sub-segment = distance(ม.)/1000 / speed(กม/ชม) * 60
    ต้องคิดจาก distance ของ sub-segment (ไม่ใช่ travel_min ทั้งเส้น เพราะ builder แตกเส้น)"""
    def __init__(self, idx): super().__init__(); self.idx = idx   # idx = speed_kmh
    def requiredAttributes(self): return [self.idx]
    def cost(self, distance, feature):
        spd = feature.attributes()[self.idx]
        spd = float(spd) if spd and spd > 5 else 40.0
        return distance/1000.0/spd*60.0

try:
    app = QgsApplication([], False); app.initQgis()
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "net", "ogr")
    spd_idx = net.fields().indexOf('speed_kmh')
    log("network edges:", net.featureCount(), "speed_kmh idx:", spd_idx)

    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zc = sorted([(f['zone_id'], f.geometry().asPoint(), f['NAME_1']) for f in cen.getFeatures()])
    zone_ids = [z[0] for z in zc]; pts0 = [QgsPointXY(z[1]) for z in zc]; names = {z[0]: z[2] for z in zc}
    pts = snap_to_backbone(net, pts0)
    log("centroids:", len(pts), "(snapped to backbone roads)")

    director = QgsVectorLayerDirector(net, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
    director.addStrategy(TimeStrategy(spd_idx))
    builder = QgsGraphBuilder(net.crs())
    log("building graph...")
    tied = director.makeGraph(builder, pts)
    graph = builder.graph()
    log("graph built. vertices:", graph.vertexCount(), "edges:", graph.edgeCount())

    vidx = [graph.findVertex(tp) for tp in tied]
    n = len(vidx)
    cost_matrix = [[None]*n for _ in range(n)]
    unreachable = 0
    for i in range(n):
        tree, cost = QgsGraphAnalyzer.dijkstra(graph, vidx[i], 0)
        for j in range(n):
            c = cost[vidx[j]]
            if c < 0 or not math.isfinite(c):
                unreachable += 1; cost_matrix[i][j] = None
            else:
                cost_matrix[i][j] = round(c, 2)
        if i % 20 == 0: log("  dijkstra origin", i+1, "/", n)

    # write long-format CSV
    out = B + r"\model\2_trip_distribution\od_cost_road.csv"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["orig_zone", "dest_zone", "cost_min"])
        for i in range(n):
            for j in range(n):
                w.writerow([zone_ids[i], zone_ids[j], cost_matrix[i][j] if cost_matrix[i][j] is not None else ""])
    # diagnostics
    diag_ok = sum(1 for i in range(n) if cost_matrix[i][i] == 0 or (cost_matrix[i][i] is not None and cost_matrix[i][i] < 1))
    finite = [cost_matrix[i][j] for i in range(n) for j in range(n) if i != j and cost_matrix[i][j] is not None]
    log("unreachable pairs:", unreachable, "/", n*n)
    log("OD cost min/mean/max (min):", round(min(finite),1), round(sum(finite)/len(finite),1), round(max(finite),1))
    # sample: Bangkok(?) find zone by name
    import statistics
    log("wrote", out)
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์
except Exception:
    log("ERR", traceback.format_exc()); raise
