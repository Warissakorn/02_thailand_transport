# -*- coding: utf-8 -*-
"""ขั้น 12: flow components ระดับอำเภอ แยกโหมด × สาย (คน/สินค้า)
d2d-คน, d2d-สินค้า, ราง-คน, ราง-สินค้า, น้ำ-คน, น้ำ-สินค้า  (อากาศ≈0 ข้าม)
ใช้สัดส่วนโหมดรวม (เหมือน 10b) ; ตรวจสอบ sum = assigned_road_total_dist
out: model/4_trip_assignment/flowd_*.gpkg ; log output/_12.log ; รันผ่าน qpy.bat (bg)
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
LOG = open(B + r"\output\_12.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
PAX_RPCU, FRG_RPCU = 1.072, 1.236
PAX_RAIL, PAX_WAT = 0.028, 0.003
FRG_RAIL, FRG_WAT = 0.356, 0.026
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

def nrst(nxy, x, y):
    dx = nxy[:, 0]-x; dy = nxy[:, 1]-y; return int(np.argmin(dx*dx+dy*dy))

def term_road(nxy, gpkg, ln, cpts):
    t = processing.run("native:reprojectlayer", {'INPUT': QgsVectorLayer(B + "\\" + gpkg + "|layername=" + ln, "t", "ogr"),
        'TARGET_CRS': QgsCoordinateReferenceSystem('EPSG:32647'), 'OUTPUT': 'memory:'})['OUTPUT']
    tp = np.array([[f.geometry().asPoint().x(), f.geometry().asPoint().y()] for f in t.getFeatures()])
    out = []
    for (x, y) in cpts:
        d = (tp[:, 0]-x)**2+(tp[:, 1]-y)**2; k = int(np.argmin(d)); out.append(nrst(nxy, tp[k][0], tp[k][1]))
    return out

def main():
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()
    nxy, Eu, Ev, Ec, Eg = build_noded(QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "r", "ogr"))
    nN = len(nxy); nE = len(Eu)
    edge_of = {}
    for e in range(nE):
        for a, b in ((Eu[e], Ev[e]), (Ev[e], Eu[e])):
            pe = edge_of.get((a, b))
            if pe is None or Ec[e] < Ec[pe]: edge_of[(a, b)] = e
    rows = np.concatenate([Eu, Ev]); cols = np.concatenate([Ev, Eu]); data = np.concatenate([Ec, Ec])
    csr = csr_matrix((data, (rows, cols)), shape=(nN, nN))
    log("road nodes=%d" % nN)

    cen = QgsVectorLayer(B + r"\data\zones_taz\district_centroids.gpkg|layername=district_centroids", "c", "ogr")
    dc = sorted([(f['district_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    dids = [d[0] for d in dc]; Z = len(dids); didx = {d: i for i, d in enumerate(dids)}
    cpts = [(p.x(), p.y()) for _, p in dc]; cnode = [nrst(nxy, x, y) for (x, y) in cpts]
    rail_n = term_road(nxy, r"data\multimodal\rail_stations.gpkg", "rail_stations", cpts)
    port_n = term_road(nxy, r"data\multimodal\ports.gpkg", "ports", cpts)
    sea_n = term_road(nxy, r"data\multimodal\seaport_nodes.gpkg", "seaport_nodes", cpts)

    tn = np.array(cnode); cost = np.full((Z, Z), np.inf); BATCH = 150
    for s0 in range(0, Z, BATCH):
        cost[s0:s0+BATCH, :] = dijkstra(csr, directed=False, indices=tn[s0:s0+BATCH])[:, tn]
    cc = cost.copy()
    for i in range(Z):
        row = cc[i].copy(); row[i] = np.inf; nn = np.nanmin(np.where(np.isfinite(row), row, np.inf)); cc[i, i] = 0.5*nn if np.isfinite(nn) else 15.0
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
    log("gravity pax=%.0f frg=%.0f" % (T_pax.sum(), T_frg.sum()))

    def assign(dem):
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
        return flow

    def d2d(T, pcu):
        dem = defaultdict(lambda: defaultdict(float))
        for i in range(Z):
            row = T[i]*pcu; ci = cnode[i]
            for j in range(Z):
                if row[j] > 0: dem[ci][cnode[j]] += row[j]
        return dem
    def ae(T, tnodes, sh, pcu):
        dem = defaultdict(lambda: defaultdict(float)); oi = T.sum(1)*sh*pcu; ii = T.sum(0)*sh*pcu
        for i in range(Z):
            if oi[i] > 0: dem[cnode[i]][tnodes[i]] += oi[i]
            if ii[i] > 0: dem[tnodes[i]][cnode[i]] += ii[i]
        return dem

    comps = [
        ("flowd_d2d_pax", d2d(T_pax, PAX_RPCU)),
        ("flowd_d2d_frg", d2d(T_frg, FRG_RPCU)),
        ("flowd_ae_rail_pax", ae(T_pax, rail_n, PAX_RAIL, 1.0)),
        ("flowd_ae_rail_frg", ae(T_frg, rail_n, FRG_RAIL, 2.0)),
        ("flowd_ae_water_pax", ae(T_pax, port_n, PAX_WAT, 1.0)),
        ("flowd_ae_water_frg", ae(T_frg, sea_n, FRG_WAT, 2.0)),
    ]
    total = np.zeros(nE)
    for name, dem in comps:
        fl = assign(dem); total += fl
        lyr = QgsVectorLayer("LineString?crs=EPSG:32647", name, "memory"); dp = lyr.dataProvider()
        dp.addAttributes([QgsField('vol_pcu', QVariant.Double)]); lyr.updateFields()
        fs = []
        for e in range(nE):
            if fl[e] <= 0: continue
            ft = QgsFeature(lyr.fields()); ft.setGeometry(Eg[e]); ft.setAttributes([round(float(fl[e]), 1)]); fs.append(ft)
        dp.addFeatures(fs)
        out = M + r"\4_trip_assignment\\" + name + ".gpkg"
        if os.path.exists(out): os.remove(out)
        o = QgsVectorFileWriter.SaveVectorOptions(); o.driverName = "GPKG"; o.layerName = name
        QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out, QgsCoordinateTransformContext(), o)
        log("%s: links=%d max=%.0f total=%.0f" % (name, len(fs), fl.max(), fl.sum()))
    tot = QgsVectorLayer(M + r"\4_trip_assignment\assigned_road_total_dist.gpkg|layername=assigned_road_total_dist", "t", "ogr")
    grand = sum(f['vol_pcu'] for f in tot.getFeatures())
    log("VERIFY: sum components=%.0f | total_dist=%.0f | diff=%.4f%%" % (total.sum(), grand, 100*abs(total.sum()-grand)/grand))
    app.exitQgis(); log("DONE")

try: main()
except Exception: log("ERR", traceback.format_exc())
