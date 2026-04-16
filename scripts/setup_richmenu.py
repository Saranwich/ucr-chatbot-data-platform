import requests
import json
from app.config import IMAGES_DIR, CHANNEL_ACCESS_TOKEN

import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

# ดึง Path รูปมาจาก config
IMAGE_PATH = IMAGES_DIR / "rich_menu.jpg"

if not CHANNEL_ACCESS_TOKEN:
    print("❌ Error: ไม่พบ CHANNEL_ACCESS_TOKEN ในไฟล์ .env")
    exit()

if not IMAGE_PATH.exists():
    print(f"❌ Error: ไม่พบไฟล์รูปภาพที่ {IMAGE_PATH}")
    exit()

HEADERS_JSON = {
    "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

def create_and_deploy_richmenu():
    print("🚀 เริ่มขั้นตอนการสร้าง Custom Rich Menu (4 ปุ่ม)...")

    # 1. กำหนดโครงสร้าง Rich Menu
    rich_menu_data = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "Custom 4-Button Menu",
        "chatBarText": "เปิดเมนู",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 625, "height": 843},
                "action": {"type": "message", "text": "เริ่มทำแบบสำรวจ"} # ปุ่ม 1
            },
            {
                "bounds": {"x": 625, "y": 0, "width": 625, "height": 843},
                "action": {"type": "message", "text": "แจ้งปัญหา"} # ปุ่ม 2
            },
            {
                "bounds": {"x": 1250, "y": 0, "width": 625, "height": 843},
                "action": {"type": "message", "text": "ติดต่อ"} # ปุ่ม 3
            },
            {
                "bounds": {"x": 1875, "y": 0, "width": 625, "height": 843},
                "action": {"type": "message", "text": "สรุปผล"} # ปุ่ม 4
            }
        ]
    }

    # 2. ส่งคำสั่งสร้าง Rich Menu เพื่อเอา ID
    response = requests.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS_JSON,
        data=json.dumps(rich_menu_data)
    )
    
    if response.status_code != 200:
        print("❌ สร้าง Rich Menu ไม่สำเร็จ:", response.text)
        return

    rich_menu_id = response.json().get("richMenuId")
    print(f"✅ สร้าง Rich Menu สำเร็จ! ได้ ID: {rich_menu_id}")

    # 3. อัปโหลดรูปภาพเข้าไปที่ ID นี้
    print("📤 กำลังอัปโหลดรูปภาพ...")
    with open(IMAGE_PATH, 'rb') as f:
        image_data = f.read()
        
    headers_image = {
        "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "image/jpeg"
    }
    
    upload_res = requests.post(
        f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
        headers=headers_image,
        data=image_data
    )
    
    if upload_res.status_code != 200:
        print("❌ อัปโหลดรูปไม่สำเร็จ:", upload_res.text)
        return
        
    print("✅ อัปโหลดรูปภาพสำเร็จ!")

    # 4. ตั้งให้ Rich Menu นี้เป็นค่าเริ่มต้นสำหรับทุกคนที่แอดบอท
    print("✨ กำลังตั้งเป็นเมนูเริ่มต้น...")
    set_default_res = requests.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
        headers=HEADERS_JSON
    )

    if set_default_res.status_code == 200:
        print(f"🎉 เสร็จสมบูรณ์! ตอนนี้บอทของคุณใช้ Rich Menu 4 ปุ่มแล้วครับ!")
    else:
        print("❌ ตั้งเป็นเมนูเริ่มต้นไม่สำเร็จ:", set_default_res.text)

if __name__ == "__main__":
    create_and_deploy_richmenu()