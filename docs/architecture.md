# สถาปัตยกรรมระบบ

(เจ้าของ: คนที่ 1) ภาพรวมทั้งระบบ: ข้อมูลไหลจากข้อมูลดิบผ่าน Prefect DAG ไปจนถึง API ที่ให้บริการ แล้ว log จากการใช้งานจริงย้อนกลับมาที่ monitoring เพื่อสั่งเทรนใหม่

```mermaid
flowchart LR
    subgraph Source["แหล่งข้อมูล"]
        RAW[(Azure PdM CSV<br/>telemetry / errors /<br/>maint / failures / machines)]
    end

    subgraph DAG["Prefect DAG: pdm-training-pipeline"]
        direction LR
        ING[ingest<br/>+ data version] --> VAL{validate<br/>Pandera schema}
        VAL -- ไม่ผ่าน --> STOP[หยุด pipeline<br/>+ report + alert]
        VAL -- ผ่าน --> FE[build_features<br/>+ labels]
        FE --> SPL[split ตามเวลา<br/>train / val / test]
        SPL --> TR[train 4 โมเดล<br/>rule, logreg, RF, XGB]
        TR --> EV{gate บน test<br/>recall, precision,<br/>latency, size,<br/>ชนะ champion}
        EV -- ไม่ผ่าน --> REJ[registry: rejected]
        EV -- ผ่าน --> REG[registry: champion]
    end

    subgraph MLflow["MLflow"]
        TRK[(Tracking<br/>6 อย่างต่อ run)]
        MR[(Model Registry<br/>alias champion)]
    end

    subgraph Serve["Serving (Docker)"]
        API[FastAPI x4 workers<br/>/predict /batch /health /metrics]
        BATCH[batch scoring ทุกกะ]
    end

    subgraph Mon["Monitoring"]
        LOG[(prediction log<br/>+ feedback)]
        PROM[Prometheus + alert rules]
        GRAF[Grafana]
        DRIFT{drift check<br/>PSI + live recall}
    end

    RAW --> ING
    TR -.log.-> TRK
    EV -.log.-> TRK
    REG --> MR
    REJ --> MR
    MR -- load champion --> API
    MR --> BATCH
    USER([ระบบโรงงาน / ช่าง]) -- telemetry 24 ชม. --> API
    API -- risk --> USER
    API --> LOG
    API -- /metrics --> PROM --> GRAF
    LOG --> DRIFT
    DRIFT -- drift --> RT[Prefect: pdm-retrain-on-drift]
    RT --> TR

    subgraph CI["GitHub Actions"]
        C1[code quality] --> C3[model gate]
        C2[data validation] --> C3
        C1 --> C4[docker build]
    end
```

## จุดสำคัญที่ต้องอธิบายได้

| ประเด็น | กลไก | ไฟล์ |
|---|---|---|
| กัน Training-Serving Skew | API เรียก `build_features()` ฟังก์ชันเดียวกับตอนเทรน, preprocessing อยู่ใน sklearn `Pipeline` ที่บันทึกเป็น artifact เดียว, cleaning ใช้ค่าคงที่จาก config ไม่ fit จากข้อมูล | `features/build.py`, `modeling/models.py`, `tests/test_skew.py` |
| ข้อมูลเสียทำให้ระบบหยุด | `validate_or_raise()` raise exception ทำให้ Prefect flow หยุด, เขียน report, ส่ง webhook | `validation/validate.py` |
| ทำซ้ำได้ | split ตามวันที่ใน config, `seed: 42`, data version = hash ของไฟล์, เวอร์ชันไลบรารีครบใน `requirements.lock` | `configs/params.yaml` |
| ด่านตรวจก่อนขึ้นใช้งาน | gate 5 ข้อบน test set, โมเดลที่ไม่ผ่านถูกเก็บใน registry เป็น `rejected` | `registry/evaluate.py`, `registry/register.py` |
| ย้อนกลับ | ย้าย alias `champion` ไปเวอร์ชันก่อนหน้า, API ทุก worker poll registry ทุก 15 วินาที | `registry/register.py`, `serving/app.py` |
| รูปแบบการให้บริการ | real-time (เครื่องเดียว) + batch ทุกกะ (ทั้งโรงงาน), 4 worker process เพื่อเลี่ยง GIL | `serving/app.py`, `serving/batch.py` |
| แยก Data Drift กับ Concept Drift | data drift = PSI ของ input, concept drift = live recall ตกแต่ input ปกติ | `monitoring/monitor.py`, `monitoring/retrain_policy.py` |
