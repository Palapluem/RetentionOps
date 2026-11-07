# เตรียม Google Cloud โดยยังไม่สร้างทรัพยากร

สถานะ 3 พ.ย. 2026: เจ้าของยืนยันว่ายังไม่ได้สมัคร GCP; ไม่พบ gcloud/bq และไม่มีการสร้าง
project, เปิด billing, เปิด API หรือเปลี่ยน IAM ในงานนี้ ระบบ local/Docker ใช้ต่อได้ทันที

## สิ่งที่เจ้าของเตรียมเมื่อพร้อม

1. อ่านเงื่อนไขและสิทธิ์ของบัญชีที่ [Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features)
   แล้วสมัครด้วยบัญชี Google ของตนเอง ขั้นยืนยันตัวตน/วิธีชำระเงินให้เจ้าของทำเอง
   สิทธิ์ trial/free tier มีขอบเขต; ไม่ถือว่าระบบตามแผนจะไม่มีค่าใช้จ่ายเสมอ
2. เลือก project สำหรับ RetentionOps และแจ้ง Project ID กับ region ที่ต้องการโดยส่วนตัว
   แผนเสนอ `asia-southeast1` แต่ยังต้องตรวจบริการ/ตำแหน่งข้อมูล/ค่าใช้จ่ายก่อนยืนยัน
3. กำหนดงบและ spending allowance ในสกุลเงินที่ใช้จริง ตั้ง budget alerts ตาม
   [คู่มือ Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/budgets)
   สำหรับ alerts-only budget การแจ้งเตือนไม่ใช่ hard cap และไม่ใช่การหยุดค่าใช้จ่ายทันที
4. ตรวจแผน resource/IAM/cleanup ด้านล่างและให้อนุมัติอย่างชัดเจนก่อนสร้างทรัพยากร
   ที่มีค่าใช้จ่าย เปลี่ยน IAM สำคัญ หรือเปิดบริการสู่สาธารณะ ไม่มีสคริปต์ apply อัตโนมัติ

ไม่ต้องส่งรหัสผ่าน บัตรเครดิต tokens หรือ service-account JSON มาใน chat/repo/issues
บัญชี/งบที่ยังไม่กำหนดถูกบันทึกเป็น `null` ในแผนเพื่อไม่เดาหรืออ้างว่าผ่านแล้ว

## แผนทรัพยากรสำหรับตรวจ

ฉบับเครื่องอ่าน: [resource-plan.json](../infra/gcp/resource-plan.json) เป็น **แผนเท่านั้น**

| รายการ | ขอบเขตเสนอ | เงื่อนไขก่อนสร้าง |
|---|---|---|
| Artifact Registry | 1 repository สำหรับ images | เลือก region และตรวจ retention ของ image |
| GCS | 1 bucket ส่วนตัว แยก raw/features/models prefixes | Uniform access, public access prevention, versioning; ตรวจ lifecycle/rights |
| BigQuery | bronze/silver/gold/analytics/features | GCS กับ datasets อยู่ location ที่ใช้ร่วมกันได้; ใช้ partition predicates/query bytes limits |
| Cloud Run Jobs | ingest/train/score; task เดียว, retry จำกัด | แยก entrypoints/identities และผ่าน manual run/replay จริง |
| Cloud Run Services | private API และ web; min=0, max API=2/web=1 | ทดสอบสิทธิ์ invoker และ private service-to-service token |
| Cloud Scheduler | ยังปิด; Asia/Bangkok | เปิดหลังมี manual run evidence และ retry/concurrency policy |
| Logging/Monitoring | job failures, publication status, source age | กำหนด retention/alerts และไม่ log raw restricted data |

ยังไม่มีราคาประเมินที่วัดจริง ต้องใส่ปริมาณ GB, scan bytes, job seconds, requests และ
retention แล้วตรวจราคาปัจจุบันก่อนอนุมัติ จำนวน instances/query limits ลด exposure ได้
แต่ไม่ใช่การรับรองยอดบิลสูงสุดทั้งโครงการ

## Identity และการส่งมอบ

ใช้ GitHub Actions OIDC / Workload Identity Federation ตาม
[คู่มือ Google](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
จำกัดด้วย numeric repository/owner IDs และ main ref; ไม่สร้าง long-lived SA keys
แยก CI deployer, ingestion, training, scoring, API และ web identities

API อ่านเฉพาะ governed gold/analytics views; ingestion เขียน bronze; training อ่าน features
และเขียน models; scoring อ่าน approved model/features และเขียน scores เท่านั้น
CI deployer ไม่มี Owner/Editor กว้างทั้ง project; ตรวจ exact roles/resource scope ก่อน grant

**Deployment gate ที่ยังต้อง implement:** ตอนนี้ API ใช้ local SQLite และ web proxy ยังไม่มี
Cloud Run identity token จึงไม่ควรนำ image ไป deploy แล้วเรียกว่า cloud integration สำเร็จ
ต้องเพิ่ม GCS/BigQuery adapters, private authentication, bounded queries และทดสอบจริงก่อน
CD ปัจจุบันจึงตรวจ local/container/browser ใน CI; ยังไม่มี workflow ที่ provision/deploy cloud

## ตรวจและเก็บหลักฐานหลังอนุมัติ

ติดตั้ง SDK และรัน `python scripts/cloud_preflight.py` แบบ read-only ก่อน ตรวจบัญชีและ
project เป็นการส่วนตัว แล้วเก็บ redacted job IDs, revision IDs, row/hash reconciliation,
unauthorized-access tests และ query bytes/cost จริง Scheduler ใช้
[แนวทาง Cloud Run Jobs](https://docs.cloud.google.com/run/docs/execute/jobs-on-schedule)

Cleanup: ปิด schedules → ลบ services/jobs ที่อนุมัติ → ตรวจ images → ตรวจ GCS/BigQuery/log
retention → ตรวจยอดบิลหลังลบอีกครั้ง ห้ามลบข้อมูลที่ต้องเก็บหรือใช้สิทธิ์ Owner เป็นทางลัด
