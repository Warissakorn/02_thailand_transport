# -*- coding: utf-8 -*-
"""ขั้น 3: Trip Generation (2 สาย passenger + freight) — รันใน QGIS Python console
อินพุตต่อโซน i:
  pop_i = ประชากร (WorldPop zonal sum)   -> data/zones_taz/zone_population.gpkg
  sch_i = จำนวนสถานศึกษา (school poly centroid + point) -> data/landuse/schools_*.gpkg
  ind_i = พื้นที่นิคม/อุตสาหกรรม กม.^2 (landuse=industrial) -> data/landuse/industrial.gpkg

สูตร (v1 — magnitude ปรับเทียบในขั้น 7):
  Passenger:
    P_pax_i = pop_i * RP            (RP = 2.0 trips/person/day)
    a_i     = 0.7*pop_share + 0.3*school_share
    A_pax_i = sum(P_pax) * a_i      (=> sum A = sum P, balanced)
  Freight:
    T_F     = FF * sum(P_pax)       (FF = 0.10, freight ~ 10% ของ pax)
    pw_i    = 0.8*ind_share + 0.2*pop_share   (ผลิต = อุตสาหกรรมนำ)
    aw_i    = 0.5*ind_share + 0.5*pop_share   (ดึงดูด = บริโภคนำ)
    P_frg_i = T_F * pw_i ; A_frg_i = T_F * aw_i
ผลลัพธ์: trip_gen_passenger.gpkg , trip_gen_freight.gpkg (TAZ + P/A)
"""
import os, processing
from qgis.core import *
from qgis.PyQt.QtCore import QVariant

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT, hard_exit
BASE=_ROOT
_sys.path.insert(0, _os.path.join(str(BASE), "config"))
import model_params as mp
from lib import scenario as sc
sc.apply(mp)      # ทับด้วย inputs/scenarios/<TT_SCENARIO>.yaml
RP=mp.TRIP_RATE_PAX; FF=mp.FREIGHT_FACTOR

def cnt_in_provinces(prov, pts):
    """นับจุดต่อจังหวัด -> dict GID_1->count (ใช้ spatial index)"""
    from collections import defaultdict
    res=processing.run("native:countpointsinpolygon",
        {'POLYGONS':prov,'POINTS':pts,'FIELD':'NUMPOINTS','OUTPUT':'memory:'})['OUTPUT']
    return {f['GID_1']:(f['NUMPOINTS'] or 0) for f in res.getFeatures()}

def main():
    # เดิมรันใน Python console ของ QGIS; รันเป็นสคริปต์เดี่ยวต้อง init เอง
    from qgis.core import QgsApplication
    from processing.core.Processing import Processing
    app = QgsApplication([], False); app.initQgis(); Processing.initialize()

    prov4326=QgsVectorLayer(BASE+r"\data\boundaries\gadm41_THA.gpkg|layername=ADM_ADM_1","p","ogr")
    taz=QgsVectorLayer(BASE+r"\data\zones_taz\taz_provinces.gpkg|layername=taz_provinces","taz","ogr")
    popl=QgsVectorLayer(BASE+r"\data\zones_taz\zone_population.gpkg|layername=zone_population","pp","ogr")
    pop={f['GID_1']:(f['pop_sum'] or 0) for f in popl.getFeatures()}

    # schools: polygons -> centroids, + points ; รวมนับต่อจังหวัด
    spoly=QgsVectorLayer(BASE+r"\inputs\landuse\schools_poly.gpkg|layername=schools_poly","sp","ogr")
    spoly=processing.run("native:fixgeometries",{'INPUT':spoly,'OUTPUT':'memory:'})['OUTPUT']
    scen=processing.run("native:centroids",{'INPUT':spoly,'OUTPUT':'memory:'})['OUTPUT']
    spts=QgsVectorLayer(BASE+r"\inputs\landuse\schools_pts.gpkg|layername=schools_pts","spt","ogr")
    sc1=cnt_in_provinces(prov4326,scen); sc2=cnt_in_provinces(prov4326,spts)
    sch={k:sc1.get(k,0)+sc2.get(k,0) for k in pop}

    # industrial area km2 ต่อจังหวัด: intersection แล้วรวมพื้นที่ (คำนวณใน 32647)
    ind_src=QgsVectorLayer(BASE+r"\inputs\landuse\industrial.gpkg|layername=industrial","ind","ogr")
    ind_src=processing.run("native:fixgeometries",{'INPUT':ind_src,'OUTPUT':'memory:'})['OUTPUT']
    ind32=processing.run("native:reprojectlayer",{'INPUT':ind_src,'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:32647'),'OUTPUT':'memory:'})['OUTPUT']
    inter=processing.run("native:intersection",{'INPUT':ind32,'OVERLAY':taz,'OUTPUT':'memory:'})['OUTPUT']
    from collections import defaultdict
    ind=defaultdict(float)
    for f in inter.getFeatures(): ind[f['GID_1']]+=f.geometry().area()/1e6
    ind={k:ind.get(k,0.0) for k in pop}

    Spop=sum(pop.values()) or 1; Ssch=sum(sch.values()) or 1; Sind=sum(ind.values()) or 1
    SP_pax=sum(pop[k]*RP for k in pop); T_F=FF*SP_pax

    rows={}
    for k in pop:
        pop_s=pop[k]/Spop; sch_s=sch[k]/Ssch; ind_s=ind[k]/Sind
        P_pax=pop[k]*RP
        A_pax=SP_pax*(0.7*pop_s+0.3*sch_s)
        P_frg=T_F*(0.8*ind_s+0.2*pop_s)
        A_frg=T_F*(0.5*ind_s+0.5*pop_s)
        rows[k]=dict(pop=pop[k],sch=sch[k],ind=ind[k],P_pax=P_pax,A_pax=A_pax,P_frg=P_frg,A_frg=A_frg)

    # write two gpkg by attaching to taz
    for stream,fields in [("passenger",[('pop','pop',QVariant.Double),('n_school','sch',QVariant.Int),('P_pax','P_pax',QVariant.Double),('A_pax','A_pax',QVariant.Double)]),
                          ("freight",[('ind_km2','ind',QVariant.Double),('P_frg','P_frg',QVariant.Double),('A_frg','A_frg',QVariant.Double)])]:
        mem=processing.run("native:reprojectlayer",{'INPUT':taz,'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:32647'),'OUTPUT':'memory:'})['OUTPUT']
        mem.startEditing()
        for fn,_,ft in fields: mem.addAttribute(QgsField(fn,ft))
        mem.updateFields()
        fi={fn:mem.fields().indexOf(fn) for fn,_,_ in fields}
        for f in mem.getFeatures():
            r=rows[f['GID_1']]
            for fn,key,_ in fields: mem.changeAttributeValue(f.id(),fi[fn],round(r[key],2))
        mem.commitChanges()
        out=BASE+r"\model\1_trip_generation\trip_gen_%s.gpkg"%stream
        os.makedirs(os.path.dirname(out),exist_ok=True)
        if os.path.exists(out): os.remove(out)
        o=QgsVectorFileWriter.SaveVectorOptions(); o.driverName="GPKG"; o.layerName="trip_gen_%s"%stream
        QgsVectorFileWriter.writeAsVectorFormatV3(mem,out,QgsCoordinateTransformContext(),o)
        print("wrote",os.path.basename(out))
    print("totals: pop=%.0f schools=%d ind_km2=%.1f | P_pax=%.0f T_freight=%.0f"%(Spop,sum(sch.values()),Sind,SP_pax,T_F))
    print("DONE")
    hard_exit(0)   # ไม่ปิด QGIS แบบปกติ: teardown segfault บนคอนเทนเนอร์

if True: main()
