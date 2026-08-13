# -*- coding: utf-8 -*-
"""ขั้น 10a: จราจรถนน "รวม" ระดับจังหวัด (sequence-consistent)
= road door-to-door (car/mc/bus + truck) + access/egress ทุกโหมด (ราง/อากาศ/น้ำ)
ผลลัพธ์เดียว -> model/4_trip_assignment/assigned_road_total_prov.gpkg (vol_pcu)
ใช้ proper noding + scipy. รันผ่าน qpy.bat ; log -> output/_10a.log
"""
import os, csv, traceback, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"; M = B + r"\model"
LOG = open(B + r"\output\_10a.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def build_noded(layer):
    feats = []; vc = defaultdict(int)
    for f in layer.getFeatures():
        g = f.geometry(); pl = g.asPolyline() if not g.isMultipart() else [p for pr in g.asMultiPolyline() for p in pr]
        if len(pl) < 2: continue
        rv = [(round(p.x(), 1), round(p.y(), 1)) for p in pl]
        feats.append((rv, pl, f['speed_kmh'] or 40.0))
        for k in rv: vc[k] += 1
    ns = set()
    for rv, _, _ in feats: ns.add(rv[0]); ns.add(rv[-1])
    for k, c in vc.items():
        if c >= 2: ns.add(k)
    nid = {}; nxy = []; Eu = []; Ev = []; Ec = []; Eg = []
    for rv, pl, spd in feats:
        idxs = [i for i, k in enumerate(rv) if k in ns]
        for a, b in zip(idxs[:-1], idxs[1:]):
            ka, kb = rv[a], rv[b]
            if ka == kb: continue
            for k, p in ((ka, pl[a]), (kb, pl[b])):
                if k not in nid: nid[k] = len(nxy); nxy.append((p.x(), p.y()))
            sub = pl[a:b+1]; gs = QgsGeometry.fromPolylineXY(sub)
            Eu.append(nid[ka]); Ev.append(nid[kb]); Ec.append((gs.length()/1000.0)/max(spd, 3)*60.0); Eg.append(gs)
    return np.array(nxy), np.array(Eu), np.array(Ev), np.array(Ec), Eg

def nearest(nxy, p):
    dx = nxy[:, 0]-p.x(); dy = nxy[:, 1]-p.y(); return int(np.argmin(dx*dx+dy*dy))

def read_od(csvf, mode, zidx, Z):
    od = np.zeros((Z, Z))
    for r in csv.DictReader(open(M + r"\3_mode_choice\\" + csvf, encoding="utf-8")):
        if r['mode'] == mode:
            i = zidx.get(int(r['orig_zone'])); j = zidx.get(int(r['dest_zone']))
            if i is not None and j is not None: od[i][j] += float(r['trips'])
    return od

def endpoints(gpkg, ln):
    l = QgsVectorLayer(B + "\\" + gpkg + "|layername=" + ln, "a", "ogr")
    return {f['zone_id']: QgsPointXY(f.geometry().asPolyline()[-1]) for f in l.getFeatures()}

def assign_pairs(nxy, Eu, Ev, Ec, Eg, demand, out, name):
    nN = len(nxy); nE = len(Eu); edge_of = {}
    for e in range(nE):
        for a, b in ((Eu[e], Ev[e]), (Ev[e], Eu[e])):
            pe = edge_of.get((a, b))
            if pe is None or Ec[e] < Ec[pe]: edge_of[(a, b)] = e
    rows = np.concatenate([Eu, Ev]); cols = np.concatenate([Ev, Eu]); data = np.concatenate([Ec, Ec])
    csr = csr_matrix((data, (rows, cols)), shape=(nN, nN)); flow = np.zeros(nE)
    origins = sorted(demand.keys()); BATCH = 120
    for s0 in range(0, len(origins), BATCH):
        srcs = origins[s0:s0+BATCH]
        dmat, pred = dijkstra(csr, directed=False, indices=srcs, return_predecessors=True)
        for bi, on in enumerate(srcs):
            ds = dmat[bi]; ps = pred[bi]; acc = np.zeros(nN)
            for dn, v in demand[on].items(): acc[dn] += v
            if acc.sum() <= 0: continue
            for node in np.argsort(ds)[::-1]:
                if not np.isfinite(ds[node]): continue
                p = ps[node]
                if p < 0: continue
                e = edge_of.get((p, node))
                if e is not None: flow[e] += acc[node]; acc[p] += acc[node]
    lyr = QgsVectorLayer("LineString?crs=EPSG:32647", name, "memory"); dp = lyr.dataProvider()
    dp.addAttributes([QgsField('vol_pcu', QVariant.Double)]); lyr.updateFields()
    fl = []
    for e in range(nE):
        if flow[e] <= 0: continue
        ft = QgsFeature(lyr.fields()); ft.setGeometry(Eg[e]); ft.setAttributes([round(float(flow[e]), 1)]); fl.append(ft)
    dp.addFeatures(fl)
    if os.path.exists(out): os.remove(out)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = name
    QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out, QgsCoordinateTransformContext(), o)
    log("%s: %d links max=%.0f total=%.0f" % (name, len(fl), flow.max(), flow.sum()))

def main():
    app = QgsApplication([], False); app.initQgis()
    nxy, Eu, Ev, Ec, Eg = build_noded(QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "r", "ogr"))
    log("road nodes=%d edges=%d" % (len(nxy), len(Eu)))
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zc = sorted([(f['zone_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    zids = [z[0] for z in zc]; Z = len(zids); zidx = {z: i for i, z in enumerate(zids)}
    cnode = [nearest(nxy, p) for _, p in zc]
    def tnodes(g, l):
        ep = endpoints(g, l); return [nearest(nxy, ep[z]) for z in zids]
    term = {'rail': tnodes(r"data\zones_taz\access_rail.gpkg", "access_rail"),
            'air': tnodes(r"data\zones_taz\access_air.gpkg", "access_air"),
            'water': tnodes(r"data\zones_taz\access_water.gpkg", "access_water"),
            'sea': tnodes(r"data\zones_taz\access_seafreight.gpkg", "access_seafreight")}

    dem = defaultdict(lambda: defaultdict(float))
    # door-to-door road
    for csvf, modes in [("mode_split_passenger.csv", {'car': 1.0, 'motorcycle': 0.33, 'bus': 2.5}),
                        ("mode_split_freight.csv", {'truck': 2.0})]:
        for m, pcu in modes.items():
            od = read_od(csvf, m, zidx, Z)
            for i in range(Z):
                for j in range(Z):
                    if od[i][j] > 0: dem[cnode[i]][cnode[j]] += od[i][j]*pcu
    # access/egress
    def add_ae(csvf, mode, tk, pcu):
        od = read_od(csvf, mode, zidx, Z); oi = od.sum(1); ii = od.sum(0)
        for i in range(Z):
            if oi[i] > 0: dem[cnode[i]][term[tk][i]] += oi[i]*pcu
            if ii[i] > 0: dem[term[tk][i]][cnode[i]] += ii[i]*pcu
    add_ae("mode_split_passenger.csv", "rail", "rail", 1.0)
    add_ae("mode_split_passenger.csv", "air", "air", 1.0)
    add_ae("mode_split_passenger.csv", "water", "water", 1.0)
    add_ae("mode_split_freight.csv", "rail", "rail", 2.0)
    add_ae("mode_split_freight.csv", "water", "sea", 2.0)
    assign_pairs(nxy, Eu, Ev, Ec, Eg, dem, M + r"\4_trip_assignment\assigned_road_total_prov.gpkg", "assigned_road_total_prov")
    app.exitQgis(); log("DONE")

try: main()
except Exception: log("ERR", traceback.format_exc())
