# แผนงานทีมและลำดับ commit

ผู้สอนให้คะแนนรายบุคคลจาก 3 อย่าง: ประวัติ commit, การประเมินจากเพื่อน และการตอบคำถามวันนำเสนอ
ดังนั้นทุกคนต้อง commit งานส่วนของตัวเอง ผ่าน branch และ Pull Request ด้วยบัญชี GitHub ของตัวเอง

## กติกาก่อนเริ่ม

1. **ห้าม commit แทนกัน** และห้ามให้คนเดียว push ทั้งโปรเจกต์
2. **ก่อน commit ทุกไฟล์:** อ่านให้เข้าใจ รัน test ของส่วนนั้น และอธิบายได้ทุกบรรทัด ตามที่เอกสารวิชากำหนด
3. **จดการใช้ AI:** ถ้าใช้ AI ช่วยส่วนไหน ให้จดไว้ในตาราง "การใช้เครื่องมือ AI" ใน [report_outline.md](../report_outline.md)
4. **แก้หรือปรับปรุงโค้ดได้** เช่น เพิ่ม feature, เปลี่ยน hyperparameter หรือเพิ่ม test ถ้าทำให้ดีขึ้น ให้เขียนเหตุผลไว้ใน PR
5. **ตั้งชื่อในเครื่องตัวเองก่อน commit ครั้งแรก:**

    ```bash
    git config user.name "ชื่อจริง"
    git config user.email "อีเมลที่ผูกกับ GitHub"
    ```

## วิธีทำงานของแต่ละ PR

```bash
git checkout main && git pull
git checkout -b feat/data-ingest            # ชื่อ branch ตามตารางด้านล่าง
# วางไฟล์ของตัวเองจากโฟลเดอร์ต้นฉบับที่แชร์ แล้วอ่าน, รัน, แก้ตามต้องการ
pytest                                       # ต้องผ่านก่อน push
ruff check src tests && ruff format src tests
git add <เฉพาะไฟล์ของตัวเอง>
git commit -m "feat(data): download Azure PdM and generate sample data"
git push -u origin feat/data-ingest
# เปิด PR บน GitHub → ขอ review จาก reviewer ในตาราง → CI ผ่าน → merge
```

- ทยอย commit เป็นหลาย commit เล็กๆ ตามที่ทำงานจริง ไม่ต้องรวมเป็น commit ใหญ่ commit เดียว
- reviewer ต้องอ่านโค้ดจริงและ comment อย่างน้อย 1 ข้อ

## ลำดับ PR

ต้อง merge ตามลำดับ เพราะ PR หลังใช้โค้ดจาก PR ก่อนหน้า

| # | วัน | เจ้าของ | branch | ไฟล์ | ต้องรอ | reviewer |
|---|---|---|---|---|---|---|
| 1 | 2 ต.ค. | คนที่ 1 | `chore/repo-skeleton` | `.gitignore` `.gitattributes` `pyproject.toml` `requirements.txt` `requirements-dev.txt` `requirements.lock` `configs/params.yaml` `src/pdm/__init__.py` `src/pdm/config.py` `CONTRIBUTING.md` `.github/pull_request_template.md` `docs/team/` | - | 8 |
| 2 | 2 ต.ค. | คนที่ 2 | `feat/data-ingest` | `src/pdm/data/__init__.py` `sample_data.py` `ingest.py` `configs/params.ci.yaml` | 1 | 4 |
| 3 | 2 ต.ค. | คนที่ 4 | `feat/validation-schema` | `src/pdm/validation/__init__.py` `schema.py` `validate.py` | 2 | 2 |
| 4 | 2 ต.ค. | คนที่ 4 | `feat/cleaning-bad-data` | `src/pdm/validation/cleaning.py` `bad_data.py` | 3 | 3 |
| 5 | 2 ต.ค. | คนที่ 2 | `feat/labels-split-version` | `src/pdm/data/labels.py` `split.py` `versioning.py` `tests/conftest.py` `tests/test_data.py` | 2 | 3 |
| 6 | 2 ต.ค. | คนที่ 5 | `feat/mlflow-tracking` | `src/pdm/registry/__init__.py` `tracking.py` | 1 | 3 |
| 7 | 3 ต.ค. | คนที่ 4 | `test/validation` | `tests/test_validation.py` | 4, 5 | 8 |
| 8 | 3 ต.ค. | คนที่ 8 | `ci/quality-and-data-checks` | `.github/workflows/ci.yml` (เฉพาะ job `code-quality` + `data-validation`) | 7 | 1 |
| 9 | 3 ต.ค. | คนที่ 3 | `feat/build-features` | `src/pdm/features/__init__.py` `build.py` | 4, 5 | 6 |
| 10 | 3 ต.ค. | คนที่ 3 | `feat/models-training` | `src/pdm/modeling/__init__.py` `models.py` `metrics.py` `train.py` `tests/test_features.py` | 6, 9 | 5 |
| 11 | 3 ต.ค. | คนที่ 5 | `feat/gate-registry-rollback` | `src/pdm/registry/evaluate.py` `register.py` `tests/test_registry.py` | 10 | 3 |
| 12 | 3 ต.ค. | คนที่ 1 | `feat/prefect-training-flow` | `src/pdm/pipelines/__init__.py` `steps.py` `training_flow.py` | 11 | 5 |
| 13 | 3 ต.ค. | คนที่ 6 | `feat/prediction-api` | `src/pdm/serving/__init__.py` `schemas.py` `payloads.py` `model_loader.py` `app.py` `tests/test_api.py` `docs/examples/predict_request.json` | 9 | 4 |
| 14 | 3 ต.ค. | คนที่ 3 | `test/training-serving-skew` | `tests/test_skew.py` | 13 | 6 |
| 15 | 3 ต.ค. | คนที่ 6 | `feat/docker-api` | `Dockerfile` `.dockerignore` `scripts/start_api.sh` `scripts/gunicorn_conf.py` | 13 | 1 |
| 16 | 3 ต.ค. | คนที่ 7 | `feat/drift-monitoring` | `src/pdm/monitoring/__init__.py` `drift.py` `retrain_policy.py` `monitor.py` `tests/test_monitoring.py` | 9 | 2 |
| 17 | 3 ต.ค. | คนที่ 7 | `feat/prometheus-grafana` | `monitoring/` ทั้งโฟลเดอร์ | 13 | 6 |
| 18 | 4 ต.ค. | คนที่ 1 | `feat/compose-makefile` | `docker-compose.yml` `Makefile` | 12, 15, 17 | 6 |
| 19 | 4 ต.ค. | คนที่ 6 | `feat/batch-and-loadtest` | `src/pdm/serving/batch.py` `benchmark.py` | 13 | 7 |
| 20 | 4 ต.ค. | คนที่ 7 | `feat/drift-simulation` | `src/pdm/monitoring/simulate_drift.py` | 16 | 3 |
| 21 | 4 ต.ค. | คนที่ 7 | `feat/retrain-on-drift-flow` | `src/pdm/pipelines/retrain_flow.py` | 12, 20 | 1 |
| 22 | 4 ต.ค. | คนที่ 8 | `ci/model-gate-and-docker` | `.github/workflows/ci.yml` (เพิ่ม job `model-quality` + `docker-build`) | 12, 15 | 5 |
| 23 | 4 ต.ค. | คนที่ 8 | `docs/readme-canvas-report` | `README.md` `docs/ai_project_canvas.md` `docs/report_outline.md` `docs/report.md` | 18 | 1 |
| 24 | 4 ต.ค. | คนที่ 1 | `docs/architecture-demo` | `docs/architecture.md` `docs/demo_script.md` | 18 | 7 |
| 25 | 5 ต.ค. | คนที่ 3 | `docs/evidence-experiments` | `docs/evidence/experiments/` | 10 | 5 |
| 26 | 5 ต.ค. | คนที่ 4 | `docs/evidence-validation` | `docs/evidence/validation/` | 7 | 2 |
| 27 | 5 ต.ค. | คนที่ 5 | `docs/evidence-gate` | `docs/evidence/gate/` | 11 | 3 |
| 28 | 5 ต.ค. | คนที่ 6 | `docs/evidence-serving` | `docs/evidence/slo/` `docs/evidence/batch/` | 19 | 7 |
| 29 | 5 ต.ค. | คนที่ 7 | `docs/evidence-monitoring` | `docs/evidence/monitoring/` | 21 | 6 |
| 30 | 5 ต.ค. | คนที่ 8 | `test/ci-must-fail-*` (3 PR, **ไม่ merge**) | ทำให้พังทีละด้านเพื่อเก็บหลักฐาน (ดูคู่มือคนที่ 8) | 22 | - |
| 31 | 5 ต.ค. | ทุกคน | `docs/screenshots-<ส่วน>` | ภาพหน้าจอ MLflow / Prefect / Grafana / Actions ของส่วนตัวเอง ใส่ `docs/evidence/screenshots/` และแทรกในรายงานตรง **[ภาพ: ...]** | 18 | 1 |
| 32 | 5 ต.ค. 12:00 | คนที่ 1 | - | code freeze, `git tag v1.0`, ตรวจรันจากเครื่องเปล่า | ทั้งหมด | - |

## คู่มือรายคน

| คนที่ | หน้าที่ | คู่มือ |
|---|---|---|
| 1 | Tech Lead / Pipeline | [01_tech_lead.md](01_tech_lead.md) |
| 2 | Data Engineer | [02_data_engineer.md](02_data_engineer.md) |
| 3 | Feature + Model | [03_feature_model.md](03_feature_model.md) |
| 4 | Data Validation | [04_data_validation.md](04_data_validation.md) |
| 5 | Tracking + Registry | [05_tracking_registry.md](05_tracking_registry.md) |
| 6 | Serving + Infra | [06_serving_infra.md](06_serving_infra.md) |
| 7 | Monitoring + Retraining | [07_monitoring.md](07_monitoring.md) |
| 8 | CI/CD + QA + เอกสาร | [08_cicd_docs.md](08_cicd_docs.md) |

## ไฟล์ของแต่ละคน

ไฟล์ถูกแบ่งไว้แล้วในโฟลเดอร์ `handoff/` (แชร์ให้ทุกคน เช่นผ่าน Google Drive) แยกเป็น `P1_tech_lead/` ถึง `P8_cicd_docs/`
ในแต่ละโฟลเดอร์มี `README.md` ที่บอกคำสั่ง git ของทุก PR ให้ copy ไปใช้ได้ทันที
ให้วางโฟลเดอร์ `handoff` ไว้ข้างโฟลเดอร์ repo `pdm-mlops` แล้วคำสั่ง `Copy-Item` ในนั้นจะใช้ได้ตามที่เขียนไว้
