# main.py
from __future__ import annotations

import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from loguru import logger

from aiogram import Dispatcher, Router, types
from aiogram.client import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from settings import settings  # TELEGRAM_TOKEN, BASE_URL, WEBHOOK_SECRET va h.k.

# (ixtiyoriy) Sheets: kodingizda bor bo'lsa import qiling
try:
    from sheets_client import Sheets
except Exception:
    Sheets = None  # sheets_client yo‘q bo‘lsa ham server ishlasin

# -------------------------------
# FastAPI ilovasi
# -------------------------------
app = FastAPI()

# -------------------------------
# Healthcheck (Render HEAD/GET / yuboradi)
# -------------------------------
@app.get("/", response_class=PlainTextResponse)
@app.head("/", response_class=PlainTextResponse)
def health():
    return "ok"

# -------------------------------
# Aiogram: bot, dispatcher, router
# -------------------------------
bot = Bot(
    token=settings.TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),  # aiogram 3.7+ talabi
)
dp = Dispatcher()
router = Router()

@router.message(commands={"start"})
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Salom! Bot ishga tushdi.\n\n"
        "Menyu: \n"
        "• 🚚 Отгрузка\n"
        "• 📊 Отчет: Вчера\n"
        "• 🗓️ Отчет: Позавчера\n"
        "• 📅 Отчет: 30 дней"
    )

dp.include_router(router)

# -------------------------------
# Webhook endpoint (trailing slash YO'Q)
# -------------------------------
@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Aiogram 3.x: dict ko‘rinishida yuboramiz
    try:
        update_dict = await request.json()
    except Exception:
        # Ayrim hollarda Telegram 'application/x-www-form-urlencoded' yuborsa:
        body = await request.body()
        # aiogram bytes/dict ikkisini ham qabul qiladi, lekin dict afzal
        update_dict = body

    await dp.feed_webhook_update(bot, update_dict)
    return {"ok": True}

# -------------------------------
# (ixtiyoriy, barqaror) Sheets ulanishi
# -------------------------------
SHEETS_SPREADSHEET_ID = os.getenv("SHEETS_SPREADSHEET_ID", "")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")  # bo‘sh bo‘lishi mumkin
GOOGLE_CREDENTIALS_JSON_B64 = os.getenv("GOOGLE_CREDENTIALS_JSON_B64")  # bo‘sh bo‘lishi mumkin

sheets_instance: Sheets | None = None  # global reference (kerak bo‘lsa ishlatasiz)

# -------------------------------
# Startup / Shutdown
# -------------------------------
@app.on_event("startup")
async def on_startup():
    # 1) Webhook URL: BASE_URL oxiridagi '/' ni olib tashlaymiz
    base = str(settings.BASE_URL).rstrip("/")
    webhook_url = f"{base}/webhook/{settings.WEBHOOK_SECRET}"
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info("Webhook set successfully.")

    # 2) Sheets ga ulanib qo'yamiz (agar mavjud bo'lsa)
    global sheets_instance
    if Sheets and SHEETS_SPREADSHEET_ID:
        try:
            # Sizning Sheets klassingiz: Sheets(spreadsheet_id, credentials_json=None, credentials_b64=None)
            sheets_instance = Sheets(
                SHEETS_SPREADSHEET_ID,
                credentials_json=GOOGLE_CREDENTIALS_JSON,
                credentials_b64=GOOGLE_CREDENTIALS_JSON_B64,
            )
            logger.info("Google Sheets: connected.")
        except Exception as e:
            # Ruxsat/ID xatolarida server yiqilmasin — faqat ogohlantiramiz
            logger.warning(
                "Google Sheets ulanmagan. Sabab: {}. "
                "Tekshiring: SHEETS_SPREADSHEET_ID (faqat ID), service-account email Editor, "
                "Sheets API/Drive API enable qilingan.", e
            )

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        logger.warning(f"Webhook delete failed: {e}")
