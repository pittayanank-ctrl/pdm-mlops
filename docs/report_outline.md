# โครงรายงาน + ผู้เขียนแต่ละส่วน

(ผู้รวบรวม: คนที่ 8) ทุกส่วนต้องมีหลักฐาน (ภาพหน้าจอ, ไฟล์ report, ลิงก์ CI run) เก็บไว้ใน `docs/evidence/`

| # | หัวข้อ | ผู้เขียน | หลักฐานที่ต้องแนบ |
|---|---|---|---|
| 1 | ปัญหา, ผู้ใช้, คุณค่า, ทำไมใช้ ML, AI Project Canvas | 8 | `docs/ai_project_canvas.md` |
| 2 | Optimizing / Gating metric และตัวชี้วัดธุรกิจ | 3 + 8 | ตาราง cost, threshold |
| 3 | ข้อมูล, การแบ่งตามเวลา, data version, ข้อจำกัดของข้อมูลสังเคราะห์ | 2 | จำนวนแถวต่อชุด, positive rate |
| 4 | Schema, การตรวจข้อมูลเสีย, การจัดการค่าหายและ outlier | 4 | report FAIL 7 กรณี, log ที่ pipeline หยุด |
| 5 | Feature engineering + กลไกกัน Training-Serving Skew | 3 | `tests/test_skew.py` ผ่าน |
| 6 | Baseline + การทดลอง ≥ 3 รอบ + เหตุผลเลือกโมเดล + การอธิบายผล | 3 | MLflow compare, PR curve, feature importance |
| 7 | Experiment tracking 6 อย่าง + Model Registry + gate + rollback | 5 | ภาพ MLflow run, registry ที่มี champion/rejected/rolled_back |
| 8 | การให้บริการ: API, real-time vs batch, workers, SLO, latency p50/p95, throughput | 6 | `reports/slo/latest.json` ที่ concurrency 1/4/8 |
| 9 | Monitoring: metric ระบบ, คุณภาพการทำนาย, data vs concept drift, เกณฑ์แจ้งเตือน, นโยบายเทรนใหม่ | 7 | Grafana, `reports/monitoring/*.html`, วงจรเทรนใหม่ |
| 10 | CI/CD 3 ด้าน (ผ่านและไม่ผ่าน) | 8 | ลิงก์ GitHub Actions ทั้ง 2 แบบ |
| 11 | Pipeline DAG, การรันจากเครื่องเปล่า, Git workflow | 1 | Prefect UI, ภาพ PR ที่ merge |
| 12 | แผนภาพสถาปัตยกรรม | 1 | `docs/architecture.md` |
| 13 | เหตุผลที่เลือกเครื่องมือแต่ละตัว | ทุกคน (เขียนส่วนที่ตัวเองดูแล) | ตาราง 9 หน้าที่ |
| 14 | การใช้เครื่องมือ AI | ทุกคน | ตารางด้านล่าง |
| 15 | สัดส่วนงานของสมาชิก | 1 | ลิงก์ contributors / PR ของแต่ละคน |

## เหตุผลที่เลือกเครื่องมือ (ร่าง ให้แต่ละคนแก้ให้ตรงกับเหตุผลของกลุ่ม)

| หน้าที่ | เครื่องมือ | เหตุผล |
|---|---|---|
| Version Control | GitHub | ใช้ PR + review + Actions ได้ในที่เดียว |
| Containerization | Docker + compose | รันทั้ง 6 service ด้วยคำสั่งเดียวจากเครื่องเปล่า |
| Data Validation | Pandera | schema เขียนเป็นโค้ด Python ตรวจ DataFrame ได้ตรงๆ เบากว่า Great Expectations |
| Experiment Tracking | MLflow Tracking | ฟรี, self-host, เปรียบเทียบ run ได้ |
| Model Registry | MLflow Registry (alias + tag) | อยู่ที่เดียวกับ tracking, alias ทำให้ rollback ทำได้ด้วยคำสั่งเดียว |
| Orchestration | Prefect 3 | เขียน DAG เป็น Python ธรรมดา, มี UI, เบากว่า Airflow สำหรับทีมเล็ก |
| Serving | FastAPI | validate input ด้วย Pydantic, มี Swagger, เร็ว |
| Monitoring | PSI เขียนเอง + Prometheus + Grafana | ควบคุมเกณฑ์ได้เอง, Prometheus เป็นมาตรฐานของ metric ระบบ |
| CI/CD | GitHub Actions | ผูกกับ PR โดยตรง |

## การใช้เครื่องมือ AI (บังคับตามเอกสารรายวิชา)

ทุกคนต้องเติมแถวของตัวเองตามจริง และต้องอธิบายโค้ดที่ส่งได้ทุกบรรทัด

| สมาชิก | เครื่องมือ AI | ใช้ช่วยส่วนไหน | สิ่งที่ตรวจสอบหรือแก้เอง |
|---|---|---|---|
| คนที่ 1 | | | |
| คนที่ 2 |Claude | โค้ดใน PR02, PR05 มาจากไฟล์ handoff ของทีม และใช้ Claude ช่วยอธิบายขั้นตอน git/PR, แก้ปัญหา .gitignore และ No module named 'pdm'| อ่านโค้ด ingest/labels/split/versioning, รัน pytest/ruff, รัน ingest แบบข้อมูลจำลอง และรัน pipeline บนข้อมูลจริง 2 ครั้งเพื่อยืนยันว่า data_version ตรงกัน |
| คนที่ 3 | | | |
| คนที่ 4 | | | |
| คนที่ 5 | | | |
| คนที่ 6 | | | |
| คนที่ 7 | | | |
| คนที่ 8 | | | |
