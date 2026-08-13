# -*- coding: utf-8 -*-
"""สร้างโครงข่ายทางอากาศจาก OpenFlights -> data/multimodal/air_nodes.gpkg + air_links.gpkg
node = สนามบินไทย (IATA, lat/lon) ; link = คู่เส้นทางบินในประเทศ + ระยะทาง great-circle
รันผ่าน qpy.bat ; log -> output/_air.log
"""
import os, csv, math, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsPointXY, QgsVectorFileWriter, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext)
from qgis.PyQt.QtCore import QVariant

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_air.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()

def gc_km(a, b):
    R=6371.0; la1,lo1,la2,lo2=map(math.radians,[a[1],a[0],b[1],b[0]])
    h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))

try:
    app=QgsApplication([],False); app.initQgis()
    md=B+r"\data\multimodal"
    TH={}
    for row in csv.reader(open(md+r"\openflights_airports.dat",encoding="utf-8")):
        if len(row)>7 and row[3]=="Thailand" and row[4] and row[4]!="\\N":
            try: TH[row[4]]=(row[1],float(row[7]),float(row[6]))  # IATA->(name,lon,lat)
            except: pass
    pairs=set()
    for row in csv.reader(open(md+r"\openflights_routes.dat",encoding="utf-8")):
        if len(row)>4 and row[2] in TH and row[4] in TH and row[2]!=row[4]:
            pairs.add(tuple(sorted((row[2],row[4]))))
    log("airports:",len(TH),"pairs:",len(pairs))

    # nodes
    nodes=QgsVectorLayer("Point?crs=EPSG:4326","air_nodes","memory"); dp=nodes.dataProvider()
    dp.addAttributes([QgsField("iata",QVariant.String),QgsField("name",QVariant.String)]); nodes.updateFields()
    for iata,(nm,lon,lat) in TH.items():
        f=QgsFeature(nodes.fields()); f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon,lat)))
        f.setAttributes([iata,nm]); dp.addFeature(f)
    # links
    links=QgsVectorLayer("LineString?crs=EPSG:4326","air_links","memory"); lp=links.dataProvider()
    lp.addAttributes([QgsField("a",QVariant.String),QgsField("b",QVariant.String),
                      QgsField("dist_km",QVariant.Double),QgsField("fly_min",QVariant.Double)]); links.updateFields()
    for a,b in pairs:
        pa=TH[a]; pb=TH[b]; d=gc_km((pa[1],pa[2]),(pb[1],pb[2]))
        # เวลาบิน ≈ 30 นาที (ขึ้น-ลง/taxi) + ระยะ/750 กม.ต่อชม.
        fly=30+ d/750.0*60.0
        f=QgsFeature(links.fields())
        f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(pa[1],pa[2]),QgsPointXY(pb[1],pb[2])]))
        f.setAttributes([a,b,round(d,1),round(fly,1)]); lp.addFeature(f)

    for lyr,name in [(nodes,"air_nodes"),(links,"air_links")]:
        out=md+"\\%s.gpkg"%name
        if os.path.exists(out): os.remove(out)
        o=QgsVectorFileWriter.SaveVectorOptions(); o.driverName="GPKG"; o.layerName=name
        QgsVectorFileWriter.writeAsVectorFormatV3(lyr,out,QgsCoordinateTransformContext(),o)
        log("wrote",name,lyr.featureCount())
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR",traceback.format_exc())
