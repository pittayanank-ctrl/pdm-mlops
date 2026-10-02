# คนที่ 5: Tracking + Registry

ดูแลการบันทึกการทดลองให้ครบ 6 อย่าง และทะเบียนโมเดลที่มีเวอร์ชัน สถานะ ด่านตรวจ และการย้อนกลับ (ส่วนที่ 4 ทั้งหมด)

## PR ของคุณ

| PR | branch | ไฟล์ |
|---|---|---|
| #6 | `feat/mlflow-tracking` | `src/pdm/registry/__init__.py` `tracking.py` |
| #11 | `feat/gate-registry-rollback` | `src/pdm/registry/evaluate.py` `register.py` `tests/test_registry.py` |
| #27 | `docs/evidence-gate` | `docs/evidence/gate/` (มีให้แล้ว) |
| #31 | `docs/screenshots-registry` | ภาพ MLflow: run 1 run ที่เห็นครบ 6 อย่าง, registry ที่มี champion / archived / rolled_back |

## ต้องเข้าใจ

**`tracking.py`: 6 อย่างที่ทุก run บันทึก**

| สิ่งที่ต้องบันทึก | บันทึกที่ไหน |
|---|---|
| เวอร์ชันโค้ด | tag `git_commit` + `git_dirty` |
| เวอร์ชันข้อมูล | tag `data_version` (hash ของไฟล์) |
| ไฮเปอร์พารามิเตอร์ | params (รวม `threshold`, `seed`) |
| ตัวชี้วัด | metrics `val_*`, `test_*`, latency, size |
| ไฟล์ผลลัพธ์ | artifact: model, PR curve, confusion matrix, feature importance, gate report |
| สภาพแวดล้อม | tag `python_version`, `platform` + artifact `requirements-frozen.txt` + `config/params.json` |

**`evaluate.py`: gate**

ทดสอบบน test set ที่ไม่เคยใช้เลย ต้องผ่านทุกข้อ:
1. recall ≥ 0.80
2. precision ≥ 0.50
3. p95 latency < 100 ms
4. ขนาดโมเดล < 50 MB
5. PR-AUC ≥ PR-AUC ของ champion บน test set เดียวกัน

`gate_checks()` เป็น pure function จึง unit test ได้

**`register.py`**
- ลงทะเบียนทุก candidate แม้ไม่ผ่าน gate เพื่อให้เห็นใน registry ว่าเคยถูกปฏิเสธ
- **สถานะ** (tag `status`): `champion`, `rejected`, `archived`, `rolled_back`
- **alias `champion`** คือเวอร์ชันที่ API ใช้จริง
- **rollback:** ย้าย alias กลับไปเวอร์ชัน `previous_champion` แล้วแจ้ง API ให้ reload นอกจากนี้ API ทุก worker เช็ก registry เองทุก 15 วินาที

## วิธีทดสอบ

```bash
pytest tests/test_registry.py
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml python -m pdm.registry.register list
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml python -m pdm.registry.register rollback
mlflow ui --backend-store-uri sqlite:///mlflow.db     # ดู UI ตอนรันบนเครื่อง
```

## คำถามที่ต้องตอบได้

1. **ถ้าโมเดลใหม่แย่กว่าเดิม ระบบรู้ได้อย่างไร?** gate เทียบ PR-AUC กับ champion บน test set เดียวกัน ถ้าแย่กว่าจะไม่ promote และสถานะเป็น `rejected`
2. **ถ้าขึ้นใช้งานแล้วพบว่าแย่ ย้อนกลับอย่างไร?**
   - สั่ง `make rollback` เพื่อย้าย alias `champion` กลับไปเวอร์ชันก่อนหน้า
   - API reload ทันที หรือภายใน 15 วินาที
   - ไม่ต้อง build image หรือ deploy ใหม่
3. **ทำไมใช้ alias ไม่ใช้ stage?** MLflow 2.9+ เลิกแนะนำ stage แล้ว alias ชี้ไปเวอร์ชันใดก็ได้ และย้ายได้ทันที
4. **รู้ได้อย่างไรว่าโมเดลใน production มาจากข้อมูลและโค้ดชุดไหน?** registry version → run_id → tag `git_commit` + `data_version`
