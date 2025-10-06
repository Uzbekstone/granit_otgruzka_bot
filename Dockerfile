# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Zarur paketlar va tozalash
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# pip/setuptools/wheel yangilash
RUN python -m pip install --upgrade pip setuptools wheel

# Talablar
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Kod
COPY . .

# Port
ENV PORT=8000
EXPOSE 8000

# Uvicornni PORT env bilan ishga tushirish (env kengayadi)
CMD ["/bin/sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
