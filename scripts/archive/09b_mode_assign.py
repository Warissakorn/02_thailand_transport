# -*- coding: utf-8 -*-
"""ขั้น 9b: assignment แยกตามโหมด+สาย — assign OD แต่ละโหมดลงโครงข่ายของมันเอง
- road_pax (PCU), road_frg (PCU)  -> network_clean
- rail (vol_pax, vol_frg trips)    -> rail_clean
- water (pax trips)                -> water_clean (ferry)
- seafreight (frg trips)           -> water_freight_links
- air (pax trips)                  -> air_links
ใช้ proper noding + scipy. รันผ่าน qpy.bat (background) ; log -> output/_ma.log
out: model/4_trip_assignment/assigned_<mode>.gpkg
"""
import os, csv, traceback, numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject)
from qgis.PyQt.QtCore import QVariant
import processing
from processing.core.Processing import Processing

def to32647(layer):
    return processing.run("native:reprojectlayer", {'INPUT': layer, 'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT
B = _ROOT; M = B + r"\model"
LOG = open(B + r"\output\_ma.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def build_noded(layer, costmode, costfield=None):
    """costmode='time' (speed_kmh) | 'field' (costfield ต่อ feature, ใช้กับ 2-point links)"""
    feats = []; vcount = defaultdict(int)
    for f in layer.getFeatures():
        g = f.geometry(); pl = g.asPolyline() if not g.isMultipart() else [p for pr in g.asMultiPolyline() for p in pr]
        if len(pl) < 2: continue
        rv = [(round(p.x(), 1), round(p.y(), 1)) for p in pl]
        c = (f[costfield] if costmode == 'field' else (f['speed_kmh'] or 40.0))
        feats.append((rv, pl, c));
        for k in rv: vcount[k] += 1
    nodeset = set()
    for rv, _, _ in feats: nodeset.add(rv[0]); nodeset.add(rv[-1])
    for k, c in vcount.items():
        if c >= 2: nodeset.add(k)
    node_id = {}; nxy = []; Eu = []; Ev = []; Ec = []; Eg = []
    for rv, pl, c in feats:
        idxs = [i for i, k in enumerate(rv) if k in nodeset]
        for a, b in zip(idxs[:-1], idxs[1:]):
            ka, kb = rv[a], rv[b]
            if ka == kb: continue
            for k, p in ((ka, pl[a]), (kb, pl[b])):
                if k not in node_id: node_id[k] = len(nxy); nxy.append((p.x(), p.y()))
            sub = pl[a:b+1]; gsub = QgsGeometry.fromPolylineXY(sub)
            cost = float(c) if costmode == 'field' else (gsub.length()/1000.0)/max(float(c), 3)*60.0
            Eu.append(node_id[ka]); Ev.append(node_id[kb]); Ec.append(cost); Eg.append(gsub)
    return np.array(nxy), np.array(Eu), np.array(Ev), np.array(Ec), Eg

def tie(nxy, points):
    out = []
    for p in points:
        dx = nxy[:, 0]-p.x(); dy = nxy[:, 1]-p.y(); out.append(int(np.argmin(dx*dx+dy*dy)))
    return np.array(out)

def assign(nxy, Eu, Ev, Ec, Eg, tnode, od, fields_vals, out, name):
    nN = len(nxy); nE = len(Eu)
    edge_of = {}
    for e in range(nE):
        for a, b in ((Eu[e], Ev[e]), (Ev[e], Eu[e])):
            pe = edge_of.get((a, b))
            if pe is None or Ec[e] < Ec[pe]: edge_of[(a, b)] = e
    rows = np.concatenate([Eu, Ev]); cols = np.concatenate([Ev, Eu]); data = np.concatenate([Ec, Ec])
    csr = csr_matrix((data, (rows, cols)), shape=(nN, nN))
    Z = od.shape[0]
    fns = list(fields_vals.keys()); field_ods = list(fields_vals.values())
    flows = [np.zeros(nE) for _ in fns]  # one flow array per field (e.g. pax, frg)
    BATCH = 120
    for s0 in range(0, Z, BATCH):
        srcs = tnode[s0:s0+BATCH]
        dmat, pred = dijkstra(csr, directed=False, indices=srcs, return_predecessors=True)
        for bi, si in enumerate(range(s0, min(s0+BATCH, Z))):
            dist_s = dmat[bi]; pred_s = pred[bi]
            order = np.argsort(dist_s)
            for fi, odm in enumerate(field_ods):
                acc = np.zeros(nN); np.add.at(acc, tnode, odm[si])
                if acc.sum() <= 0: continue
                for node in order[::-1]:
                    if not np.isfinite(dist_s[node]): continue
                    p = pred_s[node]
                    if p < 0: continue
                    e = edge_of.get((p, node))
                    if e is not None: flows[fi][e] += acc[node]; acc[p] += acc[node]
    lyr = QgsVectorLayer("LineString?crs=EPSG:32647", name, "memory"); dp = lyr.dataProvider()
    dp.addAttributes([QgsField(n, QVariant.Double) for n in fns]); lyr.updateFields()
    fl = []
    for e in range(nE):
        tot = sum(flows[i][e] for i in range(len(fns)))
        if tot <= 0: continue
        ft = QgsFeature(lyr.fields()); ft.setGeometry(Eg[e]); ft.setAttributes([round(float(flows[i][e]), 1) for i in range(len(fns))]); fl.append(ft)
    dp.addFeatures(fl)
    if os.path.exists(out): os.remove(out)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = name
    QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out, QgsCoordinateTransformContext(), o)
    log("%s: %d links | totals %s" % (name, len(fl), {n: round(flows[i].max()) for i, n in enumerate(fns)}))

def od_from_modesplit(csvf, modes_pcu, zidx, Z):
    """อ่าน mode_split -> OD matrix (รวม modes ตาม PCU/weight ที่กำหนด)"""
    od = np.zeros((Z, Z))
    for r in csv.DictReader(open(M + r"\3_mode_choice\\" + csvf, encoding="utf-8")):
        m = r['mode']
        if m in modes_pcu:
            i = zidx.get(int(r['orig_zone'])); j = zidx.get(int(r['dest_zone']))
            if i is not None and j is not None: od[i][j] += float(r['trips'])*modes_pcu[m]
    return od

def endpoints(gpkg, ln):
    l = QgsVectorLayer(B + "\\" + gpkg + "|layername=" + ln, "a", "ogr")
    d = {}
    for f in l.getFeatures():
        pl = f.geometry().asPolyline(); d[f['zone_id']] = QgsPointXY(pl[-1])
    return d

def main():
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()
    cen = QgsVectorLayer(B + r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw", "c", "ogr")
    zc = sorted([(f['zone_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    zids = [z[0] for z in zc]; Z = len(zids); zidx = {z: i for i, z in enumerate(zids)}
    cpt = [z[1] for z in zc]

    # ---- ROAD (pax / frg) ----
    road = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "r", "ogr")
    nxy, Eu, Ev, Ec, Eg = build_noded(road, 'time')
    tn = tie(nxy, cpt)
    od_rp = od_from_modesplit("mode_split_passenger.csv", {'car': 1.0, 'motorcycle': 0.33, 'bus': 2.5}, zidx, Z)
    od_rf = od_from_modesplit("mode_split_freight.csv", {'truck': 2.0}, zidx, Z)
    assign(nxy, Eu, Ev, Ec, Eg, tn, od_rp, {'vol_pcu': od_rp}, M + r"\4_trip_assignment\assigned_road_pax.gpkg", "assigned_road_pax")
    assign(nxy, Eu, Ev, Ec, Eg, tn, od_rf, {'vol_pcu': od_rf}, M + r"\4_trip_assignment\assigned_road_frg.gpkg", "assigned_road_frg")

    # ---- RAIL (pax + frg) ----
    rail = QgsVectorLayer(B + r"\data\network\rail_clean.gpkg|layername=rail_clean", "rl", "ogr")
    nxy, Eu, Ev, Ec, Eg = build_noded(rail, 'time')
    ep = endpoints(r"data\zones_taz\access_rail.gpkg", "access_rail"); tn = tie(nxy, [ep[z] for z in zids])
    od_rail_p = od_from_modesplit("mode_split_passenger.csv", {'rail': 1.0}, zidx, Z)
    od_rail_f = od_from_modesplit("mode_split_freight.csv", {'rail': 1.0}, zidx, Z)
    assign(nxy, Eu, Ev, Ec, Eg, tn, od_rail_p, {'vol_pax': od_rail_p, 'vol_frg': od_rail_f}, M + r"\4_trip_assignment\assigned_rail.gpkg", "assigned_rail")

    # ---- WATER ferry (pax) ----
    wat = QgsVectorLayer(B + r"\data\network\water_clean.gpkg|layername=water_clean", "w", "ogr")
    nxy, Eu, Ev, Ec, Eg = build_noded(wat, 'time')
    ep = endpoints(r"data\zones_taz\access_water.gpkg", "access_water"); tn = tie(nxy, [ep[z] for z in zids])
    od_wp = od_from_modesplit("mode_split_passenger.csv", {'water': 1.0}, zidx, Z)
    assign(nxy, Eu, Ev, Ec, Eg, tn, od_wp, {'vol_pax': od_wp}, M + r"\4_trip_assignment\assigned_water.gpkg", "assigned_water")

    # ---- SEAFREIGHT (frg) ----
    sea = to32647(QgsVectorLayer(B + r"\data\multimodal\water_freight_links.gpkg|layername=water_freight_links", "s", "ogr"))
    nxy, Eu, Ev, Ec, Eg = build_noded(sea, 'field', 'sail_min')
    ep = endpoints(r"data\zones_taz\access_seafreight.gpkg", "access_seafreight"); tn = tie(nxy, [ep[z] for z in zids])
    od_sf = od_from_modesplit("mode_split_freight.csv", {'water': 1.0}, zidx, Z)
    assign(nxy, Eu, Ev, Ec, Eg, tn, od_sf, {'vol_frg': od_sf}, M + r"\4_trip_assignment\assigned_seafreight.gpkg", "assigned_seafreight")

    # ---- AIR (pax) ----
    al = to32647(QgsVectorLayer(B + r"\data\multimodal\air_links.gpkg|layername=air_links", "al", "ogr"))
    nxy, Eu, Ev, Ec, Eg = build_noded(al, 'field', 'fly_min')
    # tie: province -> airport (iata) node coords
    an = QgsVectorLayer(B + r"\data\multimodal\air_nodes.gpkg|layername=air_nodes", "an", "ogr")
    ct = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'), QgsCoordinateReferenceSystem('EPSG:32647'), QgsProject.instance())
    iata_pt = {f['iata']: ct.transform(f.geometry().asPoint()) for f in an.getFeatures()}
    acc_air = QgsVectorLayer(B + r"\data\zones_taz\access_air.gpkg|layername=access_air", "aa", "ogr")
    z_iata = {f['zone_id']: f['terminal'] for f in acc_air.getFeatures()}
    tn = tie(nxy, [iata_pt.get(z_iata[z], cpt[zidx[z]]) for z in zids])
    od_air = od_from_modesplit("mode_split_passenger.csv", {'air': 1.0}, zidx, Z)
    assign(nxy, Eu, Ev, Ec, Eg, tn, od_air, {'vol_pax': od_air}, M + r"\4_trip_assignment\assigned_air.gpkg", "assigned_air")
    app.exitQgis(); log("DONE")

try: main()
except Exception: log("ERR", traceback.format_exc())
