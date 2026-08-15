# -*- coding: utf-8 -*-
"""paths — รากโปรเจกต์ + การต่อ path ที่ทำงานได้ทั้ง Windows และ Linux (GitHub Actions)

ปัญหาเดิม: ทุกสคริปต์ hardcode `B = r"C:\\Users\\...\\02_thailand_transport"` แล้วต่อ path
ด้วย backslash เช่น `B + r"\\data\\network\\network_clean.gpkg"` -> รันบน Linux ไม่ได้

วิธีแก้: ROOT เป็น str ชนิดพิเศษที่แปลง "\\" เป็น os.sep ให้อัตโนมัติตอนต่อสตริง
จึงไม่ต้องแก้ literal path หลายร้อยจุดในสคริปต์เดิม และบน Windows (os.sep == "\\")
พฤติกรรมเหมือนเดิมทุกประการ

ลำดับการหา ROOT:
  1) ตัวแปรสภาพแวดล้อม TT_ROOT (ใช้ใน GitHub Actions: TT_ROOT=${{ github.workspace }})
  2) เดินขึ้นจากไฟล์นี้จนเจอโฟลเดอร์ที่มีทั้ง config/ และ scripts/
"""
import os


class ProjPath(str):
    """str ที่ต่อ path แบบข้ามแพลตฟอร์ม: ProjPath("/a") + r"\\b\\c" -> "/a/b/c" """

    def __add__(self, other):
        return ProjPath(str(self) + str(other).replace("\\", os.sep))

    def __truediv__(self, other):          # ทางเลือกที่อ่านง่ายกว่าสำหรับโค้ดใหม่
        return ProjPath(os.path.join(str(self), str(other).replace("\\", os.sep)))


def _discover_root():
    env = os.environ.get("TT_ROOT")
    if env:
        return os.path.abspath(env)
    d = os.path.dirname(os.path.abspath(__file__))
    while d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, "config")) and os.path.isdir(os.path.join(d, "scripts")):
            return d
        d = os.path.dirname(d)
    # fallback: scripts/lib/paths.py -> ขึ้นสองชั้น
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ROOT = ProjPath(_discover_root())

# QGIS ลาก Qt มาด้วยเสมอ ถ้าไม่มีจอ (เซิร์ฟเวอร์/Actions/Colab) Qt จะพยายามต่อ "xcb"
# แล้ว abort ทั้งโปรเซส — บังคับโหมด offscreen ให้ตั้งแต่ก่อนสร้าง QgsApplication
# (บน Windows/เครื่องที่มี DISPLAY ไม่แตะ เพื่อให้ qpy.bat ทำงานเหมือนเดิม)
if os.name != "nt" and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# โฟลเดอร์มาตรฐานตามสัญญา Input -> Process -> Output (ดู docs/PIPELINE_IO.md)
INPUTS  = ROOT + r"\inputs"          # ข้อมูลนำเข้าที่คนแก้ + commit
CONFIG  = ROOT + r"\config"          # พารามิเตอร์ระดับโค้ด
SCRIPTS = ROOT + r"\scripts"         # กระบวนการ
DATA    = ROOT + r"\data"            # ข้อมูลที่ดาวน์โหลด/สร้างเอง (gitignored)
MODEL   = ROOT + r"\model"           # ผลระหว่างทาง (gitignored)
OUTPUT  = ROOT + r"\output"          # ผลลัพธ์
REPORT  = OUTPUT + r"\report"
SITE    = ROOT + r"\site"            # เว็บผลลัพธ์ (GitHub Pages)


def hard_exit(code=0):
    """จบโปรเซสทันทีโดยไม่เรียก destructor ของ Qt/GDAL

    บน Linux/คอนเทนเนอร์ การปิด QgsApplication หลังใช้ processing มักทำให้เกิด
    segmentation fault "หลังงานเสร็จแล้ว" (เขียนไฟล์ครบ) ซึ่งทำให้ CI มองว่าขั้นนั้นล้ม
    ใช้ฟังก์ชันนี้ปิดท้ายสคริปต์ที่ทำงานสำเร็จแล้ว เพื่อให้ exit code สื่อความจริง
    """
    import sys
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def ensure(*dirs):
    """สร้างโฟลเดอร์ถ้ายังไม่มี แล้วคืนค่าตัวแรก"""
    for d in dirs:
        os.makedirs(str(d), exist_ok=True)
    return dirs[0] if dirs else None


def ensure_parent(path):
    """สร้างโฟลเดอร์ที่จะเขียนไฟล์ลงไป แล้วคืน path เดิม

    model/ กับ output/ ถูก gitignore จึงไม่มีอยู่บนเครื่องที่ clone ใหม่ (เช่น CI)
    ถ้าไม่สร้างก่อน QgsVectorFileWriter จะเขียนไม่สำเร็จอย่างเงียบ ๆ
    """
    d = os.path.dirname(str(path))
    if d:
        os.makedirs(d, exist_ok=True)
    return path
