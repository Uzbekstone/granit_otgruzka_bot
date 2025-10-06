# Telegram Bot (Granit Otgruzka) — aiogram + FastAPI + Docker + Google Sheets

## Local run
```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker
```bash
docker build -t tg-bot .
docker run -p 8000:8000 --env-file .env tg-bot
```

## Env Vars
- TELEGRAM_TOKEN
- BASE_URL
- WEBHOOK_SECRET
- SHEETS_SPREADSHEET_ID
- GOOGLE_CREDENTIALS_JSON
