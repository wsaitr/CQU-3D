FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace/repo

COPY apps/requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /tmp/requirements.txt

COPY apps/dispatcher /workspace/repo/apps/dispatcher
COPY packages /workspace/repo/packages

CMD ["python", "/workspace/repo/apps/dispatcher/main.py"]
