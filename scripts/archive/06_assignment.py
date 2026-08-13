# -*- coding: utf-8 -*-
"""ขั้น 6: Trip Assignment (all-or-nothing) — OD โหมดถนน -> PCU -> ลงถนน
รวม car/mc/bus (pax) + truck (freight) เป็น PCU แล้ว assign ตามเส้นทางสั้นสุด
สะสมปริมาณต่อ link -> assigned_network.gpkg (vol_pcu)
รันผ่าน qpy.bat ; log -> output/_asg.log
"""
import os, csv, sys, math, traceback
# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT
sys.path.insert(0, (_ROOT + r"\config"))
import model_params as mp
from qgis.core import (QgsApplication, QgsVectorLayer, QgsPointXY, QgsGeometry, QgsFeature,
    QgsField, QgsVectorFileWriter, QgsCoordinateTransformContext, QgsSpatialIndex, QgsFeatureRequest)
from qgis.analysis import (QgsVectorLayerDirector, QgsNetworkStrategy, QgsGraphBuilder, QgsGraphAnalyzer)
from qgis.PyQt.QtCore import QVariant

B = _ROOT
M = B + r"\model"
LOG = open(B + r"\output\_asg.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

PCU = {'car': 1.0, 'motorcycle': 0.33, 'bus': 2.5, 'truck': 2.0}
BACKBONE = ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link')

class SpeedStrategy(QgsNetworkStrategy):
    def __init__(self, idx): super().__init__(); self.idx = idx
    def requiredAttributes(self): return [self.idx]
    def cost(self, distance, feature):
        s = feature.attributes()[self.idx]; s = float(s) if s and s > 5 else 40.0
        return distance/1000.0/s*60.0

def snap_backbone(net, pts):
    req = QgsFeatureRequest().setFilterExpression("highway IN ('%s')" % "','".join(BACKBONE))
    feats = [f for f in net.getFeatures(req)]; idx = QgsSpatialIndex(); idx.addFeatures(feats)
    fmap = {f.id(): f for f in feats}; out = []
    for p in pts:
        bd = 1e18; bpt = p
        for nid in idx.nearestNeighbor(p, 5):
            d, mp_, _, _ = fmap[nid].geometry().closestSegmentWithContext(p)
            if d < bd: bd = d; bpt = mp_
        out.append(QgsPointXY(bpt))
    return out

def load_pcu():
    """รวม OD โหมดถนนเป็น PCU: (i,j)->pcu"""
    od = {}
    for f, modes in [("3_mode_choice\\mode_split_passenger.csv", ('car','motorcycle','bus')),
                     ("3_mode_choice\\mode_split_freight.csv", ('truck',))]:
        for r in csv.DictReader(open(M + "\\" + f, encoding="utf-8")):
            m = r['mode']
            if m in modes:
                k = (int(r['orig_zone']), int(r['dest_zone']))
                od[k] = od.get(k, 0.0) + float(r['trips']) * PCU[m]
    return od

def main():
    app = QgsApplication([], False); app.initQgis()
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "net", "ogr")
    sidx = net.fields().indexOf('speed_kmh')
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zc = sorted([(f['zone_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    zones = [z[0] for z in zc]; pts = snap_backbone(net, [QgsPointXY(z[1]) for z in zc])
    zpos = {z: i for i, z in enumerate(zones)}

    od = load_pcu(); log("OD pairs with road PCU:", len(od), "| total PCU:", round(sum(od.values())))

    director = QgsVectorLayerDirector(net, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
    director.addStrategy(SpeedStrategy(sidx))
    builder = QgsGraphBuilder(net.crs())
    log("building graph...")
    tied = director.makeGraph(builder, pts)
    graph = builder.graph()
    vidx = [graph.findVertex(tp) for tp in tied]
    log("graph V=%d E=%d" % (graph.vertexCount(), graph.edgeCount()))

    edge_vol = {}   # edge_id -> pcu
    n = len(zones)
    for i in range(n):
        tree, cost = QgsGraphAnalyzer.dijkstra(graph, vidx[i], 0)
        for j in range(n):
            if i == j: continue
            flow = od.get((zones[i], zones[j]), 0.0)
            if flow <= 0: continue
            v = vidx[j]; guard = 0
            while tree[v] != -1 and guard < 200000:
                e = tree[v]; edge_vol[e] = edge_vol.get(e, 0.0) + flow
                v = graph.edge(e).fromVertex(); guard += 1
        if i % 20 == 0: log("  assigned origin", i+1, "/", n)

    # build output layer (graph sub-edges with volume)
    out_lyr = QgsVectorLayer("LineString?crs=EPSG:32647", "assigned_network", "memory"); dp = out_lyr.dataProvider()
    dp.addAttributes([QgsField('vol_pcu', QVariant.Double)]); out_lyr.updateFields()
    feats = []
    for e, vol in edge_vol.items():
        ed = graph.edge(e)
        p1 = graph.vertex(ed.fromVertex()).point(); p2 = graph.vertex(ed.toVertex()).point()
        f = QgsFeature(out_lyr.fields()); f.setGeometry(QgsGeometry.fromPolylineXY([p1, p2]))
        f.setAttributes([round(vol, 1)]); feats.append(f)
    dp.addFeatures(feats)
    out = B + r"\model\4_trip_assignment\assigned_network.gpkg"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out): os.remove(out)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "assigned_network"
    QgsVectorFileWriter.writeAsVectorFormatV3(out_lyr, out, QgsCoordinateTransformContext(), o)
    vols = [v for v in edge_vol.values()]
    log("assigned edges:", len(vols), "| vol max:", round(max(vols)), "| total veh-edge PCU:", round(sum(vols)))
    app.exitQgis(); log("DONE")

try:
    main()
except Exception:
    log("ERR", traceback.format_exc())
