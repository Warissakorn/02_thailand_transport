# การป้องกัน branch `main` และกฎของรีโป

เอกสารนี้อธิบายกฎที่ตั้งไว้กับ `main`, วิธีเปิดใช้ (ทำครั้งเดียวจากหน้าเว็บ GitHub)
และวิธีทำงานกับกฎเหล่านี้ในชีวิตประจำวัน

> การตั้งค่านี้ **ต้องทำจาก UI ของ GitHub โดยเจ้าของรีโป** — เป็นสิทธิ์ระดับ admin
> ที่เครื่องมือในเซสชันนี้เข้าไม่ถึง ไฟล์ [`.github/rulesets/main-protection.json`](../.github/rulesets/main-protection.json)
> เตรียมไว้ให้กด import ได้เลย ไม่ต้องติ๊กทีละข้อ

## 1. กฎที่ตั้ง (ระดับ "กลาง")

| กฎ | ผล | เหตุผล |
|---|---|---|
| Restrict deletions | ลบ `main` ไม่ได้ | กันอุบัติเหตุที่กู้ยาก |
| Block force pushes | `git push --force` เข้า `main` ไม่ได้ | ประวัติของ `main` เขียนทับไม่ได้ |
| Require a pull request before merging | push ตรงเข้า `main` ไม่ได้ ต้องผ่าน PR | ทุกการเปลี่ยนแปลงมีที่ให้ดู diff และมีที่ให้ CI รัน |
| — approvals ที่ต้องการ: **0** | เจ้าของ merge PR ของตัวเองได้ | รีโปนี้ทำคนเดียว ถ้าเพิ่มคนค่อยปรับเป็น 1 |
| Require status checks to pass → **`validate`** | PR ที่ CI ไม่เขียว merge ไม่ได้ | กันของพังเข้า `main` |
| — Require branches to be up to date | ต้อง merge `main` ล่าสุดเข้ามาก่อน | ผลของ CI ตรงกับสิ่งที่จะได้หลัง merge จริง |
| Bypass: **Repository admin** | เจ้าของข้ามกฎได้เมื่อจำเป็น | ไม่ให้ตัวเองล็อกตัวเองออก (เช่นต้องแก้ด่วน) |

`validate` คือ job ใน [`.github/workflows/validate.yml`](../.github/workflows/validate.yml) ใช้เวลา ~1 นาที
(ไพป์ไลน์เต็มใช้ 40+ นาที จึงไม่เหมาะเป็นเงื่อนไข merge) ตรวจให้ว่า:

1. ทุกสคริปต์ใน `scripts/` และ `config/` compile ผ่าน
2. `scripts/_check_inputs.py` — ไฟล์นำเข้าครบ, scenario ทุกไฟล์อ่านได้, **ทุก key สะกดถูกและอยู่ในช่วงที่สมเหตุสมผล**
3. `scripts/17_build_site.py` ยังสร้างหน้าเว็บผลลัพธ์ได้
4. `lib.paths` / `lib.scenario` import ได้

ข้อ 2 มีค่าเป็นพิเศษ: key ที่พิมพ์ผิดใน scenario จะถูกข้ามเงียบ ๆ ตอนรันจริง
กว่าจะรู้ก็เสียเวลาไปแล้ว 40 นาที — ตัวตรวจนี้จับให้ตั้งแต่ตอนเปิด PR

## 2. วิธีเปิดใช้ (ครั้งเดียว, ~2 นาที)

**แบบ import ไฟล์ (แนะนำ)**

1. ไปที่ **Settings → Rules → Rulesets → New ruleset → Import a ruleset**
2. เลือกไฟล์ `.github/rulesets/main-protection.json` จากเครื่อง
   (ถ้ายังไม่มีในเครื่อง กดดาวน์โหลดจากหน้ารีโปได้)
3. ตรวจว่า **Enforcement status = Active** แล้วกด **Create**

**แบบตั้งเอง** — Settings → Rules → Rulesets → New branch ruleset:
ตั้งชื่อ `protect-main`, Target branches = **Default branch**, แล้วติ๊ก
Restrict deletions · Block force pushes · Require a pull request before merging (approvals = 0) ·
Require status checks to pass (เพิ่ม `validate`, ติ๊ก Require branches to be up to date)
และเพิ่ม Bypass list = **Repository admin**

> ต้องมี PR ที่รัน `validate` อย่างน้อยหนึ่งครั้งก่อน ชื่อ check ถึงจะขึ้นมาให้เลือกในช่องค้นหา
> ถ้ายังไม่ขึ้น พิมพ์ `validate` ลงไปตรง ๆ ได้เลย

## 3. เปิด GitHub Pages (ครั้งเดียวเช่นกัน)

**Settings → Pages → Source: GitHub Actions** — หลังจากนั้นทุกครั้งที่ไพป์ไลน์รันจบบน `main`
หน้าเว็บผลลัพธ์จะอัปเดตอัตโนมัติ

## 4. วิธีทำงานหลังเปิดกฎ

```bash
git checkout main && git pull
git checkout -b <ชื่อ-branch>       # เช่น update-aadt-2567
# แก้ไฟล์ใน inputs/ ...
python3 scripts/_check_inputs.py   # ตรวจก่อน push ได้ทันที ไม่ต้องรอ CI
git commit -am "อัปเดต AADT ปี 2567" && git push -u origin <ชื่อ-branch>
```
เปิด PR → รอ `validate` เขียว → merge → ไพป์ไลน์เต็มจะเริ่มเองเพราะ `inputs/` เปลี่ยน
(ดู [`PIPELINE_IO.md`](PIPELINE_IO.md) §5)

**ถ้า `validate` แดง** ให้ดูที่ step ที่แดง: ส่วนใหญ่จะเป็นข้อความจาก `_check_inputs.py`
ที่บอกชื่อไฟล์และ key ที่ผิดตรง ๆ

**ถ้าต้องแก้ด่วนบน `main` จริง ๆ** — เจ้าของรีโปอยู่ใน bypass list จึง push ตรงได้
แต่ควรใช้เฉพาะกรณีฉุกเฉิน เพราะจะข้ามการตรวจทั้งหมด

## 5. ถ้ามีคนร่วมทีมเพิ่ม

ปรับสองจุดในกฎ: ตั้ง `required_approving_review_count` เป็น `1`
และเปิด `dismiss_stale_reviews_on_push` — หลังจากนั้น PR ต้องมีคนอื่น approve ก่อน merge
