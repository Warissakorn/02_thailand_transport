# -*- coding: utf-8 -*-
"""โครงข่ายขนส่งสินค้าทางน้ำ: ท่าเรือพาณิชย์หลัก + เส้นทางเดินเรือชายฝั่ง (coastal shipping)
+ access connector โซน -> ท่าเรือใหญ่ใกล้สุด
out: data/multimodal/seaport_nodes.gpkg, water_freight_links.gpkg ; data/zones_taz/access_seafreight.gpkg
รันผ่าน qpy.bat ; log -> output/_wf.log
"""
import os, math, traceback
from qgis.core import (QgsApplication, QgsVectorLayer, QgsField, QgsFeature, QgsGeometry,
    QgsPointXY, QgsSpatialIndex, QgsVectorFileWriter, QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext, QgsProject, QgsCoordinateTransform)
from qgis.PyQt.QtCore import QVariant

B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
LOG = open(B + r"\output\_wf.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
SHIP_KMH = 25.0; ACCESS_KMH = 50.0; DETOUR = 1.3

# ท่าเรือพาณิชย์หลัก (lon, lat, coast)
PORTS = {
 'BKK': ('ท่าเรือกรุงเทพ (คลองเตย)', 100.585, 13.705, 'gulf'),
 'SCH': ('ศรีราชา', 100.930, 13.170, 'gulf'),
 'LCB': ('แหลมฉบัง', 100.883, 13.082, 'gulf'),
 'SAT': ('สัตหีบ', 100.905, 12.657, 'gulf'),
 'MTP': ('มาบตาพุด', 101.145, 12.677, 'gulf'),
 'CHU': ('ชุมพร', 99.200, 10.500, 'gulf'),
 'SUR': ('สุราษฎร์ธานี (บ้านดอน)', 99.330, 9.140, 'gulf'),
 'SOK': ('สงขลา', 100.593, 7.208, 'gulf'),
 'RAN': ('ระนอง', 98.610, 9.960, 'andaman'),
 'PKT': ('ภูเก็ต (น้ำลึก)', 98.410, 7.812, 'andaman'),
}
# เส้นทางเดินเรือชายฝั่ง (คู่ท่าเรือที่เชื่อมกัน)
EDGES = [('BKK','SCH'),('SCH','LCB'),('LCB','SAT'),('SAT','MTP'),('BKK','LCB'),
         ('MTP','CHU'),('CHU','SUR'),('SUR','SOK'),  # อ่าวไทย
         ('RAN','PKT')]                                # อันดามัน

def gc_km(a, b):
    R=6371.0; la1,lo1,la2,lo2=map(math.radians,[a[1],a[0],b[1],b[0]])
    h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))

try:
    app = QgsApplication([], False); app.initQgis()
    # nodes
    nodes = QgsVectorLayer("Point?crs=EPSG:4326", "seaport_nodes", "memory"); dp = nodes.dataProvider()
    dp.addAttributes([QgsField('code',QVariant.String),QgsField('name',QVariant.String),QgsField('coast',QVariant.String)]); nodes.updateFields()
    for code,(nm,lon,lat,coast) in PORTS.items():
        f=QgsFeature(nodes.fields()); f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon,lat)))
        f.setAttributes([code,nm,coast]); dp.addFeature(f)
    # links
    links = QgsVectorLayer("LineString?crs=EPSG:4326", "water_freight_links", "memory"); lp = links.dataProvider()
    lp.addAttributes([QgsField('a',QVariant.String),QgsField('b',QVariant.String),QgsField('dist_km',QVariant.Double),QgsField('sail_min',QVariant.Double)]); links.updateFields()
    for a,b in EDGES:
        pa=PORTS[a]; pb=PORTS[b]; d=gc_km((pa[1],pa[2]),(pb[1],pb[2]))
        f=QgsFeature(links.fields()); f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(pa[1],pa[2]),QgsPointXY(pb[1],pb[2])]))
        f.setAttributes([a,b,round(d,1),round(d/SHIP_KMH*60,1)]); lp.addFeature(f)
    for lyr,name in [(nodes,"seaport_nodes"),(links,"water_freight_links")]:
        out=B+r"\data\multimodal\%s.gpkg"%name
        if os.path.exists(out): os.remove(out)
        o=QgsVectorFileWriter.SaveVectorOptions(); o.driverName="GPKG"; o.layerName=name
        QgsVectorFileWriter.writeAsVectorFormatV3(lyr,out,QgsCoordinateTransformContext(),o)
        log("wrote",name,lyr.featureCount())

    # access connector: zone centroid -> nearest seaport (เป็น 32647)
    ct = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'),QgsCoordinateReferenceSystem('EPSG:32647'),QgsProject.instance())
    sea32 = {code:ct.transform(QgsPointXY(lon,lat)) for code,(nm,lon,lat,coast) in PORTS.items()}
    cen = QgsVectorLayer(B+r"\data\zones_taz\taz_centroids_pw.gpkg|layername=taz_centroids_pw","c","ogr")
    acc = QgsVectorLayer("LineString?crs=EPSG:32647","access_seafreight","memory"); ap=acc.dataProvider()
    ap.addAttributes([QgsField('zone_id',QVariant.Int),QgsField('NAME_1',QVariant.String),QgsField('port',QVariant.String),QgsField('access_km',QVariant.Double),QgsField('access_min',QVariant.Double)]); acc.updateFields()
    for f in cen.getFeatures():
        pt=f.geometry().asPoint(); best=None;bd=1e18
        for code,sp in sea32.items():
            d=QgsGeometry.fromPointXY(QgsPointXY(pt)).distance(QgsGeometry.fromPointXY(sp))
            if d<bd: bd=d;best=code;bpt=sp
        dk=bd/1000.0; acc_min=dk*DETOUR/ACCESS_KMH*60
        nf=QgsFeature(acc.fields()); nf.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(pt),bpt]))
        nf.setAttributes([f['zone_id'],f['NAME_1'],best,round(dk,1),round(acc_min,1)]); ap.addFeature(nf)
    out=B+r"\data\zones_taz\access_seafreight.gpkg"
    if os.path.exists(out): os.remove(out)
    o=QgsVectorFileWriter.SaveVectorOptions(); o.driverName="GPKG"; o.layerName="access_seafreight"
    QgsVectorFileWriter.writeAsVectorFormatV3(acc,out,QgsCoordinateTransformContext(),o)
    log("access_seafreight: 77 | sample edges dist:", [(a,b,round(gc_km((PORTS[a][1],PORTS[a][2]),(PORTS[b][1],PORTS[b][2])))) for a,b in EDGES[:4]])
    app.exitQgis(); log("DONE")
except Exception:
    log("ERR", traceback.format_exc())
