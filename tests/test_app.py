import os
import tempfile

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


def ask(msg, user="t1"):
    r = client.post("/api/chat", json={"message": msg, "user_id": user})
    assert r.status_code == 200
    return r.json()


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_index_served():
    assert "J.A.R.V.I.S." in client.get("/").text


def test_greeting_and_help():
    assert "사장님" in ask("안녕")["reply"]
    assert "할 일" in ask("도움말")["reply"]


def test_calc():
    assert "18" in ask("계산 3*(4+2)")["reply"]
    assert "84" in ask("12 x 7")["reply"]
    assert "0으로" in ask("계산 1/0")["reply"]
    assert "이해하지" in ask("계산 __import__('os')")["reply"]


def test_timer():
    r = ask("1분 30초 타이머")
    assert r["action"] == {"type": "timer", "seconds": 90}


def test_todo_flow():
    ask("할 일 추가 우유 사기", "todo_user")
    ask("빨래하기 할 일에 추가해줘", "todo_user")
    lst = ask("할 일 목록", "todo_user")["reply"]
    assert "1. 우유 사기" in lst and "2. 빨래하기" in lst
    assert "완료" in ask("1번 완료", "todo_user")["reply"]
    assert "✔ 우유 사기" in ask("할 일 목록", "todo_user")["reply"]
    assert "삭제" in ask("2번 삭제", "todo_user")["reply"]
    assert "빨래하기" not in ask("할 일 목록", "todo_user")["reply"]


def test_memo_flow_and_user_isolation():
    ask("메모 와이파이 비번 1234", "memo_user")
    assert "1234" in ask("메모 목록", "memo_user")["reply"]
    assert "비어" in ask("메모 목록", "other_user")["reply"]


def test_time_date():
    assert "현재 시각" in ask("지금 몇 시야?")["reply"]
    assert "오늘은" in ask("오늘 날짜")["reply"]


def test_unknown_and_empty():
    assert "이해하지 못한" in ask("asdfgh")["reply"]
    assert "입력" in ask("   ")["reply"]
