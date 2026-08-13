# -*- coding: utf-8 -*-
"""ขั้น 6B: User-Equilibrium assignment (BPR + MSA/Frank-Wolfe)
กราฟระดับ feature (เชื่อม endpoint) -> อัปเดตเวลาตามความแออัดทุกรอบ -> จราจรกระจายหลายเส้น
BPR: t = t0*(1+0.15*(v/cap)^4) ; MSA: x += (1/n)(y-x)
รันผ่าน qpy.bat (background) ; log -> output/_eq.log
out: model/4_trip_assignment/assigned_eq.gpkg (vol_pcu)
"""
import os, csv, sys, math, heapq, traceback
import numpy as np
sys.path.insert(0, r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport\config")
import model_params as mp
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsPointXY, QgsVectorFileWriter, QgsCoordinateTransformContext, QgsSpatialIndex, QgsFeatureRequest)
from qgis.PyQt.QtCore import QVariant

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"; M = B + r"\model"
LOG = open(B + r"\output\_eq.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

PCU = {'car': 1.0, 'motorcycle': 0.33, 'bus': 2.5, 'truck': 2.0}
ALPHA, BETA = 0.15, 4.0
N_ITER = 18
EFF_HOURS, DEF_LANES = 16.0, 2  # daily capacity = cap/lane/hr * lanes * eff_hours
BACKBONE = ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link')

def load_pcu():
    od = {}
    for f, modes in [("3_mode_choice\\mode_split_passenger.csv", ('car','motorcycle','bus')),
                     ("3_mode_choice\\mode_split_freight.csv", ('truck',))]:
        for r in csv.DictReader(open(M + "\\" + f, encoding="utf-8")):
            if r['mode'] in modes:
                k = (int(r['orig_zone']), int(r['dest_zone']))
                od[k] = od.get(k, 0.0) + float(r['trips']) * PCU[r['mode']]
    return od

def main():
    app = QgsApplication([], False); app.initQgis()
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "net", "ogr")

    # ---- build feature-level node graph ----
    node_id = {}; nodes_xy = []
    def nid(pt):
        key = (round(pt.x()), round(pt.y()))
        i = node_id.get(key)
        if i is None:
            i = len(nodes_xy); node_id[key] = i; nodes_xy.append((pt.x(), pt.y()))
        return i
    E_u = []; E_v = []; E_t0 = []; E_cap = []; E_fid = []; E_geom = []
    for f in net.getFeatures():
        g = f.geometry()
        pl = g.asPolyline() if not g.isMultipart() else [p for part in g.asMultiPolyline() for p in part]
        if len(pl) < 2: continue
        u = nid(pl[0]); v = nid(pl[-1])
        if u == v: continue
        spd = f['speed_kmh'] or 40.0
        t0 = (g.length()/1000.0)/max(spd, 5)*60.0
        lanes = f['lanes']
        try: lanes = int(str(lanes).split(';')[0])
        except: lanes = DEF_LANES
        cap = (f['capacity'] or 800) * max(lanes, 1) * EFF_HOURS
        E_u.append(u); E_v.append(v); E_t0.append(t0); E_cap.append(cap); E_fid.append(f.id()); E_geom.append(g)
    nE = len(E_u); nN = len(nodes_xy)
    E_t0 = np.array(E_t0); E_cap = np.array(E_cap)
    log("graph: nodes=%d edges=%d" % (nN, nE))

    # adjacency (undirected): node -> list of (other, edge_idx)
    adj = [[] for _ in range(nN)]
    for e in range(nE):
        adj[E_u[e]].append((E_v[e], e)); adj[E_v[e]].append((E_u[e], e))

    # ---- tie zone centroids to nearest node (snap to backbone first) ----
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zc = sorted([(f['zone_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    zones = [z[0] for z in zc]
    # backbone snap
    req = QgsFeatureRequest().setFilterExpression("highway IN ('%s')" % "','".join(BACKBONE))
    bb = [f for f in net.getFeatures(req)]; bidx = QgsSpatialIndex(); bidx.addFeatures(bb)
    bmap = {f.id(): f for f in bb}
    nxy = np.array(nodes_xy)
    znode = []
    for zid, p in zc:
        bd = 1e18; bpt = p
        for fid in bidx.nearestNeighbor(QgsPointXY(p), 5):
            d, mp_, _, _ = bmap[fid].geometry().closestSegmentWithContext(QgsPointXY(p))
            if d < bd: bd = d; bpt = mp_
        dx = nxy[:, 0]-bpt.x(); dy = nxy[:, 1]-bpt.y()
        znode.append(int(np.argmin(dx*dx+dy*dy)))
    zpos = {z: i for i, z in enumerate(zones)}

    od = load_pcu()
    # group demand by origin node
    dem_by_o = {}
    for (i, j), v in od.items():
        if i == j or v <= 0: continue
        dem_by_o.setdefault(znode[zpos[i]], []).append((znode[zpos[j]], v))
    log("OD loaded, total PCU=%.0f" % sum(od.values()))

    def aon(tcost):
        """all-or-nothing ที่เวลา tcost[edge] -> flow[edge]"""
        flow = np.zeros(nE)
        for onode, dests in dem_by_o.items():
            dist = np.full(nN, np.inf); dist[onode] = 0.0
            pred_e = np.full(nN, -1, dtype=np.int64)
            pq = [(0.0, onode)]
            need = set(d for d, _ in dests); got = 0
            while pq:
                d, u = heapq.heappop(pq)
                if d > dist[u]: continue
                if u in need:
                    got += 1
                    if got >= len(need) and not pq: pass
                for w, e in adj[u]:
                    nd = d + tcost[e]
                    if nd < dist[w]: dist[w] = nd; pred_e[w] = e; heapq.heappush(pq, (nd, w))
            for dn, vol in dests:
                v = dn; guard = 0
                while pred_e[v] != -1 and guard < 500000:
                    e = pred_e[v]; flow[e] += vol
                    v = E_u[e] if E_v[e] == v else E_v[e]; guard += 1
        return flow

    # ---- MSA / Frank-Wolfe ----
    x = aon(E_t0.copy()); log("iter 1 (AON free-flow) done, max flow=%.0f" % x.max())
    for n in range(2, N_ITER+1):
        t = E_t0 * (1.0 + ALPHA*(x/E_cap)**BETA)
        y = aon(t)
        x = x + (1.0/n)*(y - x)
        # relative gap proxy: ||y-x||/||x||
        gap = np.abs(y-x).sum()/max(x.sum(), 1)
        if n % 3 == 0 or n == N_ITER: log("iter %2d  gap=%.4f  maxflow=%.0f" % (n, gap, x.max()))

    # ---- write equilibrium flows ----
    out = QgsVectorLayer("LineString?crs=EPSG:32647", "assigned_eq", "memory"); dp = out.dataProvider()
    dp.addAttributes([QgsField('vol_pcu', QVariant.Double), QgsField('voc', QVariant.Double)]); out.updateFields()
    feats = []
    for e in range(nE):
        if x[e] <= 0: continue
        f = QgsFeature(out.fields()); f.setGeometry(E_geom[e])
        f.setAttributes([round(float(x[e]), 1), round(float(x[e]/E_cap[e]), 3)]); feats.append(f)
    dp.addFeatures(feats)
    o = M + r"\4_trip_assignment\assigned_eq.gpkg"
    if os.path.exists(o): os.remove(o)
    opt = QgsVectorFileWriter.SaveVectorOptions(); opt.driverName = "GPKG"; opt.layerName = "assigned_eq"
    QgsVectorFileWriter.writeAsVectorFormatV3(out, o, QgsCoordinateTransformContext(), opt)
    log("wrote assigned_eq: %d links with flow | max=%.0f" % (len(feats), x.max()))
    app.exitQgis(); log("DONE")

try:
    main()
except Exception:
    log("ERR", traceback.format_exc())
