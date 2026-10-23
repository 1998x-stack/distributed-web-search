FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY services/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY packages /app/packages
COPY services/api /app/services/api
EXPOSE 8000
CMD ["uvicorn","services.api.main:app","--host","0.0.0.0","--port","8000"]
