# ระบบทำนายเครื่องจักรเสียล่วงหน้า (Predictive Maintenance)

โครงงานรายวิชา CP413008 Machine Learning Engineering for Production

ระบบทำนายว่าเครื่องจักรแต่ละเครื่องจะเสียภายใน 24 ชั่วโมงข้างหน้าหรือไม่ จากข้อมูลเซนเซอร์รายชั่วโมง (volt, rotate, pressure, vibration), ประวัติ error และประวัติการซ่อม
ฝ่ายซ่อมบำรุงใช้ผลนี้วางแผนซ่อมก่อนเครื่องเสีย เพื่อลด downtime ที่ไม่ได้วางแผน

- **ข้อมูล:** Microsoft Azure Predictive Maintenance มี telemetry 876,100 แถว จาก 100 เครื่อง ตลอดปี 2015
  - ดาวน์โหลดอัตโนมัติตามลำดับ: แหล่งเดิมของ Microsoft ก่อน (ปิดไปแล้วในปี 2026) ถ้าไม่ได้ใช้สำเนาบน GitHub (`configs/params.yaml` → `data.base_urls`)
- **CI และเดโมแบบออฟไลน์:** ใช้ข้อมูลสังเคราะห์ schema เดียวกัน (`configs/params.ci.yaml`)

## รันจากเครื่องเปล่า

ต้องมี [Docker Desktop](https://www.docker.com/products/docker-desktop/) และ git

```bash
git clone <repo-url> pdm-mlops
cd pdm-mlops
make all
```

ถ้าไม่มี `make` (เช่นบน Windows) ใช้ 2 คำสั่งนี้แทน:

```bash
docker compose up -d --build mlflow prefect api prometheus grafana
docker compose run --rm pipeline python -m pdm.pipelines.training_flow
```

ขั้นตอนนี้ทำงานต่อเนื่องจนจบ: ดาวน์โหลดข้อมูลดิบ → ตรวจ schema → สร้าง feature → แบ่งข้อมูลตามเวลา → เทรน 4 โมเดล → ตรวจ gate → ลงทะเบียน → API โหลดโมเดลใหม่

ถ้าต้องการรันเร็วด้วยข้อมูลสังเคราะห์ (ไม่ต้องดาวน์โหลด) ให้ตั้งค่า env ก่อน:

```bash
PDM_CONFIG=configs/params.ci.yaml make all
```

| บริการ | URL |
|---|---|
| Prediction API (Swagger) | http://localhost:8000/docs |
| MLflow (การทดลอง + Model Registry) | http://localhost:5000 |
| Prefect (DAG + ประวัติการรัน) | http://localhost:4200 |
| Prometheus (metrics + alert) | http://localhost:9090/alerts |
| Grafana dashboard | http://localhost:3000 (admin/admin) |

## ทดลองเรียก API

```bash
curl http://localhost:8000/health
```

ตัวอย่าง request อยู่ที่ [docs/examples/predict_request.json](docs/examples/predict_request.json)

```bash
curl -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d @docs/examples/predict_request.json
```

| Endpoint | หน้าที่ |
|---|---|
| `POST /predict` | ทำนาย 1 เครื่อง จาก telemetry ย้อนหลัง ≥ 24 ชม. |
| `POST /predict/batch` | ทำนายสูงสุด 500 เครื่องในครั้งเดียว |
| `POST /feedback` | ส่งผลจริงกลับมา ใช้วัด live recall และตรวจ concept drift |
| `GET /health`, `GET /ready` | ตรวจสุขภาพระบบ |
| `GET /metrics` | Prometheus metrics |
| `GET /model` | ดูว่า serve โมเดลเวอร์ชันไหนอยู่ |
| `POST /admin/reload` | สั่งโหลด champion ใหม่จาก registry |

## คำสั่งสำหรับสาธิต

| สาธิต | คำสั่ง |
|---|---|
| ข้อมูลเสีย → ระบบหยุด + แจ้งเตือน | `make bad-data` |
| ดูทะเบียนโมเดล | `make models` |
| ย้อนกลับเวอร์ชันก่อนหน้า | `make rollback` |
| Data drift → ตรวจพบ → เทรนใหม่ | `make retrain-data` |
| Concept drift → ตรวจพบ → เทรนใหม่ | `make retrain-concept` |
| ตรวจ drift จาก log การใช้งานจริง | `make monitor-live` |
| วัด latency p50/p95 + throughput เทียบ SLO | `make loadtest` |
| Batch scoring ทุกกะ | `make batch` |

ลำดับการสาธิตแบบละเอียดอยู่ใน [docs/demo_script.md](docs/demo_script.md)

รายงานฉบับเต็มพร้อมผลบนข้อมูลจริงอยู่ที่ [docs/report.md](docs/report.md) ส่วนไฟล์หลักฐานอยู่ใน `docs/evidence/`

## พัฒนาบนเครื่อง (ไม่ใช้ Docker)

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements-dev.txt -c requirements.lock
export PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml
pytest
python -m pdm.pipelines.training_flow
uvicorn pdm.serving.app:app --port 8000
```

- `.venv/Scripts/activate` ใช้บน Windows ส่วน macOS/Linux ใช้ `source .venv/bin/activate`
- ถ้าไม่ได้ตั้ง `MLFLOW_TRACKING_URI` MLflow จะเก็บข้อมูลไว้ที่ `mlflow.db` + `mlruns/`

## โครงสร้างและเจ้าของงาน

| โฟลเดอร์ | หน้าที่ | เจ้าของ |
|---|---|---|
| `src/pdm/pipelines/`, `docker-compose.yml`, `Makefile`, `docs/architecture.md` | Prefect DAG, รวมระบบ | คนที่ 1 Tech Lead |
| `src/pdm/data/` | ingest, label, split, data version | คนที่ 2 Data Engineer |
| `src/pdm/features/`, `src/pdm/modeling/` | `build_features()`, โมเดล, การทดลอง | คนที่ 3 Feature + Model |
| `src/pdm/validation/` | schema, ตรวจข้อมูล, cleaning, ข้อมูลเสีย | คนที่ 4 Data Validation |
| `src/pdm/registry/` | MLflow tracking, gate, registry, rollback | คนที่ 5 Tracking + Registry |
| `src/pdm/serving/`, `Dockerfile` | FastAPI, batch, load test | คนที่ 6 Serving + Infra |
| `src/pdm/monitoring/`, `monitoring/` | drift, alert, retrain policy, Grafana | คนที่ 7 Monitoring |
| `.github/`, `tests/` (ส่วนรวม), `README.md`, `docs/` | CI/CD, เอกสาร | คนที่ 8 CI/CD + QA |

รายละเอียดว่าใครต้อง commit อะไร และตามลำดับไหน อยู่ใน [docs/team/](docs/team/README.md)

## การใช้ AI ช่วยเขียนโค้ด

ดูหัวข้อ "การใช้เครื่องมือ AI" ใน [docs/report_outline.md](docs/report_outline.md) ต้องกรอกให้ครบก่อนส่ง
