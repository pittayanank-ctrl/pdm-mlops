# คนที่ 6: Serving + Infra

ดูแล API ที่รันใน container, latency p50/p95, throughput, SLO, รูปแบบการให้บริการ และ health/metrics endpoint (ส่วนที่ 5 ทั้งหมด) และรับ Test Case ของผู้สอนในวันนำเสนอ (ส่วนที่ 8)

## PR ของคุณ

| PR | branch | ไฟล์ |
|---|---|---|
| #13 | `feat/prediction-api` | `src/pdm/serving/__init__.py` `schemas.py` `payloads.py` `model_loader.py` `app.py` `tests/test_api.py` `docs/examples/predict_request.json` |
| #15 | `feat/docker-api` | `Dockerfile` `.dockerignore` `scripts/start_api.sh` `scripts/gunicorn_conf.py` |
| #19 | `feat/batch-and-loadtest` | `src/pdm/serving/batch.py` `benchmark.py` |
| #28 | `docs/evidence-serving` | `docs/evidence/slo/` + `docs/evidence/batch/` (มีให้แล้ว) |
| #31 | `docs/screenshots-serving` | ภาพ Swagger `/predict` ที่ได้ 200 และ 422 |

## ต้องเข้าใจ

**`schemas.py`**
- Pydantic ตรวจ request ทุกอย่างก่อนถึงโมเดล
- ช่วงค่ามาจาก `HARD_BOUNDS` ตัวเดียวกับ schema ของข้อมูลเทรน
- telemetry ต้องเป็นรายชั่วโมงต่อเนื่อง ≥ 24 แถว
- sensor เป็น `null` ได้ไม่เกิน 25%
- `last_maint` ห้ามเป็นเวลาในอนาคต
- ข้อมูลผิดจะได้ 422 พร้อมบอกว่าผิดที่ field ไหน ระบบไม่ crash

**`payloads.py`:** แปลง request เป็น DataFrame แล้วส่งเข้า `build_features()` ตัวเดียวกับตอนเทรน

**`app.py`**

| Endpoint | หน้าที่ |
|---|---|
| `/predict` | ทำนายเครื่องเดียว |
| `/predict/batch` | ทำนายสูงสุด 500 เครื่องในครั้งเดียว |
| `/health` | liveness |
| `/ready` | ตอบ 503 ถ้ายังไม่มีโมเดล |
| `/metrics` | Prometheus |
| `/feedback` | รับผลจริงกลับมา |
| `/admin/reload` | สั่งโหลด champion ใหม่ |

- **log:** ทุก prediction ถูกเขียนลง `logs/predictions.jsonl` พร้อม feature เพื่อใช้ตรวจ drift
- **Multi-worker:** รัน gunicorn 4 process (`start_api.sh`, `scripts/gunicorn_conf.py`) เพราะการสร้าง feature ด้วย pandas ใช้ CPU ล้วน thread เดียวจึงติด GIL ไม่ใช้ `uvicorn --workers` เพราะวัดได้ว่าใน container มันเพิ่ม 44 ms ทุก request
- Prometheus ใช้ multiprocess mode เพื่อรวมตัวนับจากทุก worker

**ผลวัดบนเครื่อง dev** (Windows, 4 workers, sample data):

| concurrency | throughput | p50 | p95 | SLO (p95 < 100 ms) |
|---|---|---|---|---|
| 1 | 54 req/s | 18 ms | 21 ms | ผ่าน |
| 4 | 175 req/s | 23 ms | 27 ms | ผ่าน |
| 8 | 151 req/s | 27 ms | 128 ms | ไม่ผ่าน (เกินขีดจำกัดของเครื่อง) |

ก่อนเพิ่ม worker (1 process ที่ concurrency 4) ได้ p95 = 131 ms ไม่ผ่าน SLO ใช้ตัวเลขนี้อธิบายการตัดสินใจเพิ่ม worker ได้

**ผลใน Docker บนข้อมูลจริง (ใช้ในรายงาน, `docs/evidence/slo/`):**

| concurrency | throughput | p50 | p95 | SLO |
|---|---|---|---|---|
| 1 | 37.5 req/s | 26.7 ms | 32.4 ms | ผ่าน |
| 4 | 157.2 req/s | 24.6 ms | 30.0 ms | ผ่าน |
| 8 | 24.2 req/s | 150.2 ms | 375.2 ms | ไม่ผ่าน |
| 16 | 32.1 req/s | 399.7 ms | 530.2 ms | ไม่ผ่าน |

**สิ่งที่ต้องอธิบายได้:** concurrency ≥ 8 แย่ลงเพราะ async worker รับ connection แบบ keep-alive เกินส่วนของตัวเอง แก้ได้ด้วย load balancer ระดับ request หรือหลาย container

**`benchmark.py` ใช้หลาย process ไม่ใช่หลาย thread:** ถ้าใช้หลาย thread ตัวยิงเองติด GIL แล้ววัดได้ช้ากว่าจริงหลายเท่า

**Log:** แต่ละ worker เขียนไฟล์ของตัวเอง (`logs/predictions-<pid>.jsonl`) เพราะหลาย process เขียนไฟล์เดียวกันพร้อมกันแล้วบรรทัดปนกัน ใน Docker เก็บไว้ใน named volume `api-logs` เพราะการเขียนลงโฟลเดอร์ Windows ที่ mount เข้ามาใช้เวลา 11 ms ต่อครั้ง

**รูปแบบการให้บริการ:** real-time สำหรับเครื่องที่ต้องการผลทันที + batch ทุกกะ (`batch.py`) ที่จัดอันดับทั้งโรงงานให้หัวหน้าช่างวางแผน

**ความต้องการจริง:** 100 เครื่อง × 1 ครั้ง/ชม. ≈ 0.03 req/s ระบบรองรับได้มากกว่านั้นหลายพันเท่า

## วิธีทดสอบ

```bash
pytest tests/test_api.py
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml uvicorn pdm.serving.app:app --port 8000
curl -X POST localhost:8000/predict -H "Content-Type: application/json" -d @docs/examples/predict_request.json
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml python -m pdm.serving.benchmark --requests 500 --concurrency 4
```

## คำถามที่ต้องตอบได้

1. **SLO คืออะไร วัดอย่างไร?**
   - SLO: p95 < 100 ms และ error rate < 1%
   - วัดด้วย `benchmark.py` จากฝั่ง client แบบ end-to-end
   - ตอนรันจริงดูจาก Prometheus histogram และ alert `LatencySLOBreached`
2. **ทำไมต้องหลาย worker?** pandas ใช้ CPU และติด GIL thread เดียวจึงรับ request พร้อมกันได้ไม่ดี เลยแยกเป็นหลาย process
3. **ถ้าส่งข้อมูลผิดเข้ามา?** ได้ 422 พร้อมรายละเอียด ระบบไม่ crash และไม่มี request ผิดไปถึงโมเดล
4. **ทำไมให้ client ส่ง telemetry 24 ชม. มาทั้งหมด?** API จึงไม่ต้องเก็บ state ทำให้ scale เป็นหลาย worker ได้ง่าย และคำนวณ feature ด้วยโค้ดเดียวกับตอนเทรน
5. **real-time กับ batch ใช้ตอนไหน?** real-time ใช้ตอน gateway ของเครื่องส่งข้อมูลมา ส่วน batch ใช้ทุกต้นกะเพื่อจัดอันดับทั้งโรงงาน
