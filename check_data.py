# check_data.py
import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

# 登录
login_data = {"username": "admin", "password": "admin123"}
r = requests.post(f"{BASE_URL}/api/auth/login", data=login_data)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("=" * 60)
print("数据检查")
print("=" * 60)

# 1. 检查文件操作（不加时间范围）
r = requests.get(f"{BASE_URL}/api/files/operations?limit=100", headers=headers)
files = r.json().get("items", [])
print(f"\n📁 文件操作总数: {len(files)} 条")
if files:
    print("最新5条:")
    for f in files[:5]:
        print(f"   - {f['operation']}: {f['file_name']} at {f['operation_time']}")

# 2. 检查今天的数据
today = datetime.now().strftime("%Y-%m-%d")
r = requests.get(
    f"{BASE_URL}/api/files/operations?start_date={today}&limit=100", headers=headers
)
today_files = r.json().get("items", [])
print(f"\n📁 今天文件操作: {len(today_files)} 条")

# 3. 检查所有员工ID
employee_ids = set()
for f in files:
    employee_ids.add(f.get("employee_id"))
print(f"\n👥 员工ID列表: {employee_ids}")

print("\n" + "=" * 60)
