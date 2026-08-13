# -*- coding: utf-8 -*-
"""ขั้น 16: สรุปผลการรันเป็น Markdown สำหรับหน้า Actions (GITHUB_STEP_SUMMARY)

พิมพ์ออก stdout อย่างเดียว -> ใน workflow ใช้:
    python3 scripts/16_summary.py >> "$GITHUB_STEP_SUMMARY"

ไม่ใช้ QGIS/numpy — รันได้ทุกที่ และต้อง "ไม่ล้ม" แม้ผลลัพธ์บางส่วนยังไม่มี
(ถ้าไฟล์ไหนขาด จะรายงานว่ายังไม่มีแทนการ error)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.paths import ROOT           # noqa: E402
from lib import report_data as rd    # noqa: E402


def table(rows, limit=None):
    """แปลง list-of-list เป็นตาราง Markdown"""
    if not rows:
        return "_(ไม่มีข้อมูล)_\n"
    head, body = rows[0], rows[1:]
    if limit:
        body = body[:limit]
    out = ["| " + " | ".join(str(c) for c in head) + " |",
           "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in body]
    return "\n".join(out) + "\n"


def main():
    meta = rd.run_meta()
    print("# ผลการรันแบบจำลองขนส่งไทย\n")
    print("| รายการ | ค่า |")
    print("|---|---|")
    for k, v in meta.items():
        print("| %s | %s |" % (k, v))
    print("")

    st = rd.status()
    print("## สถานะผลลัพธ์\n")
    print("| ขั้น | ไฟล์ผลลัพธ์ | สถานะ |")
    print("|---|---|---|")
    for stage, rel, ok in st:
        print("| %s | `%s` | %s |" % (stage, rel, "✅ มี" if ok else "⚠️ ยังไม่มี"))
    print("")

    fit = rd.calibration_fit()
    if fit:
        print("## คุณภาพการ calibrate\n")
        print(table(fit))

    t2 = rd.read_table("T2_mode_share_vs_target.csv")
    if t2:
        print("## สัดส่วนการเดินทางรายโหมด เทียบเป้าหมาย\n")
        print(table(t2))

    t5 = rd.read_table("T5_assignment_stats.csv")
    if t5:
        print("## สถิติการ assignment\n")
        print(table(t5))

    figs = rd.figures()
    if figs:
        print("## รูปแผนที่ที่สร้างได้ (%d รูป)\n" % len(figs))
        print("\n".join("- `%s`" % f[0] for f in figs) + "\n")

    print("> ดูผลแบบเต็ม (ตาราง + แผนที่) ได้ที่หน้าเว็บผลลัพธ์ GitHub Pages "
          "หรือดาวน์โหลด artifact `model-outputs` จากหน้ารันนี้\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:                       # summary ต้องไม่ทำให้ job ล้ม
        print("\n> ⚠️ สร้างสรุปไม่สำเร็จ: `%s`\n" % e)
        sys.exit(0)
