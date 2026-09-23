FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TASK_DB_PATH=/data/tasks.db

WORKDIR /workspace

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 benchmark \
    && mkdir --parents /data \
    && chown --recursive benchmark:benchmark /data /workspace

USER benchmark

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=2s --timeout=2s --start-period=5s --retries=15 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/tasks', timeout=1).read()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

