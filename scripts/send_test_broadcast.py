"""
send_test_broadcast.py — ยิงข้อความ broadcast ทดสอบไปหา "user คนเดียว"

ใช้เช็คหน้าตาข้อความจริงบนมือถือ โดยไม่ต้อง multicast หาคนอื่น
(ใช้ endpoint `push` = ส่งหา 1 คน ไม่ใช่ `multicast` = ส่งหาหลายคน)

⚠️ ใช้กับ test OA เท่านั้น + ส่งหา user id ของตัวเอง — จะได้ไม่รบกวนคนใช้จริง

Usage:
    python scripts/send_test_broadcast.py --test-user Uxxxx --type flood
    python scripts/send_test_broadcast.py --test-user Uxxxx --type heat
    python scripts/send_test_broadcast.py --test-user Uxxxx --type both --dry-run
"""
import sys
import argparse
import requests
from pathlib import Path

# ให้ import app.* / scripts.* เจอ
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import app.config_loader                        # โหลดค่าใน .env เข้า env
from app.config import CHANNEL_ACCESS_TOKEN
from scripts.weather_broadcast import build_message


def push_to_user(user_id: str, messages: list[dict], token: str, dry_run: bool = False) -> None:
    """ส่งข้อความหา user คนเดียวผ่าน LINE push API"""
    if dry_run:
        print(f"[DRY RUN] จะส่งหา {user_id} — ไม่ยิงจริง")
        for m in messages:
            print("   •", m["type"], "→", m.get("text") or m.get("altText"))
        return

    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"to": user_id, "messages": messages},
        timeout=10,
    )
    if resp.status_code == 200:
        print("✅ ส่งสำเร็จ — เช็คที่มือถือได้เลย")
    else:
        print(f"❌ ส่งไม่สำเร็จ {resp.status_code}: {resp.text}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-user", required=True, help="LINE user id ของแก (Uxxxx)")
    parser.add_argument("--type", choices=["flood", "heat", "both"], default="flood")
    parser.add_argument("--dry-run", action="store_true", help="แค่ดู ไม่ส่งจริง")
    args = parser.parse_args()

    if not CHANNEL_ACCESS_TOKEN:
        print("❌ ไม่เจอ CHANNEL_ACCESS_TOKEN ใน .env")
        return

    messages = build_message(args.type)
    print(f"กำลังส่งแบบ '{args.type}' ไปหา {args.test_user}")
    push_to_user(args.test_user, messages, CHANNEL_ACCESS_TOKEN, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
