"""JARVIS - API 키가 필요 없는 개인 비서 웹앱 (FastAPI).

명령 이해는 LLM 없이 키워드/정규식 기반 의도 분류(intent parsing)로 처리한다.
"""
import ast
import operator
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "jarvis.db"))
APP_VERSION = os.environ.get("APP_VERSION", "dev")  # Docker 빌드 시 커밋 SHA가 들어감

try:
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except Exception:  # tzdata가 없는 환경 대비
    KST = timezone(timedelta(hours=9))

app = FastAPI(title="JARVIS Personal Assistant")


# ---------------------------------------------------------------- DB
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,          -- 'todo' | 'memo'
            no INTEGER NOT NULL,         -- 사용자별 표시 번호
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created TEXT NOT NULL
        )"""
    )
    return conn


def add_item(user, kind, text):
    with db() as c:
        row = c.execute(
            "SELECT COALESCE(MAX(no),0)+1 AS n FROM items WHERE user_id=? AND kind=?",
            (user, kind),
        ).fetchone()
        c.execute(
            "INSERT INTO items(user_id,kind,no,text,created) VALUES(?,?,?,?,?)",
            (user, kind, row["n"], text, datetime.now(KST).isoformat()),
        )
        return row["n"]


def list_items(user, kind):
    with db() as c:
        return c.execute(
            "SELECT no,text,done FROM items WHERE user_id=? AND kind=? ORDER BY no",
            (user, kind),
        ).fetchall()


def update_item(user, kind, no, done=None, delete=False):
    with db() as c:
        row = c.execute(
            "SELECT id,text FROM items WHERE user_id=? AND kind=? AND no=?",
            (user, kind, no),
        ).fetchone()
        if not row:
            return None
        if delete:
            c.execute("DELETE FROM items WHERE id=?", (row["id"],))
        else:
            c.execute("UPDATE items SET done=? WHERE id=?", (done, row["id"]))
        return row["text"]


# ---------------------------------------------------------------- 계산기
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expr: str):
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("지수가 너무 큽니다")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("지원하지 않는 식입니다")

    return ev(ast.parse(expr, mode="eval"))


def normalize_expr(text: str) -> str:
    t = text.replace("×", "*").replace("÷", "/").replace("^", "**").replace(",", "")
    t = re.sub(r"(?<=\d)\s*[xX]\s*(?=\d)", "*", t)
    return t.strip()


def fmt_number(v):
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, float):
        v = round(v, 6)
    return f"{v:,}" if isinstance(v, int) else str(v)


# ---------------------------------------------------------------- 의도 처리
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
JOKES = [
    "제가 가장 좋아하는 운동은 숨쉬기 운동입니다. 서버는 숨을 안 쉬지만요.",
    "개발자가 바다에 안 가는 이유를 아십니까? C가 없어서요.",
    "버그가 아니라 기능입니다. 아마도요.",
    "오류가 없는 코드는 아직 테스트하지 않은 코드입니다.",
]
HELP = (
    "저는 이런 일을 도와드릴 수 있습니다.\n"
    "• 할 일: '할 일 추가 우유 사기', '할 일 목록', '1번 완료', '2번 삭제'\n"
    "• 메모: '메모 와이파이 비번 1234', '메모 목록', '메모 1번 삭제'\n"
    "• 타이머: '타이머 5분', '1분 30초 타이머'\n"
    "• 시간/날짜: '지금 몇 시야?', '오늘 날짜'\n"
    "• 계산: '계산 3*(4+2)', '12 x 7'\n"
    "• 그 밖에: '안녕', '농담 해줘'"
)


def reply(text, action=None):
    return {"reply": text, "action": action}


def fmt_list(rows, title):
    if not rows:
        return f"{title}이(가) 비어 있습니다."
    lines = []
    for r in rows:
        mark = "✔ " if r["done"] else ""
        lines.append(f"{r['no']}. {mark}{r['text']}")
    return f"{title}입니다.\n" + "\n".join(lines)


def handle(message: str, user: str):
    text = message.strip()
    if not text:
        return reply("명령을 입력해 주세요.")
    low = text.lower()

    # 도움말
    if re.search(r"도움|뭘\s*할\s*수|무엇을\s*할|기능|help", low):
        return reply(HELP)

    # 타이머
    if re.search(r"타이머|알람|알림", text):
        h = re.search(r"(\d+)\s*시간", text)
        m = re.search(r"(\d+)\s*분", text)
        s = re.search(r"(\d+)\s*초", text)
        sec = (int(h.group(1)) * 3600 if h else 0) + (int(m.group(1)) * 60 if m else 0) + (
            int(s.group(1)) if s else 0
        )
        if sec <= 0:
            return reply("몇 분으로 맞출까요? 예: '타이머 5분'")
        if sec > 24 * 3600:
            return reply("타이머는 최대 24시간까지 설정할 수 있습니다.")
        return reply(
            f"타이머를 {describe_seconds(sec)}으로 설정했습니다.",
            {"type": "timer", "seconds": sec},
        )

    # 메모 / 할 일 번호 지정 완료·삭제
    kind = "memo" if "메모" in text else "todo"
    num = re.search(r"(\d+)\s*번", text)
    if num and re.search(r"완료|끝냈|끝났|done", low):
        n = int(num.group(1))
        t = update_item(user, "todo", n, done=1)
        return reply(f"'{t}' 항목을 완료 처리했습니다." if t else f"{n}번 할 일을 찾지 못했습니다.")
    if num and re.search(r"삭제|지워|제거|없애", text):
        n = int(num.group(1))
        t = update_item(user, kind, n, delete=True)
        label = "메모" if kind == "memo" else "할 일"
        return reply(f"{label} '{t}'을(를) 삭제했습니다." if t else f"{n}번 {label}을(를) 찾지 못했습니다.")

    # 메모
    if "메모" in text:
        if re.search(r"목록|보여|뭐|알려|리스트|확인|전부|모두", text) or re.fullmatch(r"\s*메모\s*", text):
            return reply(fmt_list(list_items(user, "memo"), "메모 목록"))
        m = re.search(r"메모\s*(?:추가|저장|해줘|해|:)?\s*[:：]?\s*(.+)", text)
        body = m.group(1).strip() if m else ""
        body = re.sub(r"(?:라고|을|를)?\s*(?:메모|저장)\s*(?:해\s*줘|해줘|해)?$", "", body).strip()
        if body:
            n = add_item(user, "memo", body)
            return reply(f"메모 {n}번으로 저장했습니다: {body}")
        return reply("저장할 내용을 알려주세요. 예: '메모 회의는 3시'")

    # 할 일
    if re.search(r"할\s*일|todo|투두", low):
        m = re.search(r"할\s*일\s*(?:추가|등록|:)\s*[:：]?\s*(.+)", text) or re.search(
            r"(.+?)\s*(?:을|를)?\s*할\s*일(?:에|로|목록에)?\s*(?:추가|등록|넣어)", text
        )
        if m:
            body = m.group(1).strip()
            n = add_item(user, "todo", body)
            return reply(f"할 일 {n}번에 추가했습니다: {body}")
        return reply(fmt_list(list_items(user, "todo"), "할 일 목록"))

    # 시간 / 날짜
    now = datetime.now(KST)
    if re.search(r"몇\s*시|현재\s*시간|지금\s*시간|시각", text):
        ampm = "오전" if now.hour < 12 else "오후"
        h12 = now.hour % 12 or 12
        return reply(f"현재 시각은 {ampm} {h12}시 {now.minute}분입니다.")
    if re.search(r"날짜|며칠|무슨\s*요일|오늘", text):
        return reply(f"오늘은 {now.year}년 {now.month}월 {now.day}일 {WEEKDAYS[now.weekday()]}요일입니다.")

    # 계산
    expr = None
    m = re.match(r"\s*계산\s*[:：]?\s*(.+)", text)
    if m:
        expr = m.group(1)
    else:
        cand = normalize_expr(text.rstrip("=? "))
        if re.fullmatch(r"[\d\s+\-*/().%]+", cand) and re.search(r"\d\s*[-+*/%]\s*\d|\*\*", cand):
            expr = cand
    if expr is not None:
        try:
            return reply(f"결과는 {fmt_number(safe_eval(normalize_expr(expr)))}입니다.")
        except ZeroDivisionError:
            return reply("0으로 나눌 수는 없습니다.")
        except Exception:
            return reply("계산식을 이해하지 못했습니다. 예: '계산 3*(4+2)'")

    # 잡담
    if re.search(r"농담|웃겨|재밌는", text):
        return reply(random.choice(JOKES))
    if re.match(r"\s*(안녕|하이|헬로|hello|hi|자비스)", low):
        hour = now.hour
        part = "좋은 아침입니다" if hour < 12 else "좋은 오후입니다" if hour < 18 else "좋은 저녁입니다"
        return reply(f"{part}, 사장님. 무엇을 도와드릴까요?")
    if re.search(r"고마워|감사", text):
        return reply("별말씀을요. 언제든 불러주세요.")
    if re.search(r"누구|이름", text):
        return reply("저는 자비스, 당신의 개인 비서입니다. API 키 없이 이 서버 안에서 동작합니다.")

    return reply("죄송합니다, 아직 이해하지 못한 명령입니다. '도움말'이라고 말씀해 보세요.")


def describe_seconds(sec: int) -> str:
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}시간")
    if m:
        parts.append(f"{m}분")
    if s:
        parts.append(f"{s}초")
    return " ".join(parts)


# ---------------------------------------------------------------- API
class ChatIn(BaseModel):
    message: str
    user_id: str = "guest"


@app.post("/api/chat")
def chat(body: ChatIn):
    user = re.sub(r"[^A-Za-z0-9_-]", "", body.user_id)[:64] or "guest"
    return handle(body.message[:500], user)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION, "time": datetime.now(KST).isoformat()}


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
