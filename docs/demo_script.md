# สคริปต์สาธิต (12 นาที)

(เจ้าของ: คนที่ 1) ต้องเปิดระบบก่อนเริ่มนำเสนอ:
- รัน `make all` ล่วงหน้า และเปิดแท็บ MLflow, Prefect, Grafana, Swagger ไว้
- ใช้ข้อมูลจริงถ้าเครื่องแรงพอ ถ้าไม่พอใช้ `PDM_CONFIG=configs/params.ci.yaml`

| เวลา | คนพูด | สาธิต | คำสั่ง / หน้าจอ |
|---|---|---|---|
| 0:00 | 8 | ปัญหา, ผู้ใช้, Canvas, metric | สไลด์ |
| 1:30 | 1 | สถาปัตยกรรม + DAG | `docs/architecture.md`, Prefect UI แสดง flow run ที่ผ่าน |
| 3:00 | 2 | ข้อมูล, การแบ่งตามเวลา, data version | MLflow: tag `data_version` |
| 4:00 | 4 | ข้อมูลเสีย → ระบบหยุด + แจ้งเตือน | `make bad-data` แล้วแสดงไฟล์ `reports/validation/*FAIL.json` |
| 5:00 | 3 | การทดลอง 4 โมเดล, เหตุผลที่เลือก, threshold จากต้นทุน, กัน Skew | MLflow compare runs, `reports/experiments/comparison.csv` |
| 6:30 | 5 | Gate + registry + rollback | `make models`, `make rollback`, `curl /model` |
| 7:30 | 6 | ยิง API สด, ข้อมูลผิดได้ 422, load test เทียบ SLO | Swagger `/predict`, `make loadtest` |
| 9:00 | 7 | Concept drift → alert → เทรนใหม่ → โมเดลใหม่ | `make retrain-concept`, เปิด `reports/monitoring/concept_drift.html` |
| 10:30 | 8 | CI ผ่าน / ไม่ผ่าน 3 ด้าน | GitHub Actions: PR ที่ผ่าน + PR ที่พัง |
| 11:30 | 1 | สรุป | |

## เตรียมรับ Test Case ของผู้สอน

- **ข้อมูลปกติ:** ส่ง JSON ตาม `docs/examples/predict_request.json` จะได้ 200 และค่า `failure_probability`
- **ข้อมูลผิดปกติ** (ค่าติดลบ, ชนิดผิด, ข้อมูลไม่ครบ 24 ชม., ชั่วโมงขาด, รุ่นเครื่องไม่รู้จัก, field หาย, sensor หายเกิน 25%) จะได้ 422 พร้อมข้อความบอกว่าผิดที่ field ไหน และระบบไม่ล่ม
- **ไฟล์ CSV ผิดปกติ:** วางไว้ในโฟลเดอร์หนึ่ง แล้วรัน `python -m pdm.validation.validate --raw-dir <folder>` จะได้ exit 1 พร้อม report
- **ข้อมูลหายบางค่า** (sensor เป็น `null` ไม่เกิน 25%) ยังได้ 200 เพราะระบบเติมค่าแบบเดียวกับตอนเทรน
