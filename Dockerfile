FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Run as a normal user, not root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# --proxy-headers: behind Railway's proxy, trust X-Forwarded-Proto so the app knows the request
# was HTTPS (FORWARDED_ALLOW_IPS is read by uvicorn; set it to * on Railway). The login rate
# limit does NOT use this; it reads the client IP itself (see app/rate_limit.py).
# sh -c so that ${PORT} from Railway is expanded.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
