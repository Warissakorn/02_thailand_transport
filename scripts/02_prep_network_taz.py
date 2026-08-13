# -*- coding: utf-8 -*-
"""ขั้น 2: เตรียมโครงข่ายถนน — รันใน Python console ของ QGIS (มี processing + GDAL)
- อ่าน data/network/roads_raw_4326.gpkg (สร้างโดย 02a_extract_osm.py)
- เพิ่ม speed_kmh / travel_time_min / capacity_pcph ตามชั้นถนน (ใช้ maxspeed ถ้ามี)
- reproject -> EPSG:32647 -> data/network/network_clean.gpkg
TAZ (จังหวัด) + ประชากรรายโซน สร้างโดย 02b_build_taz.py -> data/zones_taz/
"""
import os, processing
from qgis.core import (QgsVectorLayer, QgsField, QgsVectorFileWriter,
                       QgsCoordinateReferenceSystem, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant

# --- project root (ข้ามแพลตฟอร์ม: Windows/Linux; ดู scripts/lib/paths.py) ---
import os as _os, sys as _sys
_d = _os.path.dirname(_os.path.abspath(__file__))
while _d != _os.path.dirname(_d) and not _os.path.isdir(_os.path.join(_d, "config")):
    _d = _os.path.dirname(_d)
_sys.path.insert(0, _os.path.join(_d, "scripts"))
from lib.paths import ROOT as _ROOT
BASE = _ROOT
SRC  = BASE + r"\data\network\roads_raw_4326.gpkg"
OUT  = BASE + r"\data\network\network_clean.gpkg"

# ค่าเริ่มต้นต่อชั้นถนน: (free-flow speed กม./ชม., capacity คัน-PCU/ชม./เลน)
DEFAULT = {
    'motorway':(110,2000),'motorway_link':(60,1500),
    'trunk':(90,1800),'trunk_link':(50,1400),
    'primary':(80,1600),'primary_link':(45,1200),
    'secondary':(70,1400),'secondary_link':(40,1000),
    'tertiary':(60,1000),'tertiary_link':(35,800),
    'unclassified':(50,800),'residential':(40,600),
    'living_street':(20,400),'road':(50,800),
}

def parse_speed(maxspeed, hw):
    if maxspeed:
        s = str(maxspeed).strip().lower().replace('km/h','').replace('kmh','').strip()
        try: return float(s.split()[0])
        except Exception: pass
    return DEFAULT.get(hw,(40,600))[0]

def main():
    roads = QgsVectorLayer(SRC, "roads_raw", "ogr")
    assert roads.isValid(), "roads_raw not found/valid"
    print("raw roads:", roads.featureCount())

    # reproject -> 32647 (เมตร) ก่อน เพื่อคำนวณความยาว/เวลา
    rep = processing.run("native:reprojectlayer",
        {'INPUT':roads,'TARGET_CRS':QgsCoordinateReferenceSystem('EPSG:32647'),
         'OUTPUT':'memory:net'})['OUTPUT']

    rep.startEditing()
    for n,t in [('length_m',QVariant.Double),('speed_kmh',QVariant.Double),
                ('travel_min',QVariant.Double),('capacity',QVariant.Int),
                ('oneway_i',QVariant.Int)]:
        if rep.fields().indexOf(n)==-1: rep.addAttribute(QgsField(n,t))
    rep.updateFields()
    fi={n:rep.fields().indexOf(n) for n in ['length_m','speed_kmh','travel_min','capacity','oneway_i']}
    hw_i=rep.fields().indexOf('highway'); ms_i=rep.fields().indexOf('maxspeed'); ow_i=rep.fields().indexOf('oneway')
    for f in rep.getFeatures():
        hw=f['highway']; L=f.geometry().length()
        spd=parse_speed(f['maxspeed'] if ms_i>=0 else None, hw)
        cap=DEFAULT.get(hw,(40,600))[1]
        tmin=(L/1000.0)/max(spd,5)*60.0
        ow=f['oneway'] if ow_i>=0 else None
        owi=1 if str(ow).lower() in ('yes','true','1','-1') else 0
        rep.changeAttributeValue(f.id(),fi['length_m'],round(L,1))
        rep.changeAttributeValue(f.id(),fi['speed_kmh'],spd)
        rep.changeAttributeValue(f.id(),fi['travel_min'],round(tmin,4))
        rep.changeAttributeValue(f.id(),fi['capacity'],cap)
        rep.changeAttributeValue(f.id(),fi['oneway_i'],owi)
    rep.commitChanges()

    if os.path.exists(OUT): os.remove(OUT)
    opts=QgsVectorFileWriter.SaveVectorOptions(); opts.driverName="GPKG"; opts.layerName="network_clean"
    QgsVectorFileWriter.writeAsVectorFormatV3(rep,OUT,QgsCoordinateTransformContext(),opts)
    print("wrote network_clean ->",OUT, "| feats:",rep.featureCount())

if __name__=="__main__" or True:
    main()
