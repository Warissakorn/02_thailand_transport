# -*- coding: utf-8 -*-
"""Diagnostic: ถนนความจุสูงแต่ปริมาณจราจรต่ำ (high capacity / low V-C)
map ปริมาณ (assigned_final_dist, vol_pcu รายวัน) ลงบน feature ถนน (network_clean) ->
คำนวณ V/C ใหม่แบบละเอียด (voc ในไฟล์ปัดทศนิยม -> 0.0 ใช้ไม่ได้กับสาย low-V/C):
  voc_peak = vol_pcu * K_FACTOR / cap_hr   ; cap_hr = capacity_perlane * lanes
แยกรายงาน: (A) สายความจุสูงที่ under-loaded (0<voc<0.05) (B) สายความจุสูงที่ flow=0
out: output/report/tables/T6_capacity_utilization.csv ; log output/_diag.log ; qpy.bat
"""
import os, sys, csv, traceback
import numpy as np
B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_diag.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
K = 0.09
MAJOR = {'motorway', 'trunk', 'primary', 'motorway_link', 'trunk_link'}


def main():
    from qgis.core import QgsApplication, QgsVectorLayer, QgsSpatialIndex, QgsFeature
    app = QgsApplication([], False); app.initQgis()

    net = QgsVectorLayer(B + r"\data\network\network_clean.gpkg|layername=network_clean", "n", "ogr")
    feats = {}; idx = QgsSpatialIndex()
    for f in net.getFeatures():
        g = f.geometry()
        if g.isEmpty(): continue
        try: lanes = int(str(f['lanes']).split(';')[0])
        except Exception: lanes = 2
        cap = (f['capacity'] or 800) * max(lanes, 1)
        fid = f.id()
        feats[fid] = {'ref': f['ref'] or '', 'name': f['name'] or '', 'hw': f['highway'] or '',
                      'lanes': lanes, 'cap': cap, 'len': float(f['length_m'] or g.length()),
                      'vol': 0.0, 'mid': g.interpolate(g.length()*0.5)}
        ff = QgsFeature(fid); ff.setGeometry(g); idx.addFeature(ff)
    log("network features: %d" % len(feats))

    asg = QgsVectorLayer(B + r"\model\4_trip_assignment\assigned_final_dist.gpkg|layername=assigned_final_dist", "a", "ogr")
    n = 0
    for f in asg.getFeatures():
        g = f.geometry(); mp = g.interpolate(g.length()*0.5)
        if mp.isEmpty(): continue
        near = idx.nearestNeighbor(mp.asPoint(), 1)
        if not near: continue
        fid = near[0]; v = float(f['vol_pcu'] or 0.0)
        if v > feats[fid]['vol']: feats[fid]['vol'] = v   # ปริมาณสูงสุดบน sub-edge ของสายนั้น
        n += 1
    log("assigned edges mapped: %d" % n)

    rows = list(feats.values())
    for d in rows: d['voc'] = d['vol']*K/max(d['cap'], 1)
    caps = np.array([d['cap'] for d in rows])
    p75, p90 = np.percentile(caps, 75), np.percentile(caps, 90)
    log("cap_hr p75=%.0f p90=%.0f max=%.0f" % (p75, p90, caps.max()))

    highcap = [d for d in rows if d['cap'] >= p75 or d['hw'] in MAJOR]
    under = [d for d in highcap if 0 < d['voc'] < 0.05]
    zero = [d for d in highcap if d['vol'] <= 0]
    log("high-cap features: %d | under-loaded(0<voc<0.05): %d | zero-flow: %d" % (
        len(highcap), len(under), len(zero)))
    log("high-cap zero-flow total length = %.1f km" % (sum(d['len'] for d in zero)/1000))

    # จังหวัดของแถวที่จะรายงาน (เฉพาะ top -> เบา)
    prov = QgsVectorLayer(B + r"\data\zones_taz\taz_provinces.gpkg|layername=taz_provinces", "p", "ogr")
    pfld = 'NAME_1' if prov.fields().indexFromName('NAME_1') >= 0 else prov.fields()[0].name()
    pv = [(f.geometry(), f[pfld]) for f in prov.getFeatures()]
    def provof(mid):
        for g, nm in pv:
            if g.contains(mid): return nm
        return "?"

    def emit(w, tag, items, top=40):
        items = sorted(items, key=lambda d: (-d['cap'], d['voc']))[:top]
        for d in items:
            w.writerow([tag, d['ref'], d['name'], d['hw'], d['lanes'], int(d['cap']),
                        round(d['vol'], 1), round(d['voc'], 4), round(d['len']/1000, 2),
                        provof(d['mid'])])

    os.makedirs(B + r"\output\report\tables", exist_ok=True)
    with open(B + r"\output\report\tables\T6_capacity_utilization.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["category", "highway_ref", "name", "osm_class", "lanes", "cap_veh_hr",
                    "model_vol_pcu_day", "voc_peak", "length_km", "province"])
        emit(w, "ZERO_FLOW_highcap", zero)
        emit(w, "UNDERLOADED_highcap", under)

    # สรุปตาม class
    log("--- high-cap by class (count | zero-flow | median voc) ---")
    for hw in sorted(set(d['hw'] for d in highcap)):
        sub = [d for d in highcap if d['hw'] == hw]
        z = sum(1 for d in sub if d['vol'] <= 0)
        mv = float(np.median([d['voc'] for d in sub]))
        log("  %-14s n=%-6d zero=%-5d medVOC=%.4f" % (hw, len(sub), z, mv))
    app.exitQgis(); log("DONE")


if __name__ == '__main__':
    try: main()
    except Exception: log("ERR", traceback.format_exc())
