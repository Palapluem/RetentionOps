# บันทึกเรียนรู้ RetentionOps — 3 พฤศจิกายน 2026

## รอบต่อยอด: events และ point-in-time features

เพิ่ม `events.py` เป็น Module ที่รับ events/วัน freeze/วันที่ source ครอบคลุม แล้วคืน
snapshot กับรายงานคุณภาพ Interface นี้ใช้ร่วมกันระหว่าง pipeline และ independent fixtures
ช่วยเก็บกติกา revision/window/label ไว้จุดเดียวโดยไม่สร้าง Adapter ที่ยังไม่มีงานใช้จริง

ตัวอย่างสำคัญใน `test_events.py`: failed payment เกิด 1 เม.ย. อยู่ใน lookback 90 วัน
ของ cutoff 30 มิ.ย. แต่ถ้า correction ที่รู้ภายใน cutoff แก้วันเกิดเป็น 31 มี.ค.
ต้องนำ revision ใหม่มาใช้ก่อนกรอง window มิฉะนั้นจะเผลอคืนค่า revision เก่าเข้ามานับ
ถ้า correction เพิ่งรู้ 1 ก.ค. ต้องไม่เปลี่ยน snapshot ของ 30 มิ.ย.

วันที่ cutoff ไม่รวมอยู่ใน feature window แต่วันต่ออายุที่ cutoff+30 รวมอยู่ใน label
เพราะเป็นคนละนิยามกัน `available_at` บอกว่าเรารู้ event เมื่อไร ต่างจากวันเกิด event
ส่วน watermark บอกว่าข้อมูลครอบคลุมถึงวันใด จึงจะสรุปว่าไม่มี renewal ได้อย่างมีเงื่อนไข
renewal ที่ส่งมาช้าต้องเลื่อน label availability และอาจไม่ผ่าน embargo ของ cohort ถัดไป
กรณีแก้ไขที่ลบ renewal ออกจากช่วงเวลา (เช่นเปลี่ยน `occurred_at`, `expiry_date` หรือ
tombstone) ก็ต้องเลื่อน availability เช่นกัน เพราะค่าป้าย churn ปัจจุบันอาศัย correction
ที่เพิ่งรู้ หากนับเฉพาะ revision ล่าสุดที่ยังเข้า window ข้อมูลอนาคตจะรั่วเข้าชุด train
โดยไม่เห็นวันแก้ไข จึงเพิ่ม fixture หลาย cohort ที่ให้ `temporal_split` ปฏิเสธกรณีนี้

รัน `retentionops events --customers 650` เพื่อสร้าง raw JSONL → validated features
→ CSV/Parquet → โมเดล/metrics → scores โดย Parquet เก็บวันเป็น DATE ไม่ใช่ข้อความ
raw events กับ feature hash ช่วยตรวจ replay/correction; เป็นข้อมูลจำลองทั้งหมด
เมื่อขยายสู่ GCS/BigQuery จะใช้สัญญาเดียวกัน แต่ยังต้องทดสอบ cloud integration จริง
ไม่สามารถใช้ local Parquet หรือ fake adapter เป็นหลักฐานว่า deploy แล้วได้

## Pipeline แรกที่แยกเป็นขั้นตอนรับเข้าและ replay

ก่อนหน้านี้คำสั่ง `events` สร้างข้อมูลแล้วทำทุกขั้นในคำสั่งเดียว ทำให้ยังไม่เห็นขอบเขต
ของการรับ source จริงในทางปฏิบัติ จึงเพิ่ม `generate-events` สำหรับสร้างไฟล์ JSONL,
`ingest-events` สำหรับรับไฟล์เข้า staging ตรวจ schema/identity/revision/watermark และเก็บ
immutable release, และ `run-events` สำหรับอ่าน release ที่มีอยู่แล้วไปทำ feature, train,
ประเมิน และ publish

manifest ของ event release เก็บ source ID, SHA-256, วันข้อมูลครบ, จำนวนแถว/เหตุการณ์จริง/
ลูกค้า และผล quality gate ก่อน atomic rename ส่วน feature release เชื่อมกลับไปยัง source
ด้วย hash อีกชั้น การรับไฟล์เดิมซ้ำจึงใช้ release เดิม; ไฟล์เสียหรือ quality ไม่ผ่านต้องหยุด
ก่อนปล่อย release ใหม่ การแยกนี้พิสูจน์ local intake/replay ได้ แต่ยังไม่ใช่ GCS object
generation, BigQuery bronze, IAM หรือ Cloud Run integration

ตัวอย่างคำสั่งอยู่ใน README และ `docs/OPERATIONS.md` โดยตั้งใจรับเฉพาะ event contract
สังเคราะห์ การรับ KKBox/ข้อมูลลูกค้าจริงต้องมี schema mapping, สิทธิ์ใช้ข้อมูล, label ที่
ยืนยันได้ และ cloud/account gate ก่อนพัฒนา adapter แยก

งานรอบแรกทำก่อนวันเริ่มตามแผนหนึ่งวัน เป้าหมายคือรันเส้นทางข้อมูลจนถึงหน้าจอให้ได้
พร้อมหลักฐานตรวจสอบ ไม่ใช่ประกาศว่าระบบ cloud หรือโมเดลข้อมูลจริงเสร็จแล้ว

## การรับข้อมูลและสัญญาข้อมูล — `src/retentionops/data.py`

ส่วนนี้สร้าง CSV จำลอง แล้วตรวจ schema, grain, ช่วงค่า และวันพร้อมใช้งานก่อนรับเข้า
เลือก Python/Pydantic เพราะข้อมูลทดลองเล็กและใช้สัญญาเดียวกับ API ได้ ส่วนการประมวลผล
ข้อมูลขนาดใหญ่จะใช้ Polars/PyArrow/SQL เมื่อมีงานนั้นจริง ข้อมูลออกเป็น snapshot ที่ผ่าน
การตรวจและ release ตาม SHA-256; รัน `retentionops all` และทดสอบด้วย `tests/test_data.py`

ตัวอย่าง: ลูกค้าเดียวกัน ณ 30 มิ.ย. ต้องมีแถวเดียว ถ้ารู้ข้อมูลแก้ไขวันที่ 1 ก.ค. จะใช้ทำนาย
ที่ cutoff 30 มิ.ย. ไม่ได้ แม้ event จะเกิดก่อนหน้านั้น การดูเฉพาะ event time จึงไม่พอ
NaN, Infinity, label ยังไม่ครบเวลาและ header แปลกต้องหยุดงานแทนการทิ้งเงียบ ๆ

ข้อแลกเปลี่ยน: snapshot ปัจจุบันมีค่า feature ที่จำลองขึ้นและวันที่ประกอบ การตรวจวันที่
ไม่ได้พิสูจน์ว่า feature คำนวณจาก event ถูกจริง งานถัดไปต้องมี event fixtures อิสระ
เมื่อขึ้น cloud จะเก็บ raw แบบ immutable ใน GCS และตรวจจำนวนแถวก่อนโหลด BigQuery

## การแบ่งเวลาและ baseline — `src/retentionops/training.py`

ใช้ มิ.ย.–ก.ค. ฝึก, ส.ค. validation, ก.ย. test เพื่อให้การประเมินเลียนแบบการเดินเวลา
label ของ ก.ค. พร้อมวันที่ 30 ส.ค. จึงใช้ฝึกก่อน cutoff ส.ค. ได้ ส่วน label ส.ค. พร้อม
30 ก.ย. ตรง cutoff test พอดี กติกาปัจจุบันเป็นระดับวันและยอมให้วันเท่ากัน
StandardScaler เรียนค่าเฉลี่ยจาก train เท่านั้น; ห้ามเห็น validation/test ตอน fit

เลือก Logistic Regression เพราะอธิบายง่ายและเป็นฐานให้ LightGBM เปรียบเทียบภายหลัง
constant-prior baseline ทำนายทุกคนด้วยอัตรา churn ของ train ช่วยดูว่าโมเดลมีประโยชน์
เกินการเดาค่าคงที่หรือไม่ AP เหมาะกับการจัดอันดับเมื่อ positive น้อย; Recall@10%
ถามว่าเมื่อทีมติดต่อลูกค้าได้สิบเปอร์เซ็นต์ จะครอบคลุมผู้ churn กี่ส่วน Brier/log loss
ช่วยดูคุณภาพ probability และ calibration bins เปรียบเทียบค่าทำนายกับสัดส่วนจริง

รัน `pytest tests/test_pipeline.py` เพื่อตรวจ scaler, chronology และคะแนนจากโมเดลที่บันทึก
ความล้มเหลวสำคัญคือ cohort มี class เดียว, label ยังไม่พร้อม, tune ด้วย test หรือเอา
คะแนน synthetic ไปอ้างผลลูกค้าจริง ลูกค้าซ้ำข้ามเดือนได้ จึงไม่ใช่การทดสอบลูกค้าใหม่
เมื่อขยายระบบให้ฝึกเป็น Cloud Run Job และใช้ validation เลือก candidate ก่อนเปิด test

## การทำซ้ำและ model version — `src/retentionops/pipeline.py`

เวอร์ชันไม่ได้ขึ้นกับข้อมูลอย่างเดียว แต่รวม code, feature schema, config, Python,
package versions และวัน freeze ด้วย เช่นแก้ C ของ Logistic Regression ต้องได้ model
identity ใหม่ แม้ CSV เดิม model checksum บอกว่าไฟล์ที่เก็บยังตรงกับ manifest หรือไม่
รอบเดิมที่รันซ้ำจะใช้ manifest เดิม รวม timestamp เดิม เพื่อไม่ปลอมว่าฝึกใหม่แล้ว

ข้อมูลเข้าเป็น snapshot ที่ตรวจแล้ว ข้อมูลออกคือ model.joblib, manifest และ scores
รัน CLI สองครั้งแล้วทดสอบว่าแถวไม่เพิ่ม การเสียหายของ artifact ต้องหยุดแทน overwrite
joblib สามารถรันโค้ดตอนโหลดได้ จึงโหลดเฉพาะไฟล์ที่เราสร้างและเชื่อถือ; API ไม่โหลดโมเดล
ข้อจำกัดคือรองรับ writer เดียวต่อ root และยังไม่มี remote registry/MLflow เมื่อขึ้น GCS
ต้องรักษา immutability, checksum และเส้นทาง promotion/rollback ที่ชัดเจน

## Atomic publication — `src/retentionops/storage.py`

SQLite เหมาะกับ demo เพราะไม่ต้องมี server หรือ credentials เก็บ release กับ predictions
แล้วเปลี่ยน active pointer ใน transaction เดียว ถ้าแถวสุดท้ายมี probability=2 งานต้อง
rollback ทั้งชุด ผู้ใช้ยังอ่านชุดล่าสุดที่ถูกต้อง ไม่ควรเห็น manifest ใหม่กับ scores เก่า

API อ่านหนึ่ง transaction และกรอง model_version เสมอ มิฉะนั้นรัน 150 คนแล้ว 200 คน
อาจแสดงปนกันเป็น 350 คน คีย์จริงคือ model × customer × cutoff; รันซ้ำไม่เพิ่มคีย์
ทดสอบด้วย `test_failed_transaction_rolls_back` และ `test_different_sources_are_isolated`
SQLite ไม่ใช่ warehouse production; เมื่อย้าย BigQuery ต้องออกแบบ staging/publish,
MERGE และตาราง release ให้รักษาความหมายเดียวกัน พร้อมตรวจจำนวนและต้นทุน query

## API และหน้าจอ — `src/retentionops/api.py`, `dashboard.html`

FastAPI อ่านเฉพาะผลที่ materialize แล้ว จึงไม่ฝึกโมเดลทุกครั้งที่เปิดหน้าเว็บ Pydantic
ระบุ field/ช่วงค่าให้ OpenAPI และตรวจ response ได้ `/health` หมายถึง process อยู่
ส่วน `/ready` ตรวจว่ามี publication ที่จำนวนแถวสอดคล้องกัน ไม่ได้แปลว่าข้อมูลสดวันนี้

รัน Uvicorn ตาม README และ `pytest tests/test_api.py` หน้าจอ fetch overview/risk จริง
แล้วสร้าง DOM ด้วย textContent เพื่อไม่เอาข้อมูลไปเป็น HTML ต้องแสดง loading, error,
retry และ provenance หากมีการเปลี่ยน publication ระหว่างสอง request ให้ retry
หน้า smoke นี้ยังไม่ใช่ Next.js product UI และไม่มี auth จึงเปิดเฉพาะ loopback
cloud ต้องมีสิทธิ์อ่าน governed views, จำกัด query bytes และทดสอบปฏิเสธคนไม่มีสิทธิ์

## CI และวิธีทำงานร่วมกัน — `.github/workflows/ci.yml`

Issue กำหนดขอบเขต/เกณฑ์ผ่าน → feature branch มีการแก้ไข → PR แสดงผลตรวจ → มนุษย์ review
ก่อน merge CI ติดตั้ง dependency ที่ pin พร้อม hash, รัน lint/test/pipeline/HTTP และ
container path โดยไม่ใช้ cloud credentials การมี YAML ยังไม่แปลว่า CI ผ่าน ต้องดู run จริง

requirements.lock ทำให้เลือกเวอร์ชันซ้ำได้ ส่วน hash ตรวจไฟล์ดาวน์โหลด ไม่ใช่การรับรองว่า
package ไม่มีช่องโหว่ จึงมี pip-audit อีกชั้น ความล้มเหลวจาก network ต้องระบุว่าตรวจไม่ได้
การ ignore Kit กับ data ป้องกันการ add โดยไม่ตั้งใจ และ tracked-file guard ตรวจซ้ำก่อน push
branch protection/Project board เป็นสถานะที่ต้องตรวจจาก GitHub ไม่ควรแต่งหลักฐาน

ขั้นถัดไปคือ review หลักฐาน Day 1 แล้วสร้าง event-derived features และ cloud plan ที่มี
ขอบเขต ค่าใช้จ่ายและ cleanup ชัดเจน ก่อนขออนุมัติสร้างทรัพยากรที่มีค่าใช้จ่าย

## รอบต่อยอด: analyst workspace, API contracts และ job publication

`serving.py` อ่าน Overview/Risk/Cohorts/Model status ภายใน transaction เดียวและคืน
`Workspace` ที่มี model version สอดคล้องกันทั้งชุด ช่วยตัดปัญหาอ่านสี่ endpoint ระหว่าง
มีการ publish แล้วได้ข้อมูลปนคนละเวอร์ชัน ตัวกรองเป็น query parameters ที่ validate แล้ว
และ SQL bind values เสมอ ไม่ต่อข้อความผู้ใช้เป็น SQL รายละเอียดลูกค้า pin model version
จึงไม่กระโดดไปใช้ผลชุดใหม่ขณะเปิด dialog

เพิ่ม feature snapshots ที่ grain model × customer × cutoff และตรวจคีย์ที่เชื่อมกับ scores
การนับแถวเท่ากันยังไม่พอ เช่นแทน ID ลูกค้าหนึ่งรายด้วย ID ใหม่ จำนวนเท่าเดิมแต่ join ไม่ครบ
publisher ต้อง reject และ readiness ต้องไม่ผ่าน หลักฐานอยู่ใน `tests/test_workspace.py`
`runs.py` บันทึก job attempts จริง โดย successful state commit พร้อม publication ส่วน
exception บันทึก failed แล้วเก็บ active result เดิม การหยุด process แบบ kill ยังต้องดู
run ที่ค้าง running และ replay ด้วยผู้ปฏิบัติ ไม่ใช่อ้างว่าเป็น durable cloud orchestration
API `/api/v1/jobs` อ่านประวัติ attempt ได้แยกจาก active publication เพื่อให้ผู้ใช้เห็น
ความล้มเหลวครั้งแรกตอนยังไม่มี release; หน้า error จะบอกสถานะ publication จากข้อมูลนี้

Next.js อยู่ใน `apps/web/` ใช้ TypeScript, React และ CSS ที่ควบคุมจาก tokens เดียว
เลือกเพราะเหมาะกับ UI หลายหน้าที่เชื่อม typed backend และสร้าง production container ได้
ข้อมูลเข้าเป็น workspace JSON ผ่าน same-origin proxy; ข้อมูลออกเป็นตัวกรอง ตาราง กราฟ
cohort และ lineage ที่อ่านได้ ไม่มีการฝึกโมเดลจากการเปิดเว็บ ไม่มีการประเมิน uplift
API URL อยู่ฝั่ง server และ proxy อนุญาตเฉพาะ path ที่กำหนด ไม่รับ URL ปลายทางจากผู้ใช้

สัญญาเริ่มที่ Pydantic → OpenAPI → schema types ของ frontend ผ่าน `export_contracts.py`
ตัว exporter รองรับ primitives, enums, arrays, objects, unions และ local references ที่ใช้จริง
ถ้ามี schema construct ใหม่ที่ไม่รองรับจะหยุด generation ให้เพิ่ม test ก่อน ไม่ปล่อยชนิด
ข้อมูลผิดเงียบ ๆ Runtime response validation ยังอยู่ที่ FastAPI; TypeScript ไม่ใช่ runtime validator

รัน `npm run lint`, `npm run typecheck`, `npm run build` ใน apps/web และทดสอบด้วย
`npm run test:e2e` หลัง activate Python venv Browser tests ใช้ production standalone server
กับ API และ pipeline จริงของ fixture 150 ลูกค้า ตรวจตัวเลขจาก API, filter, pagination,
model pinning, loading/error/retry, mobile overflow, keyboard และ axe accessibility
ในงานทดสอบพบว่า hint ของ metrics ต้องอยู่ภายใน dd และชื่อที่ screen reader อ่านต้องมี
ข้อความที่มองเห็นของปุ่มกราฟ ตารางที่เลื่อนแนวนอนต้องมี keyboard focus target ด้วย

ข้อแลกเปลี่ยน: UI ใช้ workspace response เดียวและ client interactions ที่ไม่มี chart library
เหมาะกับข้อมูลทดลองขนาดนี้; ขยายจริงควร materialize/cache governed warehouse summaries
แทน scan JSON ทุก request ส่วน job และ SQLite เป็น local implementation ที่รัน writer เดียว
เมื่อขึ้น GCP ต้องเปลี่ยน storage/identity และทดสอบ integration/rollback/cost จริง
บัญชี GCP ยังไม่ได้สมัคร จึงเตรียมแผนทรัพยากรกับคู่มือโดยไม่มีการ provision หรือเปิด billing

## 4 พฤศจิกายน — เปรียบเทียบ LightGBM โดยไม่แตะ test ตอนเลือก

เพิ่ม LightGBM แบบ CPU deterministic และ grid ที่กำหนดไว้สามชุด โดย fit candidate จาก
train cohorts เท่านั้น แล้วใช้ validation average precision เลือกทั้ง model family และ
parameters ถ้าคะแนนเสมอกันจะคง Logistic Regression ก่อน จากนั้น freeze ผลเลือกแล้วจึงวัด
test ของโมเดลที่เลือกและ reference ที่ยังไม่ซ้ำกับตัวเลือก: constant-prior เสมอ และ
Logistic Regression เมื่อ LightGBM ชนะ
ไม่มีการเอา validation มารวม train ซ้ำ และไม่ประเมิน LightGBM ที่แพ้บน test

ทดสอบ leakage seam ด้วยการกลับ label ของ test cohort ทั้งชุดโดยยังมีสอง class: selection,
validation metrics และ probability ที่โมเดลทำนายต้องเหมือนเดิม เพิ่มอีกเส้นทางทดสอบว่า
joblib artifact ให้คะแนนตรงกับ SQLite และ rerun ใช้ model version/checksum เดิม พร้อมมีหนึ่ง
แถวต่อ model × customer × cutoff ใน storage เดิม การ publish ยังใช้ transaction เดิม
และ API overview อ่าน metric ของโมเดลที่ active ส่วน manifest รุ่นเก่าที่ไม่มี key ใหม่ยัง
อ่าน Logistic Regression ได้

หลักฐานรัน 650 customers วันที่ 4 พ.ย. บน snapshots และ event-derived synthetic data เลือก
Logistic Regression ทั้งคู่ ค่า validation AP ของ events คือ LR 0.3093 เทียบ LightGBM สามชุด
0.2984, 0.2948 และ 0.3022 ส่วน event-derived test AP คือ 0.2515 เทียบ constant-prior
0.1600; Brier 0.1317, ROC-AUC 0.6780 และ Recall@10% 0.1827 ตัวเลขนี้ตรวจเส้นทางและ
วิธีประเมินบนข้อมูลจำลองเท่านั้น ไม่ใช่ KKBox, ลูกค้าจริง หรือหลักฐาน campaign uplift

เก็บ candidate result, config ที่เลือก, source/feature/code/dependency identity, seed และ
model checksum ใน immutable local manifest แทนการเพิ่ม MLflow ในงานขนาดนี้ งาน batch บน
Cloud Run/BigQuery ยังติด issue #2 และไม่ถือว่าผ่านจากการทดสอบ local

### ตรวจ test seams ของ LightGBM และการ publish

ยืนยันขอบเขตผ่าน public API สองจุด: `train_selected` และ `run_pipeline`/`publish` โดยไม่
mock estimator ภายใน การกลับ label ของ test cohort ต้องคง candidate, parameters และ
probability ที่เลือกไว้ ส่วนการกลับ label ของ validation cohort เปลี่ยน candidate และ
parameters ได้ตาม AP สูงสุดของ validation พร้อมยืนยันว่า test metrics ยังสะท้อน label ที่
ใช้ประเมิน

ที่ปลายทาง `run_pipeline` ต้อง batch-score จาก model artifact ที่เลือกจริง และ replay ต้อง
คงแถวเดิมทุกคอลัมน์ภายใต้ key model × customer × cutoff โดยไม่เพิ่ม key ซ้ำ เพิ่ม guard
ที่ `publish` ให้ปฏิเสธ payload คะแนนที่ขัดกับ immutable model release; transaction ต้อง
rollback และรักษาทั้งคะแนนเดิมกับ active release ก่อนหน้า

หลักฐานรอบนี้อยู่ใน `docs/evidence/ML_TEST_SEAMS_2026-11-04.md` ผลทั้งหมดเป็น synthetic
และ local; ไม่ใช่ผล KKBox, cloud integration หรือ production release evidence

## 7 พฤศจิกายน — ทบทวน Day 1–4 ก่อนเริ่ม API slice

ตรวจแผนกับ PR และรันซ้ำใน temporary roots: Day 1–4 ผ่านในขอบเขต synthetic/local ได้แก่
81 tests, Ruff check/format, snapshot/event pipeline, การรับ event แยกขั้นและ replay ซ้ำ
โดยได้ source release/model version เดิมและคะแนน 650 แถวที่ customer key ไม่ซ้ำ API
health/ready/overview/risk ผ่านใน TestClient ส่วน `/api/v1/model-status` ยังไม่มีใน branch
ที่ checkout อยู่และเป็นจุดเชื่อมของ API/dashboard slice ถัดไป

ยืนยันซ้ำว่า label ทั้งสองเส้นทางยังเป็นข้อมูลจำลอง: snapshot ใช้ seeded draw ส่วน event
นับการไม่ต่ออายุในช่วง 30 วันหลัง scheduled expiry ไม่มีแหล่ง ground-truth ที่ได้รับอนุญาต
สิทธิ์ KKBox หรือบัญชี GCP ที่ยืนยันแล้ว จึงห้ามอ้างผลลูกค้าจริงหรือการ deploy

หน้า Next.js สี่มุมมองอยู่ใน PR #9 และ CI browser ผ่าน แต่ PR ยังไม่ merge และหน้า
Data & model แสดง lineage/run history ไม่ใช่ telemetry ของ infrastructure การรวมกับ
LightGBM branch ยังมี conflict ใน API/pipeline/storage/docs; รายละเอียดและข้อจำกัดรอบนี้
บันทึกไว้ที่ `docs/evidence/DAYS1_4_REAUDIT_2026-11-07.md` การตรวจ pip-audit บนเครื่อง
ติด DNS ไป PyPI แต่ CI ล่าสุดผ่านขั้นตอน audit แล้ว
