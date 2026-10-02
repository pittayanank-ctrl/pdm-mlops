# คนที่ 7: Monitoring + Retraining

ดูแลการเฝ้าระวังทั้งคุณภาพการทำนายและสถานะระบบ แยก Data Drift กับ Concept Drift ได้ มีเกณฑ์แจ้งเตือน และนโยบายเทรนใหม่ พร้อมสาธิตวงจรตั้งแต่ตรวจพบจนได้โมเดลใหม่ (ส่วนที่ 6)

## PR ของคุณ

| PR | branch | ไฟล์ |
|---|---|---|
| #16 | `feat/drift-monitoring` | `src/pdm/monitoring/__init__.py` `drift.py` `retrain_policy.py` `monitor.py` `tests/test_monitoring.py` |
| #17 | `feat/prometheus-grafana` | `monitoring/prometheus.yml` `alert_rules.yml` `grafana/` |
| #20 | `feat/drift-simulation` | `src/pdm/monitoring/simulate_drift.py` |
| #21 | `feat/retrain-on-drift-flow` | `src/pdm/pipelines/retrain_flow.py` (reviewer: คนที่ 1) |
| #29 | `docs/evidence-monitoring` | `docs/evidence/monitoring/` (มีให้แล้ว) |
| #31 | `docs/screenshots-monitoring` | ภาพ Grafana, Prometheus alerts, registry หลังเทรนใหม่ |

## ต้องเข้าใจ

**Data Drift กับ Concept Drift**

| | Data Drift | Concept Drift |
|---|---|---|
| ความหมาย | การกระจายของ input เปลี่ยน | input เหมือนเดิม แต่ผลลัพธ์จริงเปลี่ยน |
| วัดด้วย | PSI ต่อ feature (`drift.py`) | live recall เมื่อได้ label จริงจาก `/feedback` |
| ต้องใช้ label ไหม | ไม่ต้อง รู้ได้ทันที | ต้องใช้ จึงรู้ช้ากว่า (หลัง 24 ชม.) |
| เกณฑ์ | feature ที่ PSI > 0.2 มีสัดส่วน ≥ 30% | recall < 0.70 |
| ตัวอย่างในโรงงาน | เปลี่ยนรุ่นเซนเซอร์, ฤดูร้อน | ชิ้นส่วนล็อตใหม่เสียด้วยสาเหตุใหม่ |

**PSI:** แบ่ง bin ตาม quantile ของข้อมูล reference (ข้อมูลเทรน) แล้วคำนวณ PSI = Σ (cur − ref) × ln(cur / ref)
- PSI < 0.1: ไม่เปลี่ยน
- PSI 0.1–0.2: เปลี่ยนเล็กน้อย
- PSI > 0.2: เปลี่ยนชัด

**`retrain_policy.py`:** เทรนใหม่เมื่อพบ drift แบบใดแบบหนึ่ง และเทรนตามรอบทุกสัปดาห์ แต่โมเดลใหม่ต้องผ่าน gate เดิม (รวมถึงต้องชนะ champion บนข้อมูลล่าสุด) จึงจะขึ้นใช้งาน

**`simulate_drift.py`**
- **data:** vibration +20%, pressure +15% บวก noise, volt +10% ใน raw telemetry แล้วสร้าง feature ใหม่ผ่าน pipeline ปกติ
- **concept:** feature เหมือนเดิม แต่เกิด failure mode ใหม่ในเครื่อง model1/model2 ที่ความดันแกว่งสูง

**`simulate_drift.py`:** ช่วงเวลาที่จำลองคือ "หลังเทรน" = เดือนของ val + test เพื่อให้มี label พอเทรนใหม่

**`retrain_flow.py`:** แบ่งข้อมูลช่วงล่าสุดตามเวลา:
- 50% แรก: รวมเข้าชุดเทรน โดยให้น้ำหนักแถวละ 5 เท่าของข้อมูลเก่า (`retrain.recent_weight`) เพราะโลกเปลี่ยนแล้ว
- 25% ถัดไป: validation
- 25% สุดท้าย: test ที่ใช้เทียบกับ champion
- ข้อมูลเก่าใช้เฉพาะช่วงก่อน drift ห้ามเอาข้อมูลช่วงเวลาเดียวกัน 2 เวอร์ชันมาปนกัน

**`monitor.py --from-logs --last 500`:** ตรวจจาก log ของ API จริง โดยดูเฉพาะ 500 prediction ล่าสุด ถ้ารวม log ทั้งหมด drift ใหม่จะถูกเจือจางด้วยข้อมูลปกติเก่า label มาจาก `/feedback` เท่านั้น

**สถานะระบบ (Prometheus):** alert 5 ตัว ได้แก่ `ApiDown`, `ModelNotLoaded`, `LatencySLOBreached`, `ErrorRateSLOBreached`, `PredictedFailureRateShift`

**ผลบนข้อมูลจริง (ก.ย.–ธ.ค. 2015, 97,900 แถว):**

| scenario | drift share | live recall | สถานะ | ผลเทรนใหม่ |
|---|---|---|---|---|
| none | 0% | 0.998 | no_drift | ไม่เทรน |
| data | 33% | 1.00 (แต่ precision ตกเหลือ 0.48) | data_drift | เทรนใหม่ ผ่าน gate (PR-AUC 1.000 เทียบกับ champion 0.982) |
| concept | 0% | 0.449 | concept_drift | เทรนใหม่ ผ่าน gate (PR-AUC 1.000 เทียบกับ 0.499, ระบบเลือก RF) |
| data ผ่าน API จริง (`--from-logs --last 300`) | 41% | ไม่มี (ยังไม่มี feedback) | data_drift | ตามนโยบาย |

หมายเหตุ: บนข้อมูลสังเคราะห์ที่ใช้ใน CI feature `days_since_comp*` drift เองตามเวลา (ประมาณ 11%) แต่ยังต่ำกว่าเกณฑ์ 30% บนข้อมูลจริงที่มี 100 เครื่องไม่เกิด

## วิธีทดสอบ

```bash
export PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml
python -m pdm.monitoring.simulate_drift --scenario concept
python -m pdm.monitoring.monitor --current data/drift/concept_drift.parquet
python -m pdm.pipelines.retrain_flow --current data/drift/concept_drift.parquet
python -m pdm.registry.register list
pytest tests/test_monitoring.py
```

ให้สาธิตแต่ละ scenario จาก state ตั้งต้นที่มี champion จาก training flow ปกติ ถ้ารันต่อกันหลาย scenario ผลจะผสมกัน

## คำถามที่ต้องตอบได้

1. **แยก Data Drift กับ Concept Drift อย่างไร?** ดูตารางด้านบน: input เปลี่ยนหรือไม่ (PSI) เทียบกับ recall ตกหรือไม่
2. **ถ้ายังไม่มี label จะรู้ concept drift ได้อย่างไร?**
   - รู้โดยตรงไม่ได้
   - ใช้ตัวชี้นำแทน เช่น สัดส่วนการทำนายว่าเสียที่เปลี่ยนไป (alert `PredictedFailureRateShift`)
   - แล้วยืนยันเมื่อ label มาถึงหลัง 24 ชม.
3. **ทำไมไม่รอ recall ตกก่อนค่อยเทรนใหม่?** เครื่องเสียไม่บ่อย label จึงมาช้า ถ้ารอก็ต้องพลาดเครื่องเสียจริงไปก่อน data drift จึงเป็นสัญญาณที่เร็วกว่า
4. **ถ้าเทรนใหม่แล้วแย่กว่าเดิม?** gate ปฏิเสธ champion เดิมจึงยังทำงานต่อ
