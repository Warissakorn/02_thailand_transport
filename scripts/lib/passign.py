# -*- coding: utf-8 -*-
"""passign — AON assignment แบบขนาน (multiprocessing) สำหรับ equilibrium ที่ช้า
แนวคิด: flow ของแต่ละ origin เป็นอิสระและบวกกันได้ -> แบ่ง origins ไปหลาย process
แล้วรวม flow -> ผลลัพธ์ 'เท่ากับ' assign_multi/assign_pairs แบบ serial ทุกประการ
โมดูลนี้ตั้งใจ **ไม่ import qgis** เพื่อให้ worker (spawn บน Windows) เบา/เร็ว
ใช้ได้กับกราฟ directed/undirected เดียวกับ lib.transport_graph.Graph
"""
import os
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

# ---- globals ต่อ worker (ตั้งครั้งเดียวตอน Pool init) ----
_S = {}


def init(Eu, Ev, Eoneway, edge_of, nN, nE, directed):
    _S['Eu'] = np.asarray(Eu)
    _S['Ev'] = np.asarray(Ev)
    _S['two'] = ~np.asarray(Eoneway).astype(bool)   # edge ที่วิ่งได้สองทิศ
    _S['edge_of'] = edge_of
    _S['nN'] = int(nN)
    _S['nE'] = int(nE)
    _S['directed'] = bool(directed)


def make_pool(nworkers, G):
    """สร้าง Pool ให้ประหยัดหน่วยความจำที่สุดเท่าที่ OS อนุญาต

    ปัญหา: initargs ของ Pool ถูก pickle ส่งให้ worker ทุกตัว — G.edge_of เป็น dict
    ~6.7 ล้านคีย์ (ราว 1 GB) กราฟระดับอำเภอจึงกินหน่วยความจำเป็นทวีคูณตามจำนวน worker
    จนถูก OOM kill บนเครื่อง 16 GB

    บน Linux (fork) จึงตั้งค่า global ในโปรเซสแม่ก่อน แล้ว fork เอา — worker เห็นข้อมูล
    เดียวกันแบบ copy-on-write ไม่ต้องสำเนา ส่วน Windows (spawn) ใช้ initializer ตามเดิม
    """
    import multiprocessing as _mp
    args = (G.Eu, G.Ev, G.Eoneway, G.edge_of, G.nN, G.nE, G.directed)
    try:
        ctx = _mp.get_context("fork")
        init(*args)                      # ตั้งในแม่ -> ลูกได้มาแบบแชร์หน้า memory
        return ctx.Pool(nworkers), "fork (shared)"
    except (ValueError, AttributeError, OSError):
        ctx = _mp.get_context()
        return ctx.Pool(nworkers, initializer=init, initargs=args), ctx.get_start_method()


def _csr(costs):
    Eu = _S['Eu']; Ev = _S['Ev']; two = _S['two']
    rows = np.concatenate([Eu, Ev[two]])
    cols = np.concatenate([Ev, Eu[two]])
    data = np.concatenate([costs, costs[two]])
    return csr_matrix((data, (rows, cols)), shape=(_S['nN'], _S['nN']))


def _work(task):
    """task = (costs, origins, dem_list) ; dem_list = list ของ K dict {dest: val}
    (จำกัดเฉพาะ origins ในชิ้นนี้) -> คืน list ของ K flow arrays (nE,)"""
    costs, origins, dem_list = task
    csr = _csr(np.asarray(costs, dtype=float))
    nE = _S['nE']; nN = _S['nN']; edge_of = _S['edge_of']; directed = _S['directed']
    K = len(dem_list)
    flows = [np.zeros(nE) for _ in range(K)]
    # batch dijkstra ภายใน worker (dmat+pred = B x nN x 12 ไบต์ ต่อ worker)
    B = max(int(os.environ.get("TT_DIJKSTRA_BATCH", "32")), 1)
    for s0 in range(0, len(origins), B):
        srcs = origins[s0:s0 + B]
        dmat, pred = dijkstra(csr, directed=directed, indices=srcs,
                              return_predecessors=True)
        for bi, on in enumerate(srcs):
            ds = dmat[bi]; ps = pred[bi]
            order = np.argsort(ds)[::-1]
            for ki in range(K):
                dd = dem_list[ki].get(on)
                if not dd:
                    continue
                acc = np.zeros(nN)
                for dn, v in dd.items():
                    acc[dn] += v
                if acc.sum() <= 0:
                    continue
                for node in order:
                    if not np.isfinite(ds[node]):
                        continue
                    p = ps[node]
                    if p < 0:
                        continue
                    e = edge_of.get((p, node))
                    if e is not None:
                        flows[ki][e] += acc[node]
                        acc[p] += acc[node]
    return flows


def run_assign(pool, nchunks, costs, demands):
    """ฝั่ง parent: แบ่ง origins (union ของทุก demand) เป็น nchunks (round-robin เพื่อ
    บาลานซ์ภาระ) -> pool.map -> รวม flow. demands = list ของ K dict {orig:{dest:val}}
    คืน list ของ K flow arrays (เท่ากับ transport_graph.assign_multi ทุกประการ)"""
    costs = np.asarray(costs, dtype=float)
    origins = sorted(set().union(*[set(d.keys()) for d in demands]))
    chunks = [origins[i::nchunks] for i in range(nchunks)]
    tasks = []
    for ch in chunks:
        if not ch:
            continue
        chset = set(ch)
        dem_sub = [{o: d[o] for o in ch if o in d} for d in demands]
        tasks.append((costs, ch, dem_sub))
    results = pool.map(_work, tasks)
    K = len(demands)
    flows = []
    for ki in range(K):
        acc = np.zeros(results[0][ki].shape[0])
        for r in results:
            acc += r[ki]
        flows.append(acc)
    return flows
