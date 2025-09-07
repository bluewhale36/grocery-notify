import os
import requests
from datetime import datetime, timedelta
import pprint

# ------------------------------
# 환경 변수 설정
# ------------------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DB_ID")

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")  # Pushover 앱 토큰
PUSHOVER_USER = os.getenv("PUSHOVER_USER")    # Pushover User Key

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# ------------------------------
# Notion DB 데이터 가져오기
# ------------------------------
def fetch_items():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    res = requests.post(url, headers=NOTION_HEADERS, json={}, timeout=10)
    res.raise_for_status()
    return res.json()

req_res = fetch_items()
res_list = [{"properties": item["properties"]} for item in req_res.get("results")]

today = datetime.today().date()
three_days_later = today + timedelta(days=3)

pprint.pprint(req_res)
print("="*70)
pprint.pprint(res_list)
print("="*70)


# ------------------------------
# Notion 필드 헬퍼
# ------------------------------
def get_title(item):
    title_prop = item["properties"]["Name"]["title"]
    if title_prop:
        return title_prop[0]["plain_text"]
    return "(제목 없음)"

def get_status(item):
    return item["properties"]["Status"]["status"]["name"]

def get_expire_date(item):
    expire = item["properties"]["Expire On"]["date"]["start"]
    return datetime.fromisoformat(expire).date() if expire else None

def get_balance_quantity(item):
    return item["properties"]["Balance Quantity with Unit"]["formula"].get("string")

def get_unit(item):
    rich_texts = item["properties"]["Unit"]["rich_text"]
    return rich_texts[0]["plain_text"] if rich_texts else ""

# ------------------------------
# 알림 메시지 작성
# ------------------------------
def build_alert_message(data):
    imminent = []   # 3일 이내 만료 예정
    expired = []    # 이미 지난 것

    for item in data:
        title = get_title(item)
        balance = get_balance_quantity(item)
        expire_on = get_expire_date(item)
        status = get_status(item)

        if expire_on is None:
            continue

        days_left = (expire_on - today).days

        if status in ("Consuming", "Before"):
            if 0 <= days_left <= 3:
                imminent.append(f"  • {title} | 잔여량: {balance} | D-{days_left} (~{expire_on})")
            if expire_on < today:
                expired.append(f"  • {title} | 잔여량: {balance} | D+{abs(days_left)} (~{expire_on})")

    messages = []
    if imminent:
        messages.append("⚠️ 3일 이내 만료 예정인 식료품이 있습니다:\n" + "\n".join(imminent))
    if expired:
        messages.append("❌ 소비기한이 지난 식료품이 있습니다 :\n" + "\n".join(expired))

    if not messages:
        return "오늘 사용할 식료품을 미리 확인해보세요"

    return "\n\n".join(messages)

# ------------------------------
# Pushover 알림 전송
# ------------------------------
def send_pushover(title, message):
    url = "https://api.pushover.net/1/messages.json"
    payload = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER,
        "title": title,
        "message": message
    }
    res = requests.post(url, data=payload, timeout=10)
    res.raise_for_status()
    return res.json()

# ------------------------------
# 실행
# ------------------------------
def lambda_handler(event, context):
    message = build_alert_message(res_list)
    print("[알림 메시지]\n", message)

    if PUSHOVER_TOKEN and PUSHOVER_USER:
        response = send_pushover("Grocery Alert", message)
        print("[Pushover 전송 완료]", response.get("status"))
    else:
        print("[경고] PUSHOVER_TOKEN 또는 PUSHOVER_USER 환경 변수가 설정되지 않음. 콘솔 출력만 수행합니다.")

def main():
    message = build_alert_message(res_list)
    print("[알림 메시지]\n", message)

    if PUSHOVER_TOKEN and PUSHOVER_USER:
        response = send_pushover("Grocery Alert", message)
        print("[Pushover 전송 완료]", response.get("status"))
    else:
        print("[경고] PUSHOVER_TOKEN 또는 PUSHOVER_USER 환경 변수가 설정되지 않음. 콘솔 출력만 수행합니다.")

if __name__ == "__main__":
    main()