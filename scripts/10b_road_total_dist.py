# -*- coding: utf-8 -*-
"""ขั้น 10b: จราจรถนน "รวม" ระดับอำเภอ (928) = door-to-door road + access/egress
mode split ใช้สัดส่วนรวมจากโมเดลจังหวัด (pax road PCU/trip=1.072 ; frg=1.236 ;
access: pax rail 2.8%/water 0.3% ; frg rail 35.6%/water 2.6%)
OD cost+gravity ระดับอำเภอ (beta 0.045/0.030). scipy. รันผ่าน qpy.bat (bg) ; log output/_10b.log
out: model/4_trip_assignment/assigned_road_total_dist.gpkg
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

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit
B = _ROOT; M = B + r"\model"
LOG = open(B + r"\output\_10b.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
PAX_ROAD_PCU, FRG_ROAD_PCU = 1.072, 1.236
PAX_RAIL_SH, PAX_WATER_SH = 0.028, 0.003
FRG_RAIL_SH, FRG_WATER_SH = 0.356, 0.026
BETA_PAX, BETA_FRG = 0.045, 0.030

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

def nearest(nxy, x, y):
    dx = nxy[:, 0]-x; dy = nxy[:, 1]-y; return int(np.argmin(dx*dx+dy*dy))

def nearest_pt(arr, x, y):
    dx = arr[:, 0]-x; dy = arr[:, 1]-y; return int(np.argmin(dx*dx+dy*dy))

def term_road_nodes(nxy, term_gpkg, term_ln, cpts):
    """ต่ออำเภอ -> terminal ใกล้สุด -> road node ของ terminal นั้น"""
    t = processing.run("native:reprojectlayer", {'INPUT': QgsVectorLayer(B + "\\" + term_gpkg + "|layername=" + term_ln, "t", "ogr"),
        'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']
    tp = np.array([[f.geometry().asPoint().x(), f.geometry().asPoint().y()] for f in t.getFeatures()])
    out = []
    for (x, y) in cpts:
        k = nearest_pt(tp, x, y); out.append(nearest(nxy, tp[k][0], tp[k][1]))
    return out

def main():
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()
    nxy, Eu, Ev, Ec, Eg = build_noded(QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "r", "ogr"))
    nN = len(nxy); nE = len(Eu); log("road nodes=%d edges=%d" % (nN, nE))
    edge_of = {}
    for e in range(nE):
        for a, b in ((Eu[e], Ev[e]), (Ev[e], Eu[e])):
            pe = edge_of.get((a, b))
            if pe is None or Ec[e] < Ec[pe]: edge_of[(a, b)] = e
    rows = np.concatenate([Eu, Ev]); cols = np.concatenate([Ev, Eu]); data = np.concatenate([Ec, Ec])
    csr = csr_matrix((data, (rows, cols)), shape=(nN, nN))

    cen = QgsVectorLayer(B + r"\data\zones_taz\district_centroids.gpkg|layername=district_centroids", "c", "ogr")
    dc = sorted([(f['district_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    dids = [d[0] for d in dc]; Z = len(dids); didx = {d: i for i, d in enumerate(dids)}
    cpts = [(p.x(), p.y()) for _, p in dc]
    cnode = [nearest(nxy, x, y) for (x, y) in cpts]
    log("districts=%d" % Z)
    rail_n = term_road_nodes(nxy, r"inputs\multimodal\rail_stations.gpkg", "rail_stations", cpts)
    port_n = term_road_nodes(nxy, r"inputs\multimodal\ports.gpkg", "ports", cpts)
    sea_n = term_road_nodes(nxy, r"data\multimodal\seaport_nodes.gpkg", "seaport_nodes", cpts)

    # OD cost (free-flow) batched
    cost = np.full((Z, Z), np.inf); tn = np.array(cnode); BATCH = 150
    for s0 in range(0, Z, BATCH):
        dmat = dijkstra(csr, directed=False, indices=tn[s0:s0+BATCH])
        cost[s0:s0+BATCH, :] = dmat[:, tn]
    log("OD cost finite=%.3f" % np.isfinite(cost).mean())
    cc = cost.copy()
    for i in range(Z):
        row = cc[i].copy(); row[i] = np.inf; nn = np.nanmin(np.where(np.isfinite(row), row, np.inf))
        cc[i, i] = 0.5*nn if np.isfinite(nn) else 15.0

    # tripgen + gravity
    P = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}; A = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}
    for r in csv.DictReader(open(M + r"\1_trip_generation\district_tripgen.csv", encoding="utf-8")):
        i = didx[int(r['district_id'])]; P['pax'][i] = float(r['P_pax']); A['pax'][i] = float(r['A_pax']); P['frg'][i] = float(r['P_frg']); A['frg'][i] = float(r['A_frg'])
    def grav(Pv, Av, beta):
        f = np.where(np.isfinite(cc), np.exp(-beta*np.where(np.isfinite(cc), cc, 0)), 0.0)
        Av2 = Av*(Pv.sum()/max(Av.sum(), 1)); a = np.ones(Z); b = np.ones(Z)
        for _ in range(120):
            a = 1.0/np.maximum((f*(b*Av2)).sum(1), 1e-9); b = 1.0/np.maximum((f.T*(a*Pv)).sum(1), 1e-9)
        return (a[:, None]*Pv[:, None])*(b[None, :]*Av2[None, :])*f
    T_pax = grav(P['pax'], A['pax'], BETA_PAX); T_frg = grav(P['frg'], A['frg'], BETA_FRG)
    log("gravity done pax=%.0f frg=%.0f" % (T_pax.sum(), T_frg.sum()))

    # demand
    dem = defaultdict(lambda: defaultdict(float))
    # door-to-door road
    for i in range(Z):
        ci = cnode[i]
        row = T_pax[i]*PAX_ROAD_PCU + T_frg[i]*FRG_ROAD_PCU
        for j in range(Z):
            if row[j] > 0: dem[ci][cnode[j]] += row[j]
    # access/egress (out=rowsum, in=colsum)
    pax_out = T_pax.sum(1); pax_in = T_pax.sum(0); frg_out = T_frg.sum(1); frg_in = T_frg.sum(0)
    for i in range(Z):
        ci = cnode[i]
        # pax rail
        dem[ci][rail_n[i]] += pax_out[i]*PAX_RAIL_SH*1.0; dem[rail_n[i]][ci] += pax_in[i]*PAX_RAIL_SH*1.0
        dem[ci][port_n[i]] += pax_out[i]*PAX_WATER_SH*1.0; dem[port_n[i]][ci] += pax_in[i]*PAX_WATER_SH*1.0
        # frg rail/sea (truck)
        dem[ci][rail_n[i]] += frg_out[i]*FRG_RAIL_SH*2.0; dem[rail_n[i]][ci] += frg_in[i]*FRG_RAIL_SH*2.0
        dem[ci][sea_n[i]] += frg_out[i]*FRG_WATER_SH*2.0; dem[sea_n[i]][ci] += frg_in[i]*FRG_WATER_SH*2.0

    # assign
    flow = np.zeros(nE); origins = sorted(dem.keys())
    for s0 in range(0, len(origins), BATCH):
        srcs = origins[s0:s0+BATCH]
        dmat, pred = dijkstra(csr, directed=False, indices=srcs, return_predecessors=True)
        for bi, on in enumerate(srcs):
            ds = dmat[bi]; ps = pred[bi]; acc = np.zeros(nN)
            for dn, v in dem[on].items(): acc[dn] += v
            if acc.sum() <= 0: continue
            for node in np.argsort(ds)[::-1]:
                if not np.isfinite(ds[node]): continue
                p = ps[node]
                if p < 0: continue
                e = edge_of.get((p, node))
                if e is not None: flow[e] += acc[node]; acc[p] += acc[node]
        log("  assigned origins up to %d/%d" % (min(s0+BATCH, len(origins)), len(origins)))

    lyr = QgsVectorLayer("LineString?crs=EPSG:32647", "assigned_road_total_dist", "memory"); dp = lyr.dataProvider()
    dp.addAttributes([QgsField('vol_pcu', QVariant.Double)]); lyr.updateFields()
    fl = []
    for e in range(nE):
        if flow[e] <= 0: continue
        ft = QgsFeature(lyr.fields()); ft.setGeometry(Eg[e]); ft.setAttributes([round(float(flow[e]), 1)]); fl.append(ft)
    dp.addFeatures(fl)
    out = M + r"\4_trip_assignment\assigned_road_total_dist.gpkg"
    if os.path.exists(out): os.remove(out)
    o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = "assigned_road_total_dist"
    QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out, QgsCoordinateTransformContext(), o)
    log("assigned_road_total_dist: %d links max=%.0f total=%.0f" % (len(fl), flow.max(), flow.sum()))
    log("DONE"); hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์

try: main()
except Exception: log("ERR", traceback.format_exc()); raise
