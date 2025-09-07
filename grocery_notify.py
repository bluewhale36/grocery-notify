import os
import requests
from datetime import datetime, timedelta

# ------------------------------
# 환경 변수 설정
# ------------------------------
NOTION_TOKEN = os.getenv("NOTION_TOKEN_GROCERY")
DATABASE_ID = os.getenv("NOTION_GROCERY_DB_ID")

PUSHOVER_TOKEN = os.getenv("PUSHOVER_TOKEN")  # Pushover 앱 토큰
PUSHOVER_USER = os.getenv("PUSHOVER_USER")    # Pushover User Key

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def fetch_items():
    """
    Notion 데이터베이스에서 식료품 아이템 데이터를 조회합니다.
    - 매개변수: 없음
    - 리턴값: Notion API에서 반환된 JSON 데이터(dict)
    Notion API에 POST 요청을 보내 식료품 목록을 받아옵니다.
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    res = requests.post(url, headers=NOTION_HEADERS, json={}, timeout=10)
    res.raise_for_status()
    return res.json()

# Notion에서 아이템 데이터 조회 후, 필요한 properties만 추출
req_res = fetch_items()
res_list = [{"properties": item["properties"]} for item in req_res.get("results")]

today = datetime.today().date()
three_days_later = today + timedelta(days=3)

def get_title(item):
    """
    각 아이템에서 제목(Name) 필드를 추출합니다.
    - item: Notion에서 가져온 아이템 데이터(dict)
    - 리턴값: 아이템의 제목(str)
    제목이 없는 경우 "(제목 없음)"을 반환합니다.
    """
    title_prop = item["properties"]["Name"]["title"]
    if title_prop:
        return title_prop[0]["plain_text"]
    return "(제목 없음)"

def get_status(item):
    """
    각 아이템에서 상태(Status) 필드를 추출합니다.
    - item: Notion에서 가져온 아이템 데이터(dict)
    - 리턴값: 상태명(str)
    """
    return item["properties"]["Status"]["status"]["name"]

def get_expire_date(item):
    """
    각 아이템에서 만료일(Expire On) 필드를 추출합니다.
    - item: Notion에서 가져온 아이템 데이터(dict)
    - 리턴값: 만료일(date) 또는 None
    만료일 정보가 없을 경우 None을 반환합니다.
    """
    expire = item["properties"]["Expire On"]["date"]["start"]
    return datetime.fromisoformat(expire).date() if expire else None

def get_balance_quantity(item):
    """
    각 아이템에서 잔여 수량(Balance Quantity with Unit) 필드를 추출합니다.
    - item: Notion에서 가져온 아이템 데이터(dict)
    - 리턴값: 잔여 수량 및 단위가 포함된 문자열(str)
    """
    return item["properties"]["Balance Quantity with Unit"]["formula"].get("string")

def get_unit(item):
    """
    각 아이템에서 단위(Unit) 필드를 추출합니다.
    - item: Notion에서 가져온 아이템 데이터(dict)
    - 리턴값: 단위 문자열(str)
    단위 정보가 없을 경우 빈 문자열을 반환합니다.
    """
    rich_texts = item["properties"]["Unit"]["rich_text"]
    return rich_texts[0]["plain_text"] if rich_texts else ""

def build_alert_message(data):
    """
    조회한 데이터에서 만료 임박 및 만료된 식료품을 분류하여 알림 메시지를 생성합니다.
    - data: Notion에서 추출한 식료품 데이터 리스트(list)
    - 리턴값: 알림 메시지 문자열(str)
    만료 임박(3일 이내) 및 이미 만료된 식료품을 구분하여 메시지를 작성합니다.
    """
    imminent = []   # 3일 이내 만료 예정 아이템 리스트
    expired = []    # 이미 만료된 아이템 리스트

    for item in data:
        title = get_title(item)
        balance = get_balance_quantity(item)
        expire_on = get_expire_date(item)
        status = get_status(item)

        if expire_on is None:
            continue

        days_left = (expire_on - today).days

        # 상태가 'Consuming' 또는 'Before'인 경우에만 알림 대상에 포함
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

def send_pushover(title, message):
    """
    Pushover API를 통해 푸시 알림 메시지를 전송합니다.
    - title: 알림 제목(str)
    - message: 알림 내용(str)
    - 리턴값: Pushover API 응답(JSON, dict)
    PUSHOVER_TOKEN과 PUSHOVER_USER 환경 변수 필요.
    """
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

def lambda_handler(event, context):
    """
    AWS Lambda 환경에서 호출되는 메인 함수입니다.
    - event: Lambda 이벤트 객체
    - context: Lambda 컨텍스트 객체
    - 리턴값: 없음
    알림 메시지를 생성하고 Pushover로 전송하거나 콘솔에 출력합니다.
    """
    message = build_alert_message(res_list)
    print("[알림 메시지]\n", message)

    if PUSHOVER_TOKEN and PUSHOVER_USER:
        response = send_pushover("Grocery Alert", message)
        print("[Pushover 전송 완료]", response.get("status"))
    else:
        print("[경고] PUSHOVER_TOKEN 또는 PUSHOVER_USER 환경 변수가 설정되지 않음. 콘솔 출력만 수행합니다.")


def main():
    """
    스크립트를 직접 실행할 때 호출되는 메인 함수입니다.
    - 매개변수: 없음
    - 리턴값: 없음
    알림 메시지를 생성하고 Pushover로 전송하거나 콘솔에 출력합니다.
    """
    message = build_alert_message(res_list)
    print("[알림 메시지]\n", message)

    if PUSHOVER_TOKEN and PUSHOVER_USER:
        response = send_pushover("Grocery Alert", message)
        print("[Pushover 전송 완료]", response.get("status"))
    else:
        print("[경고] PUSHOVER_TOKEN 또는 PUSHOVER_USER 환경 변수가 설정되지 않음. 콘솔 출력만 수행합니다.")

if __name__ == "__main__":
    main()
