# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     curl ca-certificates &&     rm -rf /var/lib/apt/lists/*
# ...
WORKDIR /app

# pip/setuptools/wheel yangilab oling – yechim topishni osonlashtiradi
RUN python -m pip install --upgrade pip setuptools wheel

COPY requirements.txt ./
RUN pip install -r requirements.txt
# ...

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${PORT}"]
