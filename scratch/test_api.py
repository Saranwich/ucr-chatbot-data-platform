import requests
try:
    r = requests.get("http://127.0.0.1:8001/api/dashboard/reports?date=2026-04-30")
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")
