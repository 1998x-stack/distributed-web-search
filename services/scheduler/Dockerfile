FROM python:3.12-slim
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir redis==6.4.0
COPY packages /app/packages
COPY services/scheduler /app/services/scheduler
CMD ["python","-m","services.scheduler.run"]
