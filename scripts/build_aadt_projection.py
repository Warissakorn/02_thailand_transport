# -*- coding: utf-8 -*-
"""สร้าง AADT ปีปัจจุบันด้วยการประมาณจากแนวโน้มย้อนหลัง (2563-2566)
- อ่าน AADT 4 ปี (positional cols: 0=สาย 3=จุดสำรวจ 14=รวม ; 2563 = cp874)
- national trend: median + sum ของ 'รวม' รายปี + YoY growth (จับคู่สถานีเดียวกัน)
- เลือก growth ที่เหมาะ (เลี่ยงช่วงฟื้นโควิด) แล้ว project ฐานปีล่าสุด (2566) -> ปีเป้า
out (ขั้นแรกนี้แค่วิเคราะห์): log output/_aadt_trend.log
"""
import os, sys, csv, io, statistics, traceback
B = r"C:\Users\nutta\Desktop\Qgis\projects\02_thailand_transport"
H = B + r"\data\calibration\history"
LOG = open(B + r"\output\_aadt_trend.log", "w", encoding="utf-8")
def log(*a): LOG.write(" ".join(str(x) for x in a) + "\n"); LOG.flush()
YEARS = [2563, 2564, 2565, 2566]


def readyear(y):
    path = H + ("\\aadt_%d.csv" % y)
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp874"):
        try:
            txt = raw.decode(enc)
            if "ทางหลวงสาย" in txt.splitlines()[0] or "รวม" in txt.splitlines()[0]:
                break
        except Exception:
            continue
    else:
        txt = raw.decode("cp874", "replace")
    rows = list(csv.reader(io.StringIO(txt)))
    hdr = rows[0]
    d = {}
    for r in rows[1:]:
        if len(r) < 15:
            continue
        route = r[0].strip(); km = r[3].strip()
        tot = r[14].replace(",", "").strip()
        try:
            v = float(tot)
        except Exception:
            continue
        if v > 0:
            d[(route, km)] = v
    return d


def main():
    data = {y: readyear(y) for y in YEARS}
    for y in YEARS:
        vals = list(data[y].values())
        log("%d: stations=%d  sum=%.0f  median=%.0f  mean=%.0f" % (
            y, len(vals), sum(vals), statistics.median(vals), sum(vals)/len(vals)))

    log("\n--- YoY growth (matched stations, median ratio) ---")
    for a, b in zip(YEARS[:-1], YEARS[1:]):
        common = set(data[a]) & set(data[b])
        ratios = sorted(data[b][k]/data[a][k] for k in common if data[a][k] > 0)
        med = statistics.median(ratios)
        log("  %d->%d: matched=%d  median growth=%.4f (%.1f%%)" % (
            a, b, len(common), med, (med-1)*100))

    # แนวโน้มหลังฟื้นโควิด: ใช้ 2565->2566 เป็นตัวแทน growth ปกติ (เลี่ยงช่วงดิ่ง-ฟื้นโควิด 2563-2565)
    common = set(data[2565]) & set(data[2566])
    g = statistics.median(data[2566][k]/data[2565][k] for k in common if data[2565][k] > 0)
    log("\nchosen annual growth (2565->2566, post-covid) = %.4f (%.2f%%/yr)" % (g, (g-1)*100))
    for tgt in (2567, 2568, 2569):
        f = g ** (tgt - 2566)
        log("  project 2566 -> %d : factor=%.4f" % (tgt, f))

    # ---- เขียนไฟล์ AADT ปีปัจจุบัน (project ฐาน 2566 ด้วย factor สม่ำเสมอทั้งประเทศ) ----
    TARGET = 2569
    factor = g ** (TARGET - 2566)
    SCALE_COLS = list(range(4, 15)) + [17]   # คอลัมน์นับคัน: นั่ง/โดยสาร/บรรทุก/รวม + จยย. (ไม่แตะ %หนัก, จักรยาน)
    src = list(csv.reader(io.StringIO(open(H + r"\aadt_2566.csv", "rb").read().decode("utf-8-sig"))))
    out = B + r"\data\calibration\aadt_current.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(src[0])
        n = 0
        for r in src[1:]:
            if len(r) < 20:
                w.writerow(r); continue
            rr = list(r)
            for i in SCALE_COLS:
                try:
                    rr[i] = str(int(round(float(r[i].replace(",", "")) * factor)))
                except Exception:
                    pass
            w.writerow(rr); n += 1
    log("\nWROTE %s : project 2566 -> %d factor=%.4f rows=%d" % (out, TARGET, factor, n))
    log("DONE")


if __name__ == '__main__':
    try: main()
    except Exception: log("ERR", traceback.format_exc())
