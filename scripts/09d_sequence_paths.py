# -*- coding: utf-8 -*-
"""ขั้น 9d: assignment เป็น sequence path ต่อโหมด/สาย (ครบทุกกรณี)
แต่ละทริปข้ามโหมด = เส้นทางต่อเนื่อง: access(ถนน) -> line-haul(โหมด) -> egress(ถนน)
รวมในเลเยอร์เดียวต่อกรณี มี field leg: 'access','linehaul','egress' (รวม access+egress = 'road')
cases: rail-pax, rail-frg, air-pax, water-pax, sea-frg
out: model/4_trip_assignment/seq_<case>.gpkg ; รันผ่าน qpy.bat (bg) ; log -> output/_sq.log
"""
import os, csv, traceback, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
import processing
from processing.core.Processing import Processing
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext, QgsCoordinateReferenceSystem)
from qgis.PyQt.QtCore import QVariant

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"; M = B + r"\model"
LOG = open(B + r"\output\_sq.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def to32647(l):
    return processing.run("native:reprojectlayer", {'INPUT': l, 'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']

def build_noded(layer, costmode, costfield=None):
    feats = []; vcount = defaultdict(int)
    for f in layer.getFeatures():
        g = f.geometry(); pl = g.asPolyline() if not g.isMultipart() else [p for pr in g.asMultiPolyline() for p in pr]
        if len(pl) < 2: continue
        rv = [(round(p.x(), 1), round(p.y(), 1)) for p in pl]
        c = f[costfield] if costmode == 'field' else (f['speed_kmh'] or 40.0)
        feats.append((rv, pl, c))
        for k in rv: vcount[k] += 1
    nodeset = set()
    for rv, _, _ in feats: nodeset.add(rv[0]); nodeset.add(rv[-1])
    for k, c in vcount.items():
        if c >= 2: nodeset.add(k)
    nid = {}; nxy = []; Eu = []; Ev = []; Ec = []; Eg = []
    for rv, pl, c in feats:
        idxs = [i for i, k in enumerate(rv) if k in nodeset]
        for a, b in zip(idxs[:-1], idxs[1:]):
            ka, kb = rv[a], rv[b]
            if ka == kb: continue
            for k, p in ((ka, pl[a]), (kb, pl[b])):
                if k not in nid: nid[k] = len(nxy); nxy.append((p.x(), p.y()))
            sub = pl[a:b+1]; gs = QgsGeometry.fromPolylineXY(sub)
            cost = float(c) if costmode == 'field' else (gs.length()/1000.0)/max(float(c), 3)*60.0
            Eu.append(nid[ka]); Ev.append(nid[kb]); Ec.append(cost); Eg.append(gs)
    return np.array(nxy), np.array(Eu), np.array(Ev), np.array(Ec), Eg

def nearest(nxy, p):
    dx = nxy[:, 0]-p.x(); dy = nxy[:, 1]-p.y(); return int(np.argmin(dx*dx+dy*dy))

def assign_pairs(nxy, Eu, Ev, Ec, demand):
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
    return flow

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

def main():
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()
    # graphs
    RN = build_noded(QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "r", "ogr"), 'time')
    log("road graph nodes=%d" % len(RN[0]))
    RAIL = build_noded(QgsVectorLayer(B + r"\data\network\rail_clean.gpkg|layername=rail_clean", "rl", "ogr"), 'time')
    WAT = build_noded(QgsVectorLayer(B + r"\data\network\water_clean.gpkg|layername=water_clean", "w", "ogr"), 'time')
    AIR = build_noded(to32647(QgsVectorLayer(B + r"\data\multimodal\air_links.gpkg|layername=air_links", "al", "ogr")), 'field', 'fly_min')
    SEA = build_noded(to32647(QgsVectorLayer(B + r"\data\multimodal\water_freight_links.gpkg|layername=water_freight_links", "s", "ogr")), 'field', 'sail_min')

    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zc = sorted([(f['zone_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    zids = [z[0] for z in zc]; Z = len(zids); zidx = {z: i for i, z in enumerate(zids)}
    cnode = [nearest(RN[0], p) for _, p in zc]

    # cases: (name, stream_csv, mode, mode_graph, access_gpkg, access_ln, pcu)
    cases = [
        ("seq_rail_pax", "mode_split_passenger.csv", "rail",  RAIL, r"data\zones_taz\access_rail.gpkg", "access_rail", 1.0),
        ("seq_rail_frg", "mode_split_freight.csv",   "rail",  RAIL, r"data\zones_taz\access_rail.gpkg", "access_rail", 2.0),
        ("seq_air_pax",  "mode_split_passenger.csv", "air",   AIR,  r"data\zones_taz\access_air.gpkg", "access_air", 1.0),
        ("seq_water_pax","mode_split_passenger.csv", "water", WAT,  r"data\zones_taz\access_water.gpkg", "access_water", 1.0),
        ("seq_sea_frg",  "mode_split_freight.csv",   "water", SEA,  r"data\zones_taz\access_seafreight.gpkg", "access_seafreight", 2.0),
    ]
    for name, csvf, mode, MG, agpkg, aln, pcu in cases:
        od = read_od(csvf, mode, zidx, Z)
        if od.sum() <= 0:
            log("%s: no demand, skip" % name); continue
        ep = endpoints(agpkg, aln)
        term_road = [nearest(RN[0], ep[z]) for z in zids]
        term_mode = [nearest(MG[0], ep[z]) for z in zids]
        out_i = od.sum(1); in_i = od.sum(0)
        # access/egress on ROAD (pcu)
        dem_road = defaultdict(lambda: defaultdict(float))
        for i in range(Z):
            if out_i[i] > 0: dem_road[cnode[i]][term_road[i]] += out_i[i]*pcu
            if in_i[i] > 0: dem_road[term_road[i]][cnode[i]] += in_i[i]*pcu
        froad = assign_pairs(RN[0], RN[1], RN[2], RN[3], dem_road)
        # line-haul on MODE (trips)
        dem_mode = defaultdict(lambda: defaultdict(float))
        for i in range(Z):
            for j in range(Z):
                if od[i][j] > 0: dem_mode[term_mode[i]][term_mode[j]] += od[i][j]
        fmode = assign_pairs(MG[0], MG[1], MG[2], MG[3], dem_mode)
        # write merged sequence layer
        lyr = QgsVectorLayer("LineString?crs=EPSG:32647", name, "memory"); dp = lyr.dataProvider()
        dp.addAttributes([QgsField('leg', QVariant.String), QgsField('vol', QVariant.Double)]); lyr.updateFields()
        fl = []
        for e in range(len(RN[1])):
            if froad[e] > 0:
                ft = QgsFeature(lyr.fields()); ft.setGeometry(RN[4][e]); ft.setAttributes(['road', round(float(froad[e]), 1)]); fl.append(ft)
        for e in range(len(MG[1])):
            if fmode[e] > 0:
                ft = QgsFeature(lyr.fields()); ft.setGeometry(MG[4][e]); ft.setAttributes(['linehaul', round(float(fmode[e]), 1)]); fl.append(ft)
        dp.addFeatures(fl)
        out = M + r"\4_trip_assignment\\" + name + ".gpkg"
        if os.path.exists(out): os.remove(out)
        o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = name
        QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out, QgsCoordinateTransformContext(), o)
        log("%s: road links=%d (max %.0f) linehaul links=%d (max %.0f)" % (
            name, int((froad > 0).sum()), froad.max(), int((fmode > 0).sum()), fmode.max()))
    app.exitQgis(); log("DONE")

try: main()
except Exception: log("ERR", traceback.format_exc())
