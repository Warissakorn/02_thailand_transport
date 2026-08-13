# -*- coding: utf-8 -*-
"""ขั้น B-2: OD cost + gravity + assignment ระดับอำเภอ (928 โซน) ด้วย scipy
OD cost: scipy dijkstra (free-flow) ; gravity: numpy Furness ; assignment: AON (subtree-sum)
road PCU = pax*1.049 + freight*1.24 (สัดส่วนโหมดถนน+PCU จากโมเดลจังหวัด)
out: model/4_trip_assignment/assigned_district.gpkg ; model/2_trip_distribution/od_cost_district.csv
รันผ่าน qpy.bat (background) ; log -> output/_d8b.log
"""
import os, sys, csv, traceback, numpy as np
# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT
sys.path.insert(0, (_ROOT + r"\config"))
import model_params as mp
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant

B = _ROOT; M = B + r"\model"
LOG = open(B + r"\output\_d8b.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
FAC_PAX, FAC_FRG = 1.049, 1.24   # trip -> road PCU (จากสัดส่วนโหมด+PCU จังหวัด)

def main():
    app = QgsApplication([], False); app.initQgis()
    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    # ---- proper noding: split features at intersection vertices (T-junctions) ----
    from collections import defaultdict
    feats = []; vcount = defaultdict(int)
    for f in net.getFeatures():
        g = f.geometry(); pl = g.asPolyline() if not g.isMultipart() else [p for pr in g.asMultiPolyline() for p in pr]
        if len(pl) < 2: continue
        rv = [(round(p.x()), round(p.y())) for p in pl]
        try: ln = int(str(f['lanes']).split(';')[0])
        except: ln = 2
        feats.append((rv, pl, f['speed_kmh'] or 40.0, (f['capacity'] or 800)*max(ln, 1)*16.0))
        for k in rv: vcount[k] += 1
    # node = endpoint of a feature OR vertex shared by >=2 features
    nodeset = set()
    for rv, _, _, _ in feats:
        nodeset.add(rv[0]); nodeset.add(rv[-1])
    for k, c in vcount.items():
        if c >= 2: nodeset.add(k)
    node_id = {}; nxy = []
    Eu = []; Ev = []; Et0 = []; Ecap = []; Egeom = []
    for rv, pl, spd, cap in feats:
        idxs = [i for i, k in enumerate(rv) if k in nodeset]
        for a, b in zip(idxs[:-1], idxs[1:]):
            ka, kb = rv[a], rv[b]
            if ka == kb: continue
            for k, p in ((ka, pl[a]), (kb, pl[b])):
                if k not in node_id: node_id[k] = len(nxy); nxy.append((p.x(), p.y()))
            sub = pl[a:b+1]; gsub = QgsGeometry.fromPolylineXY(sub)
            Eu.append(node_id[ka]); Ev.append(node_id[kb]); Et0.append((gsub.length()/1000.0)/max(spd, 5)*60.0)
            Ecap.append(cap); Egeom.append(gsub)
    nN = len(nxy); nE = len(Eu)
    Eu = np.array(Eu); Ev = np.array(Ev); Et0 = np.array(Et0); Ecap = np.array(Ecap)
    log("graph nodes=%d edges=%d" % (nN, nE))

    # CSR (undirected) — เก็บ edge index ของแต่ละ node-pair (min t0)
    rows = np.concatenate([Eu, Ev]); cols = np.concatenate([Ev, Eu]); data = np.concatenate([Et0, Et0])
    edge_of = {}
    for e in range(nE):
        for a, b in ((Eu[e], Ev[e]), (Ev[e], Eu[e])):
            pe = edge_of.get((a, b))
            if pe is None or Et0[e] < Et0[pe]: edge_of[(a, b)] = e
    csr = csr_matrix((data, (rows, cols)), shape=(nN, nN))

    # tie district centroids -> nearest node
    cen = QgsVectorLayer(B + r"\data\zones_taz\district_centroids.gpkg|layername=district_centroids", "c", "ogr")
    dc = sorted([(f['district_id'], f.geometry().asPoint()) for f in cen.getFeatures()])
    dids = [d[0] for d in dc]; nxy_a = np.array(nxy)
    tnode = []
    for did, p in dc:
        dx = nxy_a[:, 0]-p.x(); dy = nxy_a[:, 1]-p.y(); tnode.append(int(np.argmin(dx*dx+dy*dy)))
    tnode = np.array(tnode); Z = len(dids); zpos = {d: i for i, d in enumerate(dids)}
    log("districts tied:", Z)

    # OD cost (free-flow) via scipy, batched
    cost = np.full((Z, Z), np.inf)
    BATCH = 150
    for s0 in range(0, Z, BATCH):
        srcs = tnode[s0:s0+BATCH]
        dmat = dijkstra(csr, directed=False, indices=srcs)
        cost[s0:s0+BATCH, :] = dmat[:, tnode]
    log("OD cost done. finite frac=%.3f" % (np.isfinite(cost).mean()))
    # save od cost (sparse-ish: write all)
    with open(M + r"\2_trip_distribution\od_cost_district.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["o", "d", "min"])
        for i in range(Z):
            for j in range(Z):
                c = cost[i, j]; w.writerow([dids[i], dids[j], round(c, 2) if np.isfinite(c) else ""])

    # trip generation
    P = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}; A = {'pax': np.zeros(Z), 'frg': np.zeros(Z)}
    for r in csv.DictReader(open(M + r"\1_trip_generation\district_tripgen.csv", encoding="utf-8")):
        i = zpos[int(r['district_id'])]
        P['pax'][i] = float(r['P_pax']); A['pax'][i] = float(r['A_pax']); P['frg'][i] = float(r['P_frg']); A['frg'][i] = float(r['A_frg'])

    # intrazonal cost = 0.5*nearest
    cc = cost.copy()
    for i in range(Z):
        row = cc[i].copy(); row[i] = np.inf; nn = np.nanmin(np.where(np.isfinite(row), row, np.inf))
        cc[i, i] = 0.5*nn if np.isfinite(nn) else 15.0

    def gravity(Pv, Av, beta):
        f = np.where(np.isfinite(cc), np.exp(-beta*np.where(np.isfinite(cc), cc, 0)), 0.0)
        Av2 = Av*(Pv.sum()/max(Av.sum(), 1))
        a = np.ones(Z); b = np.ones(Z)
        for _ in range(120):
            a = 1.0/np.maximum((f*(b*Av2)).sum(1), 1e-9)
            b = 1.0/np.maximum((f.T*(a*Pv)).sum(1), 1e-9)
        return (a[:, None]*Pv[:, None])*(b[None, :]*Av2[None, :])*f
    # beta สูงขึ้นสำหรับระดับอำเภอ (ระยะสั้นกว่า -> intrazonal สมจริง)
    BETA_PAX_D, BETA_FRG_D = 0.045, 0.030
    T_pax = gravity(P['pax'], A['pax'], BETA_PAX_D)
    T_frg = gravity(P['frg'], A['frg'], BETA_FRG_D)
    od_pcu = T_pax*FAC_PAX + T_frg*FAC_FRG
    log("gravity done. total road PCU=%.0f intrazonal pax%%=%.1f" % (od_pcu.sum(), 100*np.trace(T_pax)/T_pax.sum()))

    # AON assignment: subtree-sum per source (free-flow tree)
    flow = np.zeros(nE)
    for s0 in range(0, Z, BATCH):
        srcs = tnode[s0:s0+BATCH]
        dmat, pred = dijkstra(csr, directed=False, indices=srcs, return_predecessors=True)
        for bi, si in enumerate(range(s0, min(s0+BATCH, Z))):
            dist_s = dmat[bi]; pred_s = pred[bi]
            acc = np.zeros(nN)
            # demand from source si to all districts -> their tie nodes
            np.add.at(acc, tnode, od_pcu[si])
            order = np.argsort(dist_s)  # ascending
            for node in order[::-1]:
                if not np.isfinite(dist_s[node]): continue
                p = pred_s[node]
                if p < 0: continue
                e = edge_of.get((p, node))
                if e is not None:
                    flow[e] += acc[node]; acc[p] += acc[node]
        log("  assigned sources up to %d/%d" % (min(s0+BATCH, Z), Z))

    # write
    out = QgsVectorLayer("LineString?crs=EPSG:32647", "assigned_district", "memory"); dp = out.dataProvider()
    dp.addAttributes([QgsField('vol_pcu', QVariant.Double), QgsField('voc', QVariant.Double)]); out.updateFields()
    fs = []
    for e in range(nE):
        if flow[e] <= 0: continue
        f = QgsFeature(out.fields()); f.setGeometry(Egeom[e]); f.setAttributes([round(float(flow[e]), 1), round(float(flow[e]/Ecap[e]), 3)]); fs.append(f)
    dp.addFeatures(fs)
    o = M + r"\4_trip_assignment\assigned_district.gpkg"
    if os.path.exists(o): os.remove(o)
    opt = QgsVectorFileWriter.SaveVectorOptions(); opt.driverName = "GPKG"; opt.layerName = "assigned_district"
    QgsVectorFileWriter.writeAsVectorFormatV3(out, o, QgsCoordinateTransformContext(), opt)
    log("wrote assigned_district: %d links | max=%.0f" % (len(fs), flow.max()))
    app.exitQgis(); log("DONE")

try: main()
except Exception: log("ERR", traceback.format_exc())
