# -*- coding: utf-8 -*-
"""ขั้น 17: สร้างเว็บแสดงผล (site/) สำหรับ GitHub Pages

  python3 scripts/17_build_site.py

อ่านจาก output/report/{tables,figures} + model/5_calibration แล้วเขียน:
  site/index.html          หน้าเดียวจบ (ตาราง + แผนที่ + scenario + สถานะ)
  site/figures/*.png       รูปแผนที่
  site/tables/*.csv        ไฟล์ CSV ให้ดาวน์โหลด

ไม่ใช้ QGIS/numpy และไม่เรียกทรัพยากรภายนอก (ไม่มี CDN) — สร้างได้เสมอแม้ผลยังไม่ครบ
"""
import html
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.paths import SITE, REPORT, ensure       # noqa: E402
from lib import report_data as rd                # noqa: E402

MAX_ROWS = 200          # แถวสูงสุดต่อหนึ่งตารางบนหน้าเว็บ (ที่เหลือให้โหลด CSV)

CSS = """
:root{--bg:#f7f8fa;--fg:#1b1f24;--muted:#5c6672;--card:#fff;--line:#e2e6eb;--accent:#0b6bcb;--ok:#1a7f4b;--warn:#b26a00}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--fg:#e6e9ee;--muted:#9aa4b2;--card:#171b21;--line:#2a3038;--accent:#5aa9ff;--ok:#4cc38a;--warn:#e0a33e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:"Noto Sans Thai","Sarabun",system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif;line-height:1.6}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
header h1{margin:0 0 4px;font-size:1.6rem}
header p{margin:0;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:18px 0}
h2{font-size:1.15rem;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:1rem;margin:18px 0 8px}
.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.meta div{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.meta b{display:block;color:var(--muted);font-weight:600;font-size:.8rem}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.9rem;min-width:480px}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left;white-space:nowrap}
th{background:var(--bg);position:sticky;top:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.grid figure{margin:0}
.grid img{width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
.grid figcaption{color:var(--muted);font-size:.85rem;margin-top:6px}
a{color:var(--accent)}
.pill{display:inline-block;font-size:.8rem;padding:1px 8px;border-radius:999px;border:1px solid var(--line)}
.ok{color:var(--ok)}.warn{color:var(--warn)}
.note{color:var(--muted);font-size:.88rem}
details summary{cursor:pointer;color:var(--accent)}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;font-size:.82rem}
footer{color:var(--muted);font-size:.85rem;text-align:center;margin-top:28px}
"""


def esc(x):
    return html.escape(str(x))


def is_num(s):
    try:
        float(str(s).replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False


def html_table(rows, limit=MAX_ROWS):
    if not rows:
        return '<p class="note">ยังไม่มีข้อมูล</p>'
    head, body = rows[0], rows[1:]
    shown, extra = body[:limit], max(len(body) - limit, 0)
    out = ['<div class="scroll"><table><thead><tr>']
    out += ["<th>%s</th>" % esc(c) for c in head]
    out.append("</tr></thead><tbody>")
    for r in shown:
        out.append("<tr>" + "".join(
            '<td class="num">%s</td>' % esc(c) if is_num(c) else "<td>%s</td>" % esc(c)
            for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    if extra:
        out.append('<p class="note">แสดง %d จาก %d แถว — ดูครบทั้งหมดได้จากไฟล์ CSV</p>'
                   % (len(shown), len(body)))
    return "".join(out)


def build():
    ensure(SITE, SITE + r"\figures", SITE + r"\tables")

    # ── คัดลอกไฟล์ผลลัพธ์เข้าไซต์ ──
    figs = rd.figures()
    for fn, _ in figs:
        shutil.copy2(os.path.join(str(REPORT) + os.sep + "figures", fn),
                     os.path.join(str(SITE) + os.sep + "figures", fn))
    tabs = rd.tables()
    for fn, _, _ in tabs:
        shutil.copy2(os.path.join(str(REPORT) + os.sep + "tables", fn),
                     os.path.join(str(SITE) + os.sep + "tables", fn))

    meta = rd.run_meta()
    p = ['<!doctype html><html lang="th"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         "<title>ผลแบบจำลองขนส่งไทย</title><style>%s</style></head><body><div class=\"wrap\">" % CSS,
         "<header><h1>แบบจำลองการขนส่งประเทศไทย — ผลลัพธ์</h1>",
         '<p>แบบจำลอง 4 ขั้น ระดับอำเภอ (928 พื้นที่) หลายรูปแบบการขนส่ง — สร้างอัตโนมัติจาก GitHub Actions</p></header>']

    # ── ข้อมูลรอบการรัน ──
    p.append('<section class="card"><h2>ข้อมูลรอบการรัน</h2><div class="meta">')
    for k, v in meta.items():
        p.append("<div><b>%s</b>%s</div>" % (esc(k), esc(v)))
    p.append("</div></section>")

    # ── สถานะผลลัพธ์ ──
    p.append('<section class="card"><h2>สถานะผลลัพธ์แต่ละขั้น</h2><div class="scroll"><table><thead>'
             "<tr><th>ขั้น</th><th>ไฟล์</th><th>สถานะ</th></tr></thead><tbody>")
    for stage, rel, ok in rd.status():
        p.append("<tr><td>%s</td><td><code>%s</code></td><td class=\"%s\">%s</td></tr>"
                 % (esc(stage), esc(rel), "ok" if ok else "warn", "มี" if ok else "ยังไม่มี"))
    p.append("</tbody></table></div></section>")

    # ── scenario ที่ใช้ (INPUT) ──
    sv = rd.scenario_values()
    if sv:
        p.append('<section class="card"><h2>ข้อมูลนำเข้า: scenario</h2>'
                 '<p class="note">แก้ค่าที่ <code>inputs/scenarios/%s.yaml</code> แล้ว commit '
                 "เพื่อให้รันใหม่และอัปเดตหน้านี้อัตโนมัติ</p>" % esc(meta.get("scenario", "base")))
        p.append(html_table([["หมวด", "พารามิเตอร์", "ค่า"]] + [list(map(str, r)) for r in sv], limit=999))
        p.append("</section>")

    # ── คุณภาพการ calibrate ──
    fit = rd.calibration_fit()
    rep = rd.calibration_report_text()
    if fit or rep:
        p.append('<section class="card"><h2>คุณภาพการ calibrate</h2>')
        if fit:
            p.append(html_table(fit))
        if rep:
            p.append("<details><summary>ดูรายงาน calibration ฉบับเต็ม</summary><pre>%s</pre></details>"
                     % esc(rep))
        p.append("</section>")

    # ── ตาราง ──
    p.append('<section class="card"><h2>ตารางผลลัพธ์</h2>')
    if not tabs:
        p.append('<p class="note">ยังไม่มีตาราง — รัน <code>scripts/15_report_outputs.py</code> ก่อน</p>')
    for fn, title, n in tabs:
        p.append('<h3>%s <span class="pill">%d แถว</span> '
                 '<a href="tables/%s" download>ดาวน์โหลด CSV</a></h3>' % (esc(title), n, esc(fn)))
        p.append(html_table(rd.read_table(fn)))
    p.append("</section>")

    # ── รูปแผนที่ ──
    p.append('<section class="card"><h2>แผนที่ผลลัพธ์</h2>')
    if not figs:
        p.append('<p class="note">ยังไม่มีรูป — รัน <code>scripts/15_report_outputs.py</code> ก่อน</p>')
    else:
        p.append('<div class="grid">')
        for fn, title in figs:
            p.append('<figure><a href="figures/%s" target="_blank" rel="noopener">'
                     '<img src="figures/%s" alt="%s" loading="lazy"></a>'
                     "<figcaption>%s — คลิกเพื่อดูขนาดเต็ม</figcaption></figure>"
                     % (esc(fn), esc(fn), esc(title), esc(title)))
        p.append("</div>")
    p.append("</section>")

    p.append('<footer>สร้างโดย <code>scripts/17_build_site.py</code> — '
             "ข้อมูลนำเข้าอยู่ใน <code>inputs/</code>, กระบวนการอยู่ใน <code>scripts/</code></footer>")
    p.append("</div></body></html>")

    out = os.path.join(str(SITE), "index.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("".join(p))
    print("wrote %s (%d ตาราง, %d รูป)" % (out, len(tabs), len(figs)))
    return 0


if __name__ == "__main__":
    sys.exit(build())
