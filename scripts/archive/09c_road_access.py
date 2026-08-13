# -*- coding: utf-8 -*-
"""ขั้น 9c: เพิ่ม access/egress legs (ถนน) ของผู้ใช้ราง/อากาศ/น้ำ ลง road assignment
ผู้โดยสารราง/อากาศ/น้ำ: ขับรถ โซน<->terminal (PCU 1.0)
สินค้าราง/เรือ: รถบรรทุก โซน<->railyard/ท่าเรือ (PCU 2.0)
-> เขียนทับ assigned_road_pax/frg (รวม access แล้ว) + assigned_access_egress (เฉพาะ access/egress)
ใช้ proper noding + scipy. รันผ่าน qpy.bat (background) ; log -> output/_ac.log
"""
import os, csv, traceback, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"; M = B + r"\model"
LOG = open(B + r"\output\_ac.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def build_noded(layer):
    feats = []; vcount = defaultdict(int)
    for f in layer.getFeatures():
        g = f.geometry(); pl = g.asPolyline() if not g.isMultipart() else [p for pr in g.asMultiPolyline() for p in pr]
        if len(pl) < 2: continue
        rv = [(round(p.x(), 1), round(p.y(), 1)) for p in pl]
        feats.append((rv, pl, f['speed_kmh'] or 40.0))
        for k in rv: vcount[k] += 1
    nodeset = set()
    for rv, _, _ in feats: nodeset.add(rv[0]); nodeset.add(rv[-1])
    for k, c in vcount.items():
        if c >= 2: nodeset.add(k)
    node_id = {}; nxy = []; Eu = []; Ev = []; Ec = []; Eg = []
    for rv, pl, spd in feats:
        idxs = [i for i, k in enumerate(rv) if k in nodeset]
        for a, b in zip(idxs[:-1], idxs[1:]):
            ka, kb = rv[a], rv[b]
            if ka == kb: continue
            for k, p in ((ka, pl[a]), (kb, pl[b])):
                if k not in node_id: node_id[k] = len(nxy); nxy.append((p.x(), p.y()))
            sub = pl[a:b+1]; gsub = QgsGeometry.fromPolylineXY(sub)
            Eu.append(node_id[ka]); Ev.append(node_id[kb]); Ec.append((gsub.length()/1000.0)/max(spd, 3)*60.0); Eg.append(gsub)
    return np.array(nxy), np.array(Eu), np.array(Ev), np.array(Ec), Eg

def nearest(nxy, p):
    dx = nxy[:, 0]-p.x(); dy = nxy[:, 1]-p.y(); return int(np.argmin(dx*dx+dy*dy))

def read_mode_od(csvf, mode, zidx, Z):
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
    """demand: dict origin_node -> dict(dest_node -> pcu)"""
    nN = len(nxy); nE = len(Eu)
    edge_of = {}
    for e in range(nE):
        for a, b in ((Eu[e], Ev[e]), (Ev[e], Eu[e])):
            pe = edge_of.get((a, b))
            if pe is None or Ec[e] < Ec[pe]: edge_of[(a, b)] = e
    rows = np.concatenate([Eu, Ev]); cols = np.concatenate([Ev, Eu]); data = np.concatenate([Ec, Ec])
    csr = csr_matrix((data, (rows, cols)), shape=(nN, nN))
    origins = sorted(demand.keys()); flow = np.zeros(nE)
    BATCH = 120
    for s0 in range(0, len(origins), BATCH):
        srcs = origins[s0:s0+BATCH]
        dmat, pred = dijkstra(csr, directed=False, indices=srcs, return_predecessors=True)
        for bi, onode in enumerate(srcs):
            dist_s = dmat[bi]; pred_s = pred[bi]; acc = np.zeros(nN)
            for dn, v in demand[onode].items(): acc[dn] += v
            if acc.sum() <= 0: continue
            for node in np.argsort(dist_s)[::-1]:
                if not np.isfinite(dist_s[node]): continue
                p = pred_s[node]
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
    log("%s: %d links | max=%.0f total=%.0f" % (name, len(fl), flow.max(), flow.sum()))

def main():
    app = QgsApplication([], False); app.initQgis()
    road = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "r", "ogr")
    nxy, Eu, Ev, Ec, Eg = build_noded(road)
    log("road graph nodes=%d edges=%d" % (len(nxy), len(Eu)))

    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zc = sorted([(f['zone_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    zids = [z[0] for z in zc]; Z = len(zids); zidx = {z: i for i, z in enumerate(zids)}
    cnode = [nearest(nxy, p) for _, p in zc]

    # terminal road-node per province per mode
    def term_nodes(gpkg, ln):
        ep = endpoints(gpkg, ln); return [nearest(nxy, ep[z]) for z in zids]
    tn = {'rail': term_nodes(r"data\zones_taz\access_rail.gpkg", "access_rail"),
          'air': term_nodes(r"data\zones_taz\access_air.gpkg", "access_air"),
          'water': term_nodes(r"data\zones_taz\access_water.gpkg", "access_water"),
          'sea': term_nodes(r"data\zones_taz\access_seafreight.gpkg", "access_seafreight")}

    # OD per mode
    od = {('pax', m): read_mode_od("mode_split_passenger.csv", m, zidx, Z) for m in ('car', 'motorcycle', 'bus', 'rail', 'air', 'water')}
    od.update({('frg', m): read_mode_od("mode_split_freight.csv", m, zidx, Z) for m in ('truck', 'rail', 'water')})

    def add_access(dem, mode_od, term, pcu):
        """เพิ่ม access(โซน->terminal) + egress(terminal->โซน) ลง dem"""
        out_i = mode_od.sum(1); in_i = mode_od.sum(0)
        for i in range(Z):
            if out_i[i] > 0: dem[cnode[i]][term[i]] += out_i[i]*pcu
            if in_i[i] > 0: dem[term[i]][cnode[i]] += in_i[i]*pcu

    # ---- PASSENGER road total (door-to-door road + access/egress of rail/air/water) ----
    dem_pax = defaultdict(lambda: defaultdict(float))
    for m, p in (('car', 1.0), ('motorcycle', 0.33), ('bus', 2.5)):
        o = od[('pax', m)]
        for i in range(Z):
            for j in range(Z):
                if o[i][j] > 0: dem_pax[cnode[i]][cnode[j]] += o[i][j]*p
    for m in ('rail', 'air', 'water'):
        add_access(dem_pax, od[('pax', m)], tn[m], 1.0)
    assign_pairs(nxy, Eu, Ev, Ec, Eg, dem_pax, M + r"\4_trip_assignment\assigned_road_pax.gpkg", "assigned_road_pax")

    # ---- FREIGHT road total (truck + access/egress of rail/sea freight) ----
    dem_frg = defaultdict(lambda: defaultdict(float))
    o = od[('frg', 'truck')]
    for i in range(Z):
        for j in range(Z):
            if o[i][j] > 0: dem_frg[cnode[i]][cnode[j]] += o[i][j]*2.0
    add_access(dem_frg, od[('frg', 'rail')], tn['rail'], 2.0)
    add_access(dem_frg, od[('frg', 'water')], tn['sea'], 2.0)
    assign_pairs(nxy, Eu, Ev, Ec, Eg, dem_frg, M + r"\4_trip_assignment\assigned_road_frg.gpkg", "assigned_road_frg")

    # ---- access/egress only (เฉพาะช่วงเข้า-ออก terminal ทุกโหมด) ----
    dem_ae = defaultdict(lambda: defaultdict(float))
    for m in ('rail', 'air', 'water'): add_access(dem_ae, od[('pax', m)], tn[m], 1.0)
    add_access(dem_ae, od[('frg', 'rail')], tn['rail'], 2.0)
    add_access(dem_ae, od[('frg', 'water')], tn['sea'], 2.0)
    assign_pairs(nxy, Eu, Ev, Ec, Eg, dem_ae, M + r"\4_trip_assignment\assigned_access_egress.gpkg", "assigned_access_egress")
    app.exitQgis(); log("DONE")

try: main()
except Exception: log("ERR", traceback.format_exc())
