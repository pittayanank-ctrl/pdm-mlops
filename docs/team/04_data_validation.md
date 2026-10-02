# คนที่ 4: Data Validation

ดูแล schema และการตรวจจับความผิดปกติ: เมื่อป้อนข้อมูลเสีย ระบบต้องหยุดและแจ้งเตือน (ส่วนที่ 2) รวมถึงการจัดการค่าที่หายไปและค่าผิดปกติ

## PR ของคุณ

| PR | branch | ไฟล์ |
|---|---|---|
| #3 | `feat/validation-schema` | `src/pdm/validation/__init__.py` `schema.py` `validate.py` |
| #4 | `feat/cleaning-bad-data` | `src/pdm/validation/cleaning.py` `bad_data.py` |
| #7 | `test/validation` | `tests/test_validation.py` |
| #26 | `docs/evidence-validation` | `docs/evidence/validation/` (มีให้แล้ว: pass 1 + FAIL 7) |

**งานเพิ่ม:**
- เทียบช่วงค่าใน `HARD_BOUNDS` และ `cleaning.clip` กับ EDA ของข้อมูลจริงจากคนที่ 2
- เตรียมไฟล์ข้อมูลเสียสำหรับรับ Test Case ของผู้สอน

## ต้องเข้าใจ

**`schema.py`**

| ตาราง | สิ่งที่ตรวจ |
|---|---|
| telemetry | ชนิดข้อมูล, ช่วงค่า, `machineID` 1–100, ห้ามซ้ำ (machineID, datetime), sensor ว่างได้ไม่เกิน 5% |
| errors | errorID ต้องอยู่ใน error1–5 |
| maint, failures | comp ต้องอยู่ใน comp1–4 |
| machines | model ต้องอยู่ใน model1–4, age 0–30 |

- `HARD_BOUNDS` ถูก import ไปใช้ใน API ด้วย ทำให้ข้อมูลเทรนกับ request ใช้กฎเดียวกัน
- การเช็กสัดส่วน null อยู่ระดับ DataFrame เพราะ pandera ข้าม null ก่อนรัน check ของคอลัมน์ที่ `nullable=True` (เคยเป็น bug ที่เจอระหว่างทดสอบ)

**`validate.py`**
- ใช้ `lazy=True` เก็บทุกปัญหาในครั้งเดียว แทนที่จะหยุดที่ปัญหาแรก
- เช็กข้ามตาราง: เครื่องใน telemetry ต้องมีอยู่ในตาราง machines
- เมื่อไม่ผ่าน:
  1. เขียน `reports/validation/*_FAIL.json`
  2. log ERROR
  3. ส่ง webhook ถ้าตั้งค่า `PDM_ALERT_WEBHOOK` ไว้ (Discord/LINE)
  4. raise `DataValidationError` ทำให้ pipeline หยุด
- CLI คืนค่า exit code 1 ซึ่ง CI ใช้ตรวจ

**`cleaning.py`** (ใช้ทั้งตอนเทรนและตอนให้บริการ)
- **ค่าหายช่วงสั้น:** forward-fill ได้ไม่เกิน 3 ชม. ต่อเครื่อง
- **ค่าที่ยังหายอยู่:** เติมด้วยกึ่งกลางของช่วงปกติ ซึ่งเป็นค่าคงที่จาก config ไม่ใช่ median ของข้อมูล เพื่อกัน skew
- **outlier:** clip ไว้ในช่วงปกติ

**แยก 2 ระดับ:**

| ระดับ | ตัวอย่าง | ผลลัพธ์ |
|---|---|---|
| hard bound | vibration ติดลบ | เป็นไปไม่ได้ทางกายภาพ → reject |
| soft bound | ค่าสูงผิดปกติแต่ยังเป็นไปได้ | clip |

**`bad_data.py`:** สร้างข้อมูลเสีย 7 แบบ ได้แก่ คอลัมน์หาย, ชนิดผิด, ค่าติดลบ, เกินช่วง, null เกิน 5%, แถวซ้ำ, เครื่องที่ไม่มีในระบบ

## วิธีทดสอบ

```bash
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml python -m pdm.validation.bad_data
PYTHONPATH=src PDM_CONFIG=configs/params.ci.yaml python -m pdm.validation.validate --raw-dir data/bad/negative_vibration   # exit 1
pytest tests/test_validation.py
```

## คำถามที่ต้องตอบได้

1. **ถ้า CSV มี "N/A" ในคอลัมน์ตัวเลขเกิดอะไร?** `read_csv` แปลงเป็น NaN จึงนับเป็นค่าหาย ถ้าเกิน 5% จะไม่ผ่าน แต่ถ้าเป็นข้อความอื่น คอลัมน์จะกลายเป็น object แล้วไม่ผ่านการเช็กชนิดข้อมูล
2. **ทำไมไม่ใช้ median เติมค่าหาย?** median ของ request 24 แถวไม่เท่ากับ median ของชุดเทรน ทำให้เกิด skew จึงใช้ค่าคงที่จาก config
3. **reject กับ clip ต่างกันอย่างไร?** ค่าที่เป็นไปไม่ได้ทางกายภาพ reject ส่วนค่าสุดโต่งแต่ยังเป็นไปได้ clip
4. **ทำไมเลือก Pandera?** schema เขียนเป็นโค้ด Python อยู่ใน repo ได้ เบา ตรวจ pandas ได้โดยตรง และมี lazy validation
