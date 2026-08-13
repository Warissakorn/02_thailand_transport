# -*- coding: utf-8 -*-
"""ขั้น 5a: line-haul OD matrix ของราง + เรือ(ferry) — เวลา terminal->terminal
tie จุด = terminal ใกล้สุดของแต่ละโซน (ปลายเส้น access connector)
ราง/เรือมี speed_kmh -> ใช้ speed strategy. รันผ่าน qpy.bat ; log -> output/_lh.log
out: model/3_mode_choice/linehaul_{rail,water}.csv  (orig,dest,min ; ว่าง=เข้าไม่ถึง)
"""
import os, csv, math, traceback
from qgis.core import QgsApplication, QgsVectorLayer, QgsPointXY
from qgis.analysis import (QgsVectorLayerDirector, QgsNetworkStrategy, QgsGraphBuilder, QgsGraphAnalyzer)

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_lh.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

class SpeedStrategy(QgsNetworkStrategy):
    def __init__(self, idx): super().__init__(); self.idx = idx
    def requiredAttributes(self): return [self.idx]
    def cost(self, distance, feature):
        s = feature.attributes()[self.idx]; s = float(s) if s and s > 1 else 30.0
        return distance/1000.0/s*60.0

def term_points(access_gpkg, ln):
    """ปลายเส้น access connector = ตำแหน่ง terminal ต่อ zone (เรียงตาม zone_id)"""
    l = QgsVectorLayer(B + "\\" + access_gpkg + "|layername=" + ln, "a", "ogr")
    d = {}
    for f in l.getFeatures():
        pl = f.geometry().asPolyline()
        d[f['zone_id']] = QgsPointXY(pl[-1])  # ปลายทาง = terminal
    return [d[z] for z in sorted(d)], sorted(d)

def linehaul(net_gpkg, ln, access_gpkg, access_ln, name):
    net = QgsVectorLayer(B + "\\" + net_gpkg + "|layername=" + ln, "n", "ogr")
    sidx = net.fields().indexOf('speed_kmh')
    pts, zones = term_points(access_gpkg, access_ln)
    director = QgsVectorLayerDirector(net, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
    director.addStrategy(SpeedStrategy(sidx))
    builder = QgsGraphBuilder(net.crs())
    tied = director.makeGraph(builder, pts)
    graph = builder.graph()
    vidx = [graph.findVertex(tp) for tp in tied]
    n = len(vidx); reach = 0
    out = B + r"\model\3_mode_choice\linehaul_%s.csv" % name
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["orig_zone", "dest_zone", "min"])
        for i in range(n):
            tree, cost = QgsGraphAnalyzer.dijkstra(graph, vidx[i], 0)
            for j in range(n):
                c = cost[vidx[j]]
                ok = (c >= 0 and math.isfinite(c))
                if ok and i != j: reach += 1
                w.writerow([zones[i], zones[j], round(c, 2) if ok else ""])
    log("%s: graph V=%d E=%d | reachable interzonal pairs=%d/%d" % (name, graph.vertexCount(), graph.edgeCount(), reach, n*(n-1)))

try:
    app = QgsApplication([], False); app.initQgis()
    linehaul(r"data\network\rail_clean.gpkg", "rail_clean", r"data\zones_taz\access_rail.gpkg", "access_rail", "rail")
    linehaul(r"data\network\water_clean.gpkg", "water_clean", r"data\zones_taz\access_water.gpkg", "access_water", "water")
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
