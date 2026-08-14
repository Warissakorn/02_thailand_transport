# -*- coding: utf-8 -*-
"""ขั้น 1: ดาวน์โหลดข้อมูลนำเข้าสำหรับแบบจำลองขนส่งไทย
ใช้: python 01_fetch_data.py <what>   where what in {gadm, osm, all}
"""
import os, sys, urllib.request, time, ssl, socket

# data.go.th uses a cert chain that may not verify on all hosts + needs a UA
_CTX = ssl.create_default_context(); _CTX.check_hostname = False; _CTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_CTX))
_OPENER.addheaders = [("User-Agent", "Mozilla/5.0")]
urllib.request.install_opener(_OPENER)

ROOT = os.environ.get("TT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# เขียน log ของตัวเองเหมือนสคริปต์อื่น ๆ เพื่อให้ step ดัมพ์ log ท้าย job เห็นด้วยว่า
# แหล่งไหนล้ม (เดิมพิมพ์ลง stdout อย่างเดียว ต้องไล่หากลาง log ของ job)
os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)
LOG = open(os.path.join(ROOT, "output", "_01.log"), "w", encoding="utf-8")


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.write(msg + "\n"); LOG.flush()
    print(msg, flush=True)
DIRS = {
    "boundaries": os.path.join(ROOT, "data", "boundaries"),
    "raw":        os.path.join(ROOT, "data", "raw"),
}
SOURCES = {
    # ใส่ได้หลาย URL (ลองไล่ตามลำดับ) — ตอนนี้มีตัวเดียวเพราะยังไม่มี mirror ที่ยืนยันแล้ว
    # geodata.ucdavis.edu ล่มเป็นช่วง ๆ : พึ่ง retry + cache แทน (โหลดสำเร็จครั้งเดียวก็พอ)
    "gadm": (["https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_THA.gpkg"],
             os.path.join(DIRS["boundaries"], "gadm41_THA.gpkg")),
    "osm":  ("https://download.geofabrik.de/asia/thailand-latest.osm.pbf",
             os.path.join(DIRS["raw"], "thailand-latest.osm.pbf")),
    "pop":  ("https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/THA/tha_ppp_2020_constrained.tif",
             os.path.join(DIRS["raw"], "tha_pop_2020_100m.tif")),
    # AADT ปริมาณจราจรบนทางหลวง ปี 2565 (กรมทางหลวง / data.go.th) — แยกชนิดรถ + จังหวัด + สาย/กม.
    "aadt": ("https://data.go.th/dataset/0ed9305b-0752-4189-bd89-0dfa96e6f992/resource/6cfd40db-807d-4169-9b0d-879bd94b88e3/download/65.csv",
             os.path.join(ROOT, "inputs", "calibration", "aadt_2565.csv")),
    # ---- เป้า calibration (สถิติทางการ, เข้าถึง 2026-07-02) ----
    # ปริมาณการขนส่งสินค้าภายในประเทศ จำแนกตามรูปแบบ 2560-2565 (สนข./กระทรวงคมนาคม)
    "target_freight": ("https://otp.gdcatalog.go.th/dataset/8d7f86ef-a6e2-4dcd-b227-02b87fedce0c/resource/8f792f68-d194-479d-9f95-ccfbc934dbe8/download/dataset_12_03-2560-2565.csv",
             os.path.join(ROOT, "inputs", "calibration", "targets", "freight_by_mode_2560_2565.csv")),
    # ปริมาณผู้โดยสารขนส่งสาธารณะภายในประเทศ รายโหมด (กระทรวงคมนาคม)
    "target_pax": ("https://datagov.mot.go.th/dataset/8a3b54cd-791e-461f-b3ec-50581c92ab52/resource/e0a4e2c5-17ad-4f09-a6e2-619f20587a85/download/domestic-passenger.csv",
             os.path.join(ROOT, "inputs", "calibration", "targets", "passenger_domestic_by_mode.csv")),
    # สัดส่วนการเดินทางระหว่างเมืองรายโหมด (สนข. แบบจำลอง NAM ปีฐาน 2560 + รฟท./ทอท./กทย.)
    "target_intercity": ("https://otp.gdcatalog.go.th/dataset/12eb6ec3-659a-42d0-b5e4-b94e9ab660f4/resource/af3886c8-eafa-430a-aaed-1af32f2c1eb1/download/otp_65_03.csv",
             os.path.join(ROOT, "inputs", "calibration", "targets", "intercity_pt_share_otp6503.csv")),
}

# แหล่งข้อมูลเป็นเซิร์ฟเวอร์สาธารณะที่ล่ม/ช้าเป็นครั้งคราว ถ้าปล่อยให้ล้มทันที
# การรันทั้งไปป์ไลน์ (40 นาที+) จะจบตั้งแต่นาทีที่ 2 เพราะเน็ตสะดุดครั้งเดียว
RETRIES = 4
BACKOFF = [5, 15, 45]      # วินาที ก่อนลองใหม่ครั้งที่ 2/3/4
socket.setdefaulttimeout(60)


def urls_for(key):
    """URL ของแหล่ง key โดยให้ตัวที่ตั้งผ่าน env TT_URL_<KEY> มาก่อนเสมอ

    ใช้เมื่อแหล่งต้นทางล่มยาว: อัปไฟล์ขึ้นที่เก็บของตัวเอง (เช่น GitHub Release)
    แล้วตั้งตัวแปรไว้ ไม่ต้องแก้โค้ด — ดู docs/DATA_SOURCES.md
    """
    u = SOURCES[key][0]
    urls = [u] if isinstance(u, str) else list(u)
    override = (os.environ.get("TT_URL_" + key.upper()) or "").strip()
    if override:
        urls.insert(0, override)
        log(f"  ใช้ URL ที่ตั้งไว้ผ่าน TT_URL_{key.upper()}: {override}")
    return urls


def dl(url, dst, retries=RETRIES):
    """url เป็น str หรือ list ของ URL สำรอง — ลองไล่จนกว่าจะได้"""
    urls = [url] if isinstance(url, str) else list(url)
    errs = []
    for i, u in enumerate(urls):
        try:
            return _dl_one(u, dst, retries)
        except Exception as e:
            errs.append((u, f"{type(e).__name__}: {e}"))
            if i + 1 < len(urls):
                log(f"  เปลี่ยนไปใช้แหล่งสำรอง: {urls[i+1]}")
    raise DownloadFailed(errs)


class DownloadFailed(Exception):
    """เก็บ error แยกตาม URL เพื่อให้สรุปท้ายบอกได้ว่าตัวไหนพังเพราะอะไร"""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(f"{u} -> {e}" for u, e in errors))


def _dl_one(url, dst, retries=RETRIES):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    for attempt in range(1, retries + 1):
        t0 = time.time(); last = [0]
        def hook(b, bs, total):
            done = b * bs
            if total > 0 and done - last[0] > 10 * 1048576:
                last[0] = done
                print(f"  {done/1048576:6.1f}/{total/1048576:.1f} MB  ({done*100/total:4.1f}%)  {done/1048576/(time.time()-t0+1e-9):.1f} MB/s", flush=True)
        log(f"downloading {url}" + (f" (ครั้งที่ {attempt}/{retries})" if attempt > 1 else ""))
        try:
            urllib.request.urlretrieve(url, tmp, hook)
            os.replace(tmp, dst)
            log(f"DONE -> {dst}  ({os.path.getsize(dst)/1048576:.1f} MB)")
            return
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            if attempt == retries:
                log(f"FAILED after {retries} attempts: {url}\n  {type(e).__name__}: {e}")
                raise
            wait = BACKOFF[min(attempt - 1, len(BACKOFF) - 1)]
            log(f"  ผิดพลาด ({type(e).__name__}: {e}) — รอ {wait}s แล้วลองใหม่")
            time.sleep(wait)

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    keys = ["gadm", "osm", "pop", "aadt", "target_freight", "target_pax", "target_intercity"] if what == "all" else [what]
    # ไม่หยุดที่แหล่งแรกที่ล้ม — ลองให้ครบทุกแหล่งก่อน แล้วสรุปทีเดียวว่าแหล่งไหนใช้ไม่ได้
    # (แหล่งเป็นเซิร์ฟเวอร์สาธารณะคนละเจ้า ล่มทีละเจ้าได้)
    status = []
    for k in keys:
        url, dst = SOURCES[k]
        if os.path.exists(dst):
            log(f"skip {k}: exists ({os.path.getsize(dst)/1048576:.1f} MB)")
            status.append((k, "cached", ""))
            continue
        try:
            dl(urls_for(k), dst)
            status.append((k, "ok", ""))
        except DownloadFailed as e:
            status.append((k, "FAILED", e.errors))
        except Exception as e:
            status.append((k, "FAILED", [(str(SOURCES[k][0]), f"{type(e).__name__}: {e}")]))

    log("")
    log("== สรุปแหล่งข้อมูล ==")
    for k, st, info in status:
        log(f"  {k:16s} {st}")
        if st == "FAILED":
            for u, err in info:
                log(f"    {u}\n      -> {err}")
    bad = [k for k, st, _ in status if st == "FAILED"]
    if bad:
        log(f"ดาวน์โหลดไม่สำเร็จ {len(bad)} แหล่ง: {', '.join(bad)}")
        sys.exit(1)
    log("DONE")
