# main.py
from __future__ import annotations

import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from loguru import logger

# ✅ aiogram 3.10.0 importlari
from aiogram import Bot, Dispatcher, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from settings import settings  # TELEGRAM_TOKEN, BASE_URL, WEBHOOK_SECRET va b.

# -------------------------------
# FastAPI ilovasi
# -------------------------------
app = FastAPI()

# -------------------------------
# Healthcheck: Render HEAD/GET / yuboradi → 200 qaytaramiz
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
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),  # parse_mode uchun to‘g‘ri usul
)
dp = Dispatcher()
router = Router()

@router.message(commands={"start"})
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Salom! Bot ishga tushdi.\n\n"
        "Menyu:\n"
        "• 🚚 Отгрузка\n"
        "• 📊 Отчет: Вчера\n"
        "• 🗓️ Отчет: Позавчера\n"
        "• 📅 Отчет: 30 дней"
    )

dp.include_router(router)

# -------------------------------
# Webhook endpoint (TRAILING SLASHSIZ yo‘l!)
# -------------------------------
@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Telegram yuborgan update'ni json sifatida olishga harakat qilamiz
    try:
        update_dict = await request.json()
    except Exception:
        # Favqulodda holat: json bo‘lmasa, body bytes olib beramiz
        update_dict = await request.body()

    await dp.feed_webhook_update(bot, update_dict)
    return {"ok": True}

# -------------------------------
# Startup / Shutdown
# -------------------------------
@app.on_event("startup")
async def on_startup():
    # BASE_URL oxiridagi '/' ni olib tashlaymiz → `//webhook/...` 404 muammosini yo‘qotadi
    base = str(settings.BASE_URL).rstrip("/")
    webhook_url = f"{base}/webhook/{settings.WEBHOOK_SECRET}"
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info("Webhook set successfully.")

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        logger.warning(f"Webhook delete failed: {e}")
