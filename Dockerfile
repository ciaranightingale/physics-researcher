FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Mount a persistent volume at /data, or your posted-videos log is lost on every redeploy.
ENV DB_PATH=/data/scout.db
EXPOSE 8000
CMD ["sh", "-c", "uvicorn science_scout.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
