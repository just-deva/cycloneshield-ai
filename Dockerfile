# One container serves the API and the static UI. Build & deploy without local Docker:
#   gcloud run deploy cycloneshield --source . --region asia-south1 --allow-unauthenticated ...   (see docs/DEPLOY.md)
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# hazard engine is CPU-bound and keeps per-tenant arrays in memory: one worker, threads for concurrency
# --proxy-headers: Cloud Run terminates TLS, so request.base_url must reflect https (used for the self-webhook URL)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips="*"
