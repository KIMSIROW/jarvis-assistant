FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
COPY static/ ./static/

# 배포된 버전 확인용 (CI에서 커밋 SHA를 전달)
ARG GIT_SHA=dev
ENV APP_VERSION=$GIT_SHA \
    DB_PATH=/data/jarvis.db

RUN mkdir -p /data
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
