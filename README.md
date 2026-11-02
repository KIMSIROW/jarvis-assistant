# J.A.R.V.I.S. – API 키 없는 개인 비서 웹앱

아이언맨의 자비스처럼 명령을 말하거나 입력하면 할 일·메모·타이머·시간·계산을 처리해 주는 개인 비서입니다.
**외부 LLM API나 API 키를 전혀 사용하지 않고**, 서버 안의 규칙 기반 의도 분류(키워드/정규식)로 동작합니다.

## 주요 기능
| 분류 | 예시 명령 |
|---|---|
| 할 일 | `할 일 추가 우유 사기` · `빨래하기 할 일에 추가해줘` · `할 일 목록` · `1번 완료` · `2번 삭제` |
| 메모 | `메모 와이파이 비번 1234` · `메모 목록` · `메모 1번 삭제` |
| 타이머 | `타이머 5분` · `1분 30초 타이머` (종료 시 음성 안내) |
| 시간/날짜 | `지금 몇 시야?` · `오늘 날짜` |
| 계산 | `계산 3*(4+2)` · `12 x 7` |
| 기타 | `안녕` · `농담 해줘` · `도움말` |

- 음성 입력/출력은 브라우저 내장 Web Speech API를 사용합니다(키 불필요, 크롬 계열 권장). 미지원 브라우저에서는 텍스트로 동작합니다.
- 사용자별 데이터는 브라우저가 만든 익명 ID로 구분해 SQLite에 저장합니다.

## 구조
```
app.py              FastAPI 백엔드 (의도 분류 + SQLite)
static/index.html   자비스 스타일 UI (HTML/CSS/JS)
tests/              pytest 테스트
render.yaml         Render 자동 배포 설정
.github/workflows/  GitHub Actions CI (push 시 테스트)
```

## 로컬 실행 (Windows PowerShell)
```powershell
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```
브라우저에서 http://127.0.0.1:8000 접속

## 테스트
```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

## 배포 (GitHub push → 자동 배포)
1. 이 폴더를 GitHub 저장소에 push합니다.
2. [Render](https://render.com)에서 **New → Blueprint**로 저장소를 연결하면 `render.yaml`을 읽어 서비스가 만들어집니다.
3. 이후 코드를 수정해 `git push`하면 Render가 자동으로 다시 빌드·배포합니다. 동시에 GitHub Actions가 테스트를 실행합니다.

> 무료 플랜의 파일시스템은 재배포/재시작 시 초기화될 수 있어 할 일·메모가 사라질 수 있습니다(과제용 데모 기준).

## 모델 준비
사전 학습 모델이나 API 키는 필요하지 않습니다.
