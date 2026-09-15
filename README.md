# UCR Smartcity Chatbot

บอทบน LINE OA (UCR / TONKIT Lab) ที่ชวนคนในชุมชนเล่าเรื่องสภาพแวดล้อมและ
โครงสร้างพื้นฐานแถวบ้าน แล้วสกัดออกมาเป็นรายงานพร้อมพิกัด ปลายทางคือหมุดบน
แผนที่ให้ทีมออกแบบเมืองใช้ตัดสินใจว่าควรปรับปรุงตรงไหนก่อน

## Admin

Run `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`, then open
`http://127.0.0.1:8000/admin/` for the map, report statistics, and manual broadcasts.

See [admin setup and API reference](admin/README.md) for configuration,
report attachments, broadcast behavior, and validation.
