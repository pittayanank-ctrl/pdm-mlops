# คนที่ 1: Tech Lead / Pipeline

ดูแลให้ทั้งระบบรันต่อเนื่องตั้งแต่ข้อมูลดิบจนถึงการให้บริการ ด้วยคำสั่งเดียว (ส่วนที่ 7 ของเกณฑ์) พร้อมแผนภาพสถาปัตยกรรม (ส่วนที่ 8)

## PR ของคุณ

| PR | branch | ไฟล์ |
|---|---|---|
| #1 | `chore/repo-skeleton` | `.gitignore` `.gitattributes` `pyproject.toml` `requirements*.txt` `requirements.lock` `configs/params.yaml` `src/pdm/__init__.py` `src/pdm/config.py` `CONTRIBUTING.md` `.github/pull_request_template.md` `docs/team/` |
| #12 | `feat/prefect-training-flow` | `src/pdm/pipelines/__init__.py` `steps.py` `training_flow.py` |
| #18 | `feat/compose-makefile` | `docker-compose.yml` `Makefile` |
| #24 | `docs/architecture-demo` | `docs/architecture.md` `docs/demo_script.md` |
| #32 | - | code freeze + `git tag v1.0` |

**งานที่ไม่ใช่โค้ด:**
- หลัง merge PR #1 ให้ตั้ง branch protection ของ `main`: Settings → Branches → ต้องมี PR, review 1 คน และ status check ผ่าน
- review PR ของคนอื่นตามตาราง

## ต้องเข้าใจ

**`config.py`**
- ทุกค่าตั้ง (วันที่แบ่งข้อมูล, threshold, gate) อยู่ใน `params.yaml` ที่เดียว
- `PDM_CONFIG` ใช้สลับเป็นชุดข้อมูลสังเคราะห์ โดยเขียนทับเฉพาะ key ที่ระบุ (deep merge)

**`steps.py` กับ `training_flow.py`**
- logic อยู่ใน `steps.py` เป็นฟังก์ชันธรรมดา ส่วน Prefect เป็นแค่ตัวห่อเป็น task เพื่อให้ test ง่าย
- ลำดับ DAG: `ingest → validate → features → split → reference → train → evaluate → register → reload-api`
- ถ้า `validate` raise `DataValidationError` ทั้ง flow จะหยุด ขั้นตอนถัดไปไม่ทำงาน
- `cache_policy=NO_CACHE`: ไม่ให้ Prefect hash DataFrame ขนาดใหญ่
- `--fail-on-reject`: ใช้ใน CI ให้ exit 1 เมื่อโมเดลไม่ผ่าน gate

**`docker-compose.yml`**
- มี 6 service: mlflow, prefect, api, pipeline (profile `jobs`), prometheus, grafana
- `depends_on: service_healthy` ทำให้ API รอจน MLflow พร้อมก่อน
- `pipeline` ใช้รัน job ครั้งเดียวด้วย `docker compose run --rm pipeline ...`

**`Makefile`:** `make all` = เปิดทุก service แล้วรัน training flow

## วิธีทดสอบ

```bash
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml python -m pdm.pipelines.training_flow
make all          # ทั้งระบบผ่าน Docker
```

ทดสอบจากเครื่องเปล่าจริงอย่างน้อย 1 ครั้งก่อนวันที่ 5: clone ใหม่บนเครื่องเพื่อนที่ไม่เคยรัน แล้วทำตาม README

## หลักฐานที่ต้องเก็บ

- ภาพ Prefect UI ที่แสดง flow run สำเร็จ (เห็นทุก task)
- ภาพ flow run ที่หยุดตรง `validate` เมื่อใช้ข้อมูลเสีย
- ภาพหน้า Pull requests ของ repo ที่เห็นว่าทุกคนเปิดและ merge PR

## คำถามที่ต้องตอบได้

1. **ถ้า validate ไม่ผ่าน เกิดอะไรต่อ?** exception ถูก raise flow จึงหยุด, มีไฟล์ report และ alert, train ไม่ถูกเรียก
2. **รันซ้ำแล้วได้ผลเหมือนเดิมไหม?**
   - ข้อมูลเดิมได้ hash เดิม
   - split ใช้วันที่คงที่
   - seed คงที่
   - เวอร์ชันไลบรารีล็อกไว้
3. **ทำไมเลือก Prefect ไม่เลือก Airflow?** เขียนเป็น Python ธรรมดา, ไม่ต้องมี scheduler หรือ DB แยกตอนพัฒนา, มี UI, เบากว่าสำหรับทีมเล็ก
4. **คนอื่นรันจากเครื่องเปล่าได้อย่างไร?** มีแค่ Docker ก็พอ, `make all` หรือ 2 คำสั่งใน README, ไม่ต้องติดตั้ง Python
