"""ค่า default ของทุกอย่างที่แอดมินปรับได้ระหว่างแอปรัน — ที่เดียวในแอป

ใช้ตอน db ยังไม่มีแถว active หรือแถวนั้นชี้ไปของที่ไม่มีอยู่
ช่วงค่าที่รับได้ไม่อยู่ที่นี่ อยู่ใน Field ของ schemas/ ตัวนั้น ๆ
ค่าคงที่ที่ไม่มีใครปรับ (TIMEOUT, endpoint) ก็ไม่อยู่ที่นี่
"""

# ================================================================ ai_config
# ต่อ agent หนึ่งตัว — key ต้องตรงกับช่องใน schemas/ai_config.py ทุกตัว

DEFAULT_AGENT_CONFIG = {
    "communicator": {
        "provider": "typhoon",
        "model_name": "typhoon-v2.5-30b-a3b-instruct",
        "temperature": 0.7,
        "max_output_tokens": 1024,
    },
    "analyzer": {
        "provider": "typhoon",
        "model_name": "typhoon-v2.5-30b-a3b-instruct",
        "temperature": 0.7,
        "max_output_tokens": 1024,
    },
    "resource_analyzer": {
        "provider": "typhoon",
        "model_name": "typhoon-v2.5-30b-a3b-instruct",
        "temperature": 0.7,
        "max_output_tokens": 1024,
    },
}


# ================================================================ system_config

DEFAULT_SESSION_TTL_SECONDS = 60 * 60   # เงียบไปชั่วโมงนึง บอทลืมบทสนทนา
