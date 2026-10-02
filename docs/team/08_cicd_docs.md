# คนที่ 8: CI/CD + QA + เอกสาร

ดูแล CI/CD ที่ตรวจ 3 ด้าน (คุณภาพโค้ด, ความถูกต้องของข้อมูล, เกณฑ์คุณภาพโมเดล) พร้อมหลักฐานทั้งครั้งที่ผ่านและไม่ผ่าน (ส่วนที่ 6) รวมถึง AI Project Canvas (ส่วนที่ 1) และการรวมรายงาน (ส่วนที่ 8)

## PR ของคุณ

| PR | branch | ไฟล์ |
|---|---|---|
| #8 | `ci/quality-and-data-checks` | `.github/workflows/ci.yml`: ใส่เฉพาะ `env` + job `code-quality` + `data-validation` (ลบ 2 job หลังออกก่อน) |
| #22 | `ci/model-gate-and-docker` | `.github/workflows/ci.yml`: เพิ่ม job `model-quality` + `docker-build` |
| #23 | `docs/readme-canvas-report` | `README.md` `docs/ai_project_canvas.md` `docs/report_outline.md` `docs/report.md` |
| #30 | 3 PR ที่ตั้งใจให้ CI ไม่ผ่าน (**ไม่ merge**) | ดูหัวข้อถัดไป |
| #31 | `docs/screenshots-ci` | ภาพหน้า Actions ทั้งตอนผ่านและไม่ผ่าน |

## หลักฐาน CI ไม่ผ่าน (ต้องมีครบ 3 ด้าน)

เปิด PR แยกกันจาก `main` เก็บภาพหน้าจอแล้วปิด PR โดยไม่ merge:

| branch | สิ่งที่แก้ | job ที่ต้องพัง |
|---|---|---|
| `test/ci-must-fail-code` | เพิ่ม import ที่ไม่ได้ใช้ หรือทำให้ test assert ผิด | `code-quality` |
| `test/ci-must-fail-data` | ใน `schema.py` เปลี่ยน `HARD_BOUNDS["vibration"]` เป็น `(0.0, 20.0)` | `data-validation` (ข้อมูลปกติไม่ผ่าน schema) |
| `test/ci-must-fail-model` | ใน `configs/params.yaml` เปลี่ยน `gate.min_recall` เป็น `0.999` | `model-quality` (gate reject แล้ว exit 1) |

## ต้องเข้าใจ

**`ci.yml` มี 4 job:**

| job | สิ่งที่ตรวจ |
|---|---|
| `code-quality` | ruff lint + format + pytest (test ทั้งหมด รวม skew test) |
| `data-validation` | สร้างข้อมูล → ข้อมูลปกติต้องผ่าน → ข้อมูลเสีย 7 แบบต้องไม่ผ่านทุกแบบ (ถ้ามีแบบไหนผ่าน job จะพัง) |
| `model-quality` | รัน training flow เต็ม ถ้า gate reject จะ exit 1 พร้อมเขียนตารางผล gate ลง Job Summary |
| `docker-build` | build image ได้ (ส่วน CD) |

- CI ใช้ข้อมูลสังเคราะห์ (`params.ci.yaml`) เพื่อให้รันเสร็จในไม่กี่นาที
- `requirements.lock` ใช้เป็น constraints เพื่อให้เวอร์ชันไลบรารีเหมือนเดิมทุกครั้ง

## วิธีทดสอบ

```bash
ruff check src tests && ruff format --check src tests && pytest
```

จากนั้น push branch แล้วดูผลในแท็บ Actions ของ GitHub

## งานเอกสาร

- **README:** ต้องทดสอบตามทีละบรรทัดบนเครื่องที่ไม่เคยรันโปรเจกต์มาก่อน
- **Canvas:** เติมตัวเลขผลจริงหลังรันบนข้อมูล Azure
- **รายงาน:** ตาม [report_outline.md](../report_outline.md) ตามงานจากแต่ละคน และรวมตาราง "การใช้เครื่องมือ AI" ให้ครบ

## คำถามที่ต้องตอบได้

1. **CI ตรวจอะไรบ้าง และทำไมแยก job?** 3 ด้านตามเอกสาร แยก job เพื่อให้รู้ทันทีว่าพังด้านไหน และ job หลังรอ job แรกผ่านก่อน (`needs`)
2. **ทำไม CI ใช้ข้อมูลสังเคราะห์?** เร็ว ไม่ต้องดาวน์โหลด และ schema เดียวกับข้อมูลจริง ทำให้ทดสอบโค้ดเส้นทางเดียวกันได้
3. **CI กับ CD ในโปรเจกต์นี้คืออะไร?**
   - CI คือ 3 job แรก
   - CD คือ build image ที่ docker compose ใช้
   - ส่วนการ deploy โมเดลเกิดผ่าน registry: gate ผ่านแล้ว alias ย้าย API จึงโหลดโมเดลใหม่เอง
