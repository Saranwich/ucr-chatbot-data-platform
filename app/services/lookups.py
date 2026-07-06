"""Single-source lookup lists (V2).

# ponytail: hardcoded in code for now — in M3 these become the seed data for the
# categories/communities tables + the profile dropdown source (one place, no drift
# between DB / dropdown / forecast — the 3-way spelling mismatch the DBML calls out).
"""

# 5 หมวดปัญหา (docs/db_redesign_v2.dbml — ตาราง categories)
CATEGORIES = [
    "ทางเท้าชำรุด",
    "ไฟฟ้าสาธารณะ",
    "ขยะ",
    "น้ำท่วม/น้ำขัง",
    "อากาศร้อน",
]

# 14 ชุมชน (เดิม hardcode ใน static/userdata_form.html — ย้ายมารวมที่เดียว)
COMMUNITIES = [
    "ชุมชนคนรักถิ่น",
    "ชุมชนหลังแฟลตร่วมพัฒนา",
    "ชุมชนหลักสี่พัฒนา 99",
    "ชุมชนคลองเปรมประชาพัฒนา",
    "ชุมชนศิษย์หลวงปู่ขาว",
    "ชุมชนตลาดหลักสี่",
    "ชุมชนแจ้งวัฒนะซอย 5",
    "ชุมชนมิตรประชาพัฒนา",
    "ชุมชนอยู่แล้วรวย",
    "ชุมชนอยู่ดีมีสุขร่วมใจ",
    "ชุมชนเทวสุนทร",
    "ชุมชนสามัคคีเทวสุนทร",
    "ชุมชนประชาร่วมใจ 1",
    "ชุมชนประชาร่วมใจ 2",
]
