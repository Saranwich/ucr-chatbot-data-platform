# คง PostgreSQL ไว้ (hybrid relational + PostGIS + JSONB) — ไม่ย้ายไป NoSQL

มีการพิจารณาย้ายไป NoSQL เพราะคำตอบ survey เก็บเป็น `payload` JSONB ที่ schema ไม่ตายตัว
แต่ตัดสินใจ **คง Postgres ไว้** เพราะในตารางเดียวกันยังมี `location_data` เป็น PostGIS `Geometry(POINT, 4326)`
(หัวใจของโปรเจกต์: พล็อตแผนที่ / `ST_X`/`ST_Y` / วางผังชุมชน) บวกกับ FK `User → SurveySession → CompletedReport`
ที่เป็นความสัมพันธ์เชิงตารางจริง Postgres ให้ทั้ง relational + geospatial + document (JSONB) ในที่เดียว
ซึ่ง NoSQL ส่วนใหญ่ให้ครบสามอย่างนี้ไม่ได้ (โดยเฉพาะ geospatial ระดับ PostGIS) JSONB คือคำตอบของ schema-less อยู่แล้ว
จึงไม่มีความเจ็บจริงมารองรับการย้ายที่ย้อนยาก
