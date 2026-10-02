# คนที่ 3: Feature + Model

ดูแล feature ที่ใช้ร่วมกันทั้งตอนเทรนและตอนให้บริการ (กัน Training-Serving Skew ในส่วนที่ 2) และ baseline กับการทดลองเปรียบเทียบ (ส่วนที่ 3)

## PR ของคุณ

| PR | branch | ไฟล์ |
|---|---|---|
| #9 | `feat/build-features` | `src/pdm/features/__init__.py` `build.py` |
| #10 | `feat/models-training` | `src/pdm/modeling/__init__.py` `models.py` `metrics.py` `train.py` `tests/test_features.py` |
| #14 | `test/training-serving-skew` | `tests/test_skew.py` |
| #25 | `docs/evidence-experiments` | `docs/evidence/experiments/` (มีให้แล้ว) |
| #31 | `docs/screenshots-model` | ภาพ MLflow compare runs |

**งานเพิ่ม (ช่วยเพิ่มคะแนนรายบุคคลได้จริง):**
- รันกับข้อมูลจริงและเปรียบเทียบผล
- ลองปรับ hyperparameter หรือเพิ่ม feature แล้วเปิด PR แยก พร้อมเขียนผลเทียบในรายงาน

## ต้องเข้าใจ

**`build.py`**
- `build_features()` คือ feature code ชุดเดียวของระบบ ถูกเรียกจาก 3 ที่: `build_training_table` (เทรน), API (`app.py`) และ batch
- **Rolling feature:** `rolling("3h")` และ `rolling("24h")` แบบใช้เวลา (ไม่ใช่นับจำนวนแถว) ต่อเครื่อง จึงไม่พังถ้ามีแถวหาย
- **Error counts:** นับ error แต่ละชนิดใน 24 ชม.
- **days_since_comp:** ใช้ `merge_asof` ครั้งเดียวกับตารางที่สะสมเวลาซ่อมล่าสุดของทุกชิ้นส่วน
- **failure นับเป็นการซ่อม** (`maint_with_failures`) เพราะชิ้นส่วนที่เสียถูกเปลี่ยนใหม่
- **เก็บเฉพาะแถวที่มีประวัติครบ 24 ชม.:** ใช้กฎเดียวกันทั้งตอนเทรนและตอนให้บริการ

**`models.py`**
- ทุกโมเดลเป็น sklearn `Pipeline` (impute → scale → one-hot → model) และบันทึกเป็น artifact เดียว serving จึงใช้ preprocessing ชุดเดียวกับตอนเทรนเสมอ
- `ThresholdRule` คือ baseline ที่เลียนแบบช่าง: "ถ้า vibration สูงให้เตือน"

**`metrics.py`**
- threshold ไม่ได้ใช้ 0.5 แต่เลือกจากค่าที่ทำให้ต้นทุนรวมต่ำสุด
- ต้นทุนรวม = FN × 50,000 + FP × 5,000 บาท
- เลือกเฉพาะ threshold ที่ recall และ precision บน validation สูงกว่าเกณฑ์ gate อย่างน้อย `gate.threshold_margin` (0.05) เผื่อค่าแกว่งเมื่อไปเจอ test set ถ้าไม่มีค่าไหนผ่าน จะใช้ค่าที่ต้นทุนต่ำสุดแทน
- `train.py` รองรับคอลัมน์ `sample_weight` (ใช้ตอนเทรนใหม่หลัง drift)

**`train.py`**
- เทรนทุกโมเดลที่ระบุใน config บันทึกลง MLflow ทีละ run แล้วเลือกตัวที่ PR-AUC บน validation สูงสุด
- ไม่แตะ test set เพราะ test ใช้ตอน gate เท่านั้น

**`test_skew.py`**
- สร้าง JSON request จากข้อมูลดิบ ส่งผ่าน `request_to_frames` และ `build_features` ฝั่ง serving
- แล้วเทียบกับแถวเดียวกันในตารางที่ใช้เทรน ค่าต้องตรงกันทุก feature
- เทสต์นี้คือหลักฐานว่าไม่มี Training-Serving Skew

## ผลบนข้อมูลจริง (validation)

| โมเดล | PR-AUC | Recall | Precision |
|---|---|---|---|
| rule baseline | 0.088 | 0.26 | 0.19 |
| logistic regression | 0.817 | 1.00 | 0.69 |
| random forest | 0.9997 | 1.00 | 0.99 |
| XGBoost | 0.9999 | 1.00 | 0.98 |

**บน test:** recall 0.997, precision 0.957, FN 3 / FP 40

**ผลดีผิดปกติ จึงตรวจ leakage แล้ว:** เทรนแยกทีละกลุ่ม feature ได้ PR-AUC: เซนเซอร์ 0.25, error 0.69, days_since 0.31 ไม่มี feature ไหนรั่ว ผลสูงมาจากการรวมสัญญาณ ในข้อมูลจำลองชุดนี้ (ต้องอธิบายได้ เพราะน่าจะถูกถาม)

## วิธีทดสอบ

```bash
pytest tests/test_features.py tests/test_skew.py
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml python -m pdm.pipelines.training_flow
# ผลเทียบอยู่ที่ reports/experiments/comparison.csv และ MLflow UI
```

## คำถามที่ต้องตอบได้

1. **ทำไมใช้ PR-AUC ไม่ใช้ accuracy?** positive มีแค่ไม่กี่ % ถ้าทายว่า "ไม่เสีย" ทุกแถวก็ได้ accuracy 95% แต่ไม่มีประโยชน์ PR-AUC ดูเฉพาะความสามารถในการจับคลาสที่หายาก
2. **กัน Skew อย่างไร?**
   - feature function เดียว
   - preprocessing อยู่ใน Pipeline เดียวกับโมเดล
   - cleaning ใช้ค่าคงที่จาก config ไม่ fit จากข้อมูล เพราะ median ของ request 24 แถวไม่เท่ากับ median ของชุดเทรน
   - มี `test_skew.py` เป็นหลักฐาน
3. **เลือก threshold อย่างไร?** ลองทุกค่า 0.02–0.98 บน validation แล้วเลือกค่าที่ต้นทุนรวมต่ำสุด ในกลุ่มค่าที่ผ่านเกณฑ์ gate บวก margin 0.05 ผลคือ threshold ต่ำ เพราะการพลาดเครื่องเสียแพงกว่าการเตือนผิด 10 เท่า
4. **ทำไม XGBoost ชนะ?** จับความสัมพันธ์แบบไม่เป็นเส้นตรงและ interaction ได้ (error ชนิดไหนคู่กับเซนเซอร์ตัวไหน) ได้ PR-AUC สูงสุด และเล็กกว่า RF มาก (0.54 MB เทียบกับประมาณ 8 MB) จึงเร็วกว่า (p95 1.6 ms)
5. **จัดการคลาสไม่สมดุลอย่างไร?** ใช้ `class_weight="balanced"` และ `scale_pos_weight` ร่วมกับเลือก threshold จากต้นทุน
