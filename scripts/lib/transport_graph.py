# -*- coding: utf-8 -*-
"""transport_graph — shared library ของแบบจำลอง (แทนโค้ดซ้ำใน 08b/09*/10*/11/12)
- build_road_graph(): กราฟถนน noding ถูกต้อง (T-junction) + รองรับ one-way (directed)
- build_simple_graph(): กราฟราง/น้ำ/อากาศ (undirected)
- od_cost_matrix(), assign_pairs(), msa_equilibrium(): scipy dijkstra
- gravity_furness(), geh(), fit_stats(): แกนคำนวณโมเดล
ใช้ใน QGIS python (qpy.bat) — ต้องมี numpy + scipy
"""
import math
import numpy as np
from collections import defaultdict
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from qgis.core import (QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant
import os, csv as _csv

# ขนาด batch ของ dijkstra: dmat/pred กินหน่วยความจำ batch x nN x 12 ไบต์
# กราฟระดับอำเภอมี ~2.8M node -> 1 origin กิน ~33 MB ค่าตั้งต้นเดิม (120-150)
# จึงต้องใช้ RAM 4 GB+ ต่อครั้งและถูก OOM kill บนเครื่องเล็ก/CI
# ปรับได้ด้วย scenario run.dijkstra_batch (ขั้น 13/14 ส่งต่อผ่าน env นี้ไปยัง worker)
DIJKSTRA_BATCH = max(int(os.environ.get("TT_DIJKSTRA_BATCH", "32")), 1)


class Graph:
    """กราฟเครือข่าย: node coords + edge arrays + csr (directed หรือไม่ก็ได้)"""
    def __init__(self, nxy, Eu, Ev, Ec, Eg, Eoneway=None):
        self.nxy = np.asarray(nxy, dtype=float)   # (nN,2)
        self.Eu = np.asarray(Eu); self.Ev = np.asarray(Ev)
        self.Ec = np.asarray(Ec, dtype=float)     # ต้นทุนต่อ edge (นาที)
        self.Eg = Eg                              # geometry ต่อ edge
        self.Eoneway = (np.asarray(Eoneway) if Eoneway is not None
                        else np.zeros(len(Eu), dtype=int))
        self.nN = len(self.nxy); self.nE = len(self.Eu)
        self.directed = bool(self.Eoneway.any())
        self._build_lookup(); self.rebuild_csr(self.Ec)

    def _build_lookup(self):
        """edge_of[(u,v)] = edge index (เฉพาะทิศที่วิ่งได้; เก็บ edge ที่ cost ต่ำสุด)"""
        self.edge_of = {}
        for e in range(self.nE):
            pairs = [(self.Eu[e], self.Ev[e])]
            if not self.Eoneway[e]:
                pairs.append((self.Ev[e], self.Eu[e]))
            for a, b in pairs:
                pe = self.edge_of.get((a, b))
                if pe is None or self.Ec[e] < self.Ec[pe]:
                    self.edge_of[(a, b)] = e

    def rebuild_csr(self, costs):
        """สร้าง csr ใหม่ด้วยต้นทุนที่กำหนด (ใช้ตอน equilibrium อัปเดตเวลา)"""
        costs = np.asarray(costs, dtype=float)
        two = ~self.Eoneway.astype(bool)
        rows = np.concatenate([self.Eu, self.Ev[two]])
        cols = np.concatenate([self.Ev, self.Eu[two]])
        data = np.concatenate([costs, costs[two]])
        self.csr = csr_matrix((data, (rows, cols)), shape=(self.nN, self.nN))
        return self.csr

    def nearest(self, x, y=None):
        if y is None:  # QgsPointXY
            x, y = x.x(), x.y()
        dx = self.nxy[:, 0] - x; dy = self.nxy[:, 1] - y
        return int(np.argmin(dx*dx + dy*dy))


def _extract_polyline(g):
    if g.isMultipart():
        return [p for part in g.asMultiPolyline() for p in part]
    return g.asPolyline()


def _noded_edges(feats):
    """feats: list of (rounded_verts, pts, cost_per_km_factor_or_speed, oneway)
    คืน node/edge arrays โดย split ที่จุดตัดจริง (endpoint หรือ vertex ร่วม >=2 เส้น)"""
    vcount = defaultdict(int)
    for rv, _, _, _ in feats:
        for k in rv: vcount[k] += 1
    nodeset = set()
    for rv, _, _, _ in feats:
        nodeset.add(rv[0]); nodeset.add(rv[-1])
    for k, c in vcount.items():
        if c >= 2: nodeset.add(k)
    node_id = {}; nxy = []
    Eu = []; Ev = []; Elen = []; Emeta = []; Eg = []; Eow = []
    for rv, pl, meta, ow in feats:
        idxs = [i for i, k in enumerate(rv) if k in nodeset]
        for a, b in zip(idxs[:-1], idxs[1:]):
            ka, kb = rv[a], rv[b]
            if ka == kb: continue
            for k, p in ((ka, pl[a]), (kb, pl[b])):
                if k not in node_id:
                    node_id[k] = len(nxy); nxy.append((p.x(), p.y()))
            sub = pl[a:b+1]; gs = QgsGeometry.fromPolylineXY(sub)
            Eu.append(node_id[ka]); Ev.append(node_id[kb])
            Elen.append(gs.length()); Emeta.append(meta); Eg.append(gs); Eow.append(ow)
    return nxy, Eu, Ev, Elen, Emeta, Eg, Eow


def build_road_graph(layer, directed=True, min_speed=3.0, round_dp=1, default_lanes=2):
    """กราฟถนนจาก network_clean: cost=เวลา(นาที) จาก speed_kmh; oneway_i -> directed
    เก็บ G.Ecap_hr = ความจุรายชั่วโมงต่อ edge (capacity/เลน/ชม. x เลน)
    หมายเหตุ: oneway=-1 (สวนทิศ digitize) ใน OSM ถูก treat เป็น oneway ปกติ — ดู LIMITATIONS"""
    feats = []
    for f in layer.getFeatures():
        g = f.geometry(); pl = _extract_polyline(g)
        if len(pl) < 2: continue
        rv = [(round(p.x(), round_dp), round(p.y(), round_dp)) for p in pl]
        spd = f['speed_kmh'] or 40.0
        ow = int(f['oneway_i'] or 0) if directed else 0
        try: lanes = int(str(f['lanes']).split(';')[0])
        except Exception: lanes = default_lanes
        cap_hr = (f['capacity'] or 800) * max(lanes, 1)
        feats.append((rv, pl, (float(spd), float(cap_hr)), ow))
    nxy, Eu, Ev, Elen, Emeta, Eg, Eow = _noded_edges(feats)
    Espd = [m[0] for m in Emeta]; Ecap = [m[1] for m in Emeta]
    Ec = [(L/1000.0)/max(s, min_speed)*60.0 for L, s in zip(Elen, Espd)]
    G = Graph(nxy, Eu, Ev, Ec, Eg, Eow)
    G.Elen = np.asarray(Elen); G.Espd = np.asarray(Espd); G.Ecap_hr = np.asarray(Ecap)
    return G


def build_simple_graph(layer, costmode='time', costfield=None, round_dp=1):
    """กราฟราง/น้ำ (costmode='time' ใช้ speed_kmh) หรือ air/sea (costmode='field')"""
    feats = []
    for f in layer.getFeatures():
        g = f.geometry(); pl = _extract_polyline(g)
        if len(pl) < 2: continue
        rv = [(round(p.x(), round_dp), round(p.y(), round_dp)) for p in pl]
        meta = (f[costfield] if costmode == 'field' else (f['speed_kmh'] or 40.0))
        feats.append((rv, pl, float(meta), 0))
    nxy, Eu, Ev, Elen, Emeta, Eg, _ = _noded_edges(feats)
    if costmode == 'field':
        Ec = Emeta
    else:
        Ec = [(L/1000.0)/max(s, 3.0)*60.0 for L, s in zip(Elen, Emeta)]
    return Graph(nxy, Eu, Ev, Ec, Eg)


# ---------------- routing / assignment ----------------

def od_cost_matrix(G, tie_nodes, batch=None):
    """เวลาเดินทางระหว่าง tie_nodes ทุกคู่ -> (Z,Z) numpy (inf = เข้าไม่ถึง)"""
    batch = batch or DIJKSTRA_BATCH
    tn = np.asarray(tie_nodes); Z = len(tn)
    cost = np.full((Z, Z), np.inf)
    for s0 in range(0, Z, batch):
        dmat = dijkstra(G.csr, directed=G.directed, indices=tn[s0:s0+batch])
        cost[s0:s0+batch, :] = dmat[:, tn]
    return cost


def assign_pairs(G, demand, batch=None, costs=None):
    """AON assignment: demand = {origin_node: {dest_node: pcu}} -> flow ต่อ edge
    costs: ถ้าให้มา จะ rebuild csr ชั่วคราว (เช่นตอน equilibrium)"""
    batch = batch or DIJKSTRA_BATCH
    if costs is not None: G.rebuild_csr(costs)
    flow = np.zeros(G.nE)
    origins = sorted(demand.keys())
    for s0 in range(0, len(origins), batch):
        srcs = origins[s0:s0+batch]
        dmat, pred = dijkstra(G.csr, directed=G.directed, indices=srcs,
                              return_predecessors=True)
        for bi, on in enumerate(srcs):
            ds = dmat[bi]; ps = pred[bi]
            acc = np.zeros(G.nN)
            for dn, v in demand[on].items(): acc[dn] += v
            if acc.sum() <= 0: continue
            for node in np.argsort(ds)[::-1]:
                if not np.isfinite(ds[node]): continue
                p = ps[node]
                if p < 0: continue
                e = G.edge_of.get((p, node))
                if e is not None:
                    flow[e] += acc[node]; acc[p] += acc[node]
    return flow


def assign_multi(G, demands, batch=None):
    """AON หลาย demand matrix ใน routing sweep เดียว (เส้นทางคงที่ ต่างกันแค่ปริมาณ)
    demands: list ของ {origin_node: {dest_node: value}} -> list ของ flow arrays"""
    batch = batch or DIJKSTRA_BATCH
    K = len(demands)
    flows = [np.zeros(G.nE) for _ in range(K)]
    all_origins = sorted(set().union(*[set(d.keys()) for d in demands]))
    for s0 in range(0, len(all_origins), batch):
        srcs = all_origins[s0:s0+batch]
        dmat, pred = dijkstra(G.csr, directed=G.directed, indices=srcs,
                              return_predecessors=True)
        for bi, on in enumerate(srcs):
            ds = dmat[bi]; ps = pred[bi]
            order = np.argsort(ds)[::-1]
            for ki in range(K):
                dd = demands[ki].get(on)
                if not dd: continue
                acc = np.zeros(G.nN)
                for dn, v in dd.items(): acc[dn] += v
                if acc.sum() <= 0: continue
                for node in order:
                    if not np.isfinite(ds[node]): continue
                    p = ps[node]
                    if p < 0: continue
                    e = G.edge_of.get((p, node))
                    if e is not None:
                        flows[ki][e] += acc[node]; acc[p] += acc[node]
    return flows


def robust_tie(G, pts, sample_targets=None, min_reach=0.9, n_cand=6):
    """หา node ผูกต่อจุด โดยเลือก candidate ใกล้สุดที่เข้าถึงเครือข่ายส่วนใหญ่ได้
    (กัน centroid ติด stub ที่ one-way ตัดขาด) — ทดสอบด้วย dijkstra ไปยัง sample_targets"""
    ties = []
    nxy = G.nxy
    for p in pts:
        x, y = (p.x(), p.y()) if hasattr(p, 'x') else (p[0], p[1])
        dx = nxy[:, 0]-x; dy = nxy[:, 1]-y
        cand = np.argsort(dx*dx + dy*dy)[:n_cand]
        ties.append(cand)
    # ตรวจ candidate แรกทั้งชุดพร้อมกัน แล้วซ่อมเฉพาะตัวที่แย่
    first = np.array([c[0] for c in ties])
    targets = first if sample_targets is None else np.asarray(sample_targets)
    # เดิมยิง dijkstra ทุกจุดพร้อมกันครั้งเดียว: 928 อำเภอ x 2.76M node x 8 ไบต์ = ~20 GB
    # -> ถูก OOM kill ทันที ทำเป็น batch แล้วเก็บเฉพาะสัดส่วน reach (ผลลัพธ์เท่าเดิมทุกประการ)
    reach = np.empty(len(first), dtype=float)
    for s0 in range(0, len(first), DIJKSTRA_BATCH):
        dm = dijkstra(G.csr, directed=G.directed, indices=first[s0:s0+DIJKSTRA_BATCH])
        reach[s0:s0+DIJKSTRA_BATCH] = np.isfinite(dm[:, targets]).mean(axis=1)
    out = first.copy()
    for i in np.where(reach < min_reach)[0]:
        for c in ties[i][1:]:
            d = dijkstra(G.csr, directed=G.directed, indices=[c])[0]
            if np.isfinite(d[targets]).mean() >= min_reach:
                out[i] = c; break
    return out.tolist(), reach


def msa_equilibrium(G, demand, cap, t0, n_iter=25, alpha=0.15, beta=4.0, log=None):
    """MSA user-equilibrium: t = t0*(1+alpha*(v/cap)^beta) ; คืน flow เฉลี่ยลู่เข้า"""
    x = assign_pairs(G, demand, costs=t0)
    if log: log("  eq iter 1 (free-flow) maxflow=%.0f" % x.max())
    for n in range(2, n_iter+1):
        t = t0*(1.0 + alpha*np.power(np.maximum(x, 0)/np.maximum(cap, 1), beta))
        y = assign_pairs(G, demand, costs=t)
        x = x + (1.0/n)*(y - x)
        if log and (n % 5 == 0 or n == n_iter):
            gap = np.abs(y-x).sum()/max(x.sum(), 1)
            log("  eq iter %d gap=%.4f maxflow=%.0f" % (n, gap, x.max()))
    G.rebuild_csr(t0)  # คืนสถานะ free-flow
    return x


# ---------------- model core ----------------

def gravity_furness(P, A, cost, beta, n_iter=150, intrazonal_factor=0.5):
    """doubly-constrained gravity, f=exp(-beta*c); intrazonal c = factor*nearest"""
    Z = len(P)
    cc = np.array(cost, dtype=float)
    for i in range(Z):
        row = cc[i].copy(); row[i] = np.inf
        nn = np.nanmin(np.where(np.isfinite(row), row, np.inf))
        cc[i, i] = intrazonal_factor*nn if np.isfinite(nn) else 15.0
    f = np.where(np.isfinite(cc), np.exp(-beta*np.where(np.isfinite(cc), cc, 0)), 0.0)
    P = np.asarray(P, float); A = np.asarray(A, float)
    A2 = A*(P.sum()/max(A.sum(), 1e-9))
    a = np.ones(Z); b = np.ones(Z)
    for _ in range(n_iter):
        a = 1.0/np.maximum((f*(b*A2)).sum(1), 1e-12)
        b = 1.0/np.maximum((f.T*(a*P)).sum(1), 1e-12)
    return (a[:, None]*P[:, None])*(b[None, :]*A2[None, :])*f


def geh(m, c):
    return math.sqrt(2*(m-c)**2/(m+c)) if (m+c) > 0 else 0.0


def fit_stats(modeled, observed):
    """คืน dict: k (LS through origin), geh5/geh10 (%), median_geh, r2, rmse — คำนวณหลัง scale k"""
    m = np.asarray(modeled, float); o = np.asarray(observed, float)
    k = float((m*o).sum()/max((m*m).sum(), 1e-12))
    cal = k*m
    g = np.array([geh(a, b) for a, b in zip(cal, o)])
    ssres = ((o-cal)**2).sum(); sstot = ((o-o.mean())**2).sum()
    return {'k': k, 'n': len(m),
            'geh5': float((g < 5).mean()*100), 'geh10': float((g < 10).mean()*100),
            'median_geh': float(np.median(g)),
            'r2': float(1-ssres/max(sstot, 1e-12)),
            'rmse': float(math.sqrt(ssres/len(m)))}


# ---------------- I/O helpers ----------------

def read_mode_od(csv_path, modes_weight, zidx, Z):
    """อ่าน mode_split csv -> OD matrix รวมโหมดตามน้ำหนัก (เช่น PCU)"""
    od = np.zeros((Z, Z))
    with open(csv_path, encoding='utf-8') as fh:
        for r in _csv.DictReader(fh):
            w = modes_weight.get(r['mode'])
            if w:
                i = zidx.get(int(r['orig_zone'])); j = zidx.get(int(r['dest_zone']))
                if i is not None and j is not None:
                    od[i][j] += float(r['trips'])*w
    return od


def write_flow_gpkg(G, flows_dict, out_path, layer_name):
    """flows_dict: {field: flow_array}; เขียนเฉพาะ edge ที่มี flow > 0"""
    lyr = QgsVectorLayer("LineString?crs=EPSG:32647", layer_name, "memory")
    dp = lyr.dataProvider()
    names = list(flows_dict.keys())
    dp.addAttributes([QgsField(n, QVariant.Double) for n in names])
    lyr.updateFields()
    arrays = [flows_dict[n] for n in names]
    feats = []
    for e in range(G.nE):
        tot = sum(a[e] for a in arrays)
        if tot <= 0: continue
        ft = QgsFeature(lyr.fields()); ft.setGeometry(G.Eg[e])
        ft.setAttributes([round(float(a[e]), 1) for a in arrays])
        feats.append(ft)
    dp.addFeatures(feats)
    if os.path.exists(out_path): os.remove(out_path)
    o = QgsVectorFileWriter.SaveVectorOptions()
    o.driverName = "GPKG"; o.layerName = layer_name
    QgsVectorFileWriter.writeAsVectorFormatV3(lyr, out_path, QgsCoordinateTransformContext(), o)
    return len(feats)
