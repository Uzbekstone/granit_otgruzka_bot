import asyncio
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Update

from settings import settings

# ---- Extended imports for our flow ----
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from states import Otgruzka
from utils_translit import latin_to_cyr
from sheets_client import Sheets
import datetime as dt
import os

# Router for handlers
router = Router()

TZ = dt.timezone(dt.timedelta(hours=5))  # Asia/Tashkent (UTC+5)

SHEETS_SPREADSHEET_ID = os.getenv("SHEETS_SPREADSHEET_ID", "")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "")

sheets = Sheets(SHEETS_SPREADSHEET_ID, GOOGLE_CREDENTIALS_JSON)

# Keyboards
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚚 Отгрузка"), KeyboardButton(text="📊 Отчет: Вчера")],
    [KeyboardButton(text="🗓️ Отчет: Позавчера"), KeyboardButton(text="📅 Отчет: 30 дней")]
], resize_keyboard=True)

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Salom! Granit yuklash jarayonini yozib borish uchun bot tayyor.\n"
        "Menyu: Отгрузка / Отчетlar.", reply_markup=main_kb)

@router.message(F.text == "🚚 Отгрузка")
async def m_otgruzka(message: types.Message, state: FSMContext):
    await state.set_state(Otgruzka.TuriRazmer)
    await message.answer(
        "1) Granit turi va o'lchami (yozma).\n"
        "Eslatma: lotinchada ruscha yozsangiz, men avtomatik кирилл га o'tkazaman."
    )

@router.message(Otgruzka.TuriRazmer)
async def f_turi_razmer(message: types.Message, state: FSMContext):
    text = latin_to_cyr(message.text)
    await state.update_data(turi_razmer=text)
    await state.set_state(Otgruzka.Miqdor)
    await message.answer("2) Kv.metr yoki uzunlik (raqam kiriting, masalan 125.6)")

@router.message(Otgruzka.Miqdor)
async def f_miqdor(message: types.Message, state: FSMContext):
    val = message.text.replace(",", ".")
    try:
        _ = float(val)
    except ValueError:
        return await message.answer("Iltimos, raqam kiriting. Masalan: 120.5")
    await state.update_data(miqor=val)
    await state.set_state(Otgruzka.Paddon)
    await message.answer("3) Paddonlar soni (butun raqam)")

@router.message(Otgruzka.Paddon)
async def f_paddon(message: types.Message, state: FSMContext):
    try:
        pcs = int(message.text)
    except ValueError:
        return await message.answer("Iltimos, butun raqam kiriting. Masalan: 4")
    await state.update_data(paddon=pcs)
    await state.set_state(Otgruzka.Manzil)
    await message.answer("4) Qayerga ketayapti? (viloyat / Respublika / joy nomi — yozma, lotin ham bo'ladi)")

@router.message(Otgruzka.Manzil)
async def f_manzil(message: types.Message, state: FSMContext):
    await state.update_data(manzil=latin_to_cyr(message.text))
    await state.set_state(Otgruzka.Telefon)
    await message.answer("5) Haydovchi telefon raqami (+9989xxxxxxxx ko'rinishida)")

@router.message(Otgruzka.Telefon)
async def f_tel(message: types.Message, state: FSMContext):
    t = message.text.strip()
    if not t.startswith("+") or len(t) < 9:
        return await message.answer("Telefon to'g'ri emas. Misol: +998901234567")
    await state.update_data(tel=t)
    await state.set_state(Otgruzka.Rasmlar)
    await message.answer("6) Yuklangan mashina suratlari 3–4 dona yuboring. Tugatgach 'Готово' deb yozing.")

@router.message(Otgruzka.Rasmlar, F.photo)
async def f_photos(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    if len(photos) >= 4:
        await state.set_state(Otgruzka.Summa)
        return await message.answer("7) Yetkazib berish summasi (so'm)")
    await message.answer(f"Qabul qilindi ✅ ({len(photos)}/4). Davom eting yoki 'Готово' deb yozing.")

@router.message(Otgruzka.Rasmlar, F.text.casefold() == "готово")
async def f_photos_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) < 3:
        return await message.answer("Kamida 3 ta foto kerak. Yana yuboring yoki 'Готово' deb yozing.")
    await state.set_state(Otgruzka.Summa)
    await message.answer("7) Yetkazib berish summasi (so'm)")

@router.message(Otgruzka.Summa)
async def f_sum(message: types.Message, state: FSMContext):
    amt = message.text.replace(" ", "")
    try:
        int(amt)
    except ValueError:
        return await message.answer("Butun son kiriting, masalan 2500000")
    await state.update_data(summa=amt)
    await state.set_state(Otgruzka.Kim)
    await message.answer("8) Kim yukladi? (FIO/bo'lim, lotin yozsangiz кирилл qilaman)")

@router.message(Otgruzka.Kim)
async def f_kim(message: types.Message, state: FSMContext):
    await state.update_data(kim=latin_to_cyr(message.text))
    data = await state.get_data()
    now = dt.datetime.now(tz=TZ)
    row = [
        now.isoformat(), now.strftime("%Y-%m-%d"),
        data.get("turi_razmer", ""), data.get("miqor", ""), data.get("paddon", ""),
        data.get("manzil", ""), data.get("tel", ""), ",".join(data.get("photos", [])),
        data.get("summa", ""), data.get("kim", ""), message.from_user.full_name,
    ]
    try:
        sheets.append_otgruzka(row)
    except Exception as e:
        await message.answer("Sheetsga yozishda xatolik. Logs tekshiring.")
        raise

    await state.clear()
    await message.answer("Отгрузка yozildi ✅", reply_markup=main_kb)

def _fmt_rows(rows: list[list[str]]) -> str:
    if not rows:
        return "Ma'lumot topilmadi."
    lines = []
    for r in rows:
        _, sana, turi, miqdor, paddon, manzil, tel, photos, summa, kim, operator = r
        lines.append(
            f"📦 {turi}\n▫️ Sana: {sana}\n▫️ Miqdor: {miqdor}\n▫️ Paddon: {paddon}\n▫️ Manzil: {manzil}\n▫️ Tel: {tel}\n▫️ Summa: {summa} so'm\n▫️ Yuklagan: {kim}\n▫️ Operator: {operator}\n▫️ Rasmlar: {len(photos.split(',')) if photos else 0} ta\n— — —"
        )
    return "\n".join(lines)

@router.message(F.text == "📊 Отчет: Вчера")
async def r_yesterday(message: types.Message):
    today = dt.datetime.now(TZ).date()
    y = dt.datetime.combine(today - dt.timedelta(days=1), dt.time.min, tzinfo=TZ)
    y2 = dt.datetime.combine(today, dt.time.min, tzinfo=TZ)
    rows = sheets.read_between(y, y2)
    await message.answer(f"📊 Вчера ({(today - dt.timedelta(days=1)).isoformat()})\n\n" + _fmt_rows(rows))

@router.message(F.text == "🗓️ Отчет: Позавчера")
async def r_day_before(message: types.Message):
    today = dt.datetime.now(TZ).date()
    start = dt.datetime.combine(today - dt.timedelta(days=2), dt.time.min, tzinfo=TZ)
    end = dt.datetime.combine(today - dt.timedelta(days=1), dt.time.min, tzinfo=TZ)
    rows = sheets.read_between(start, end)
    await message.answer(f"🗓️ Позавчера ({(today - dt.timedelta(days=2)).isoformat()})\n\n" + _fmt_rows(rows))

@router.message(F.text == "📅 Отчет: 30 дней")
async def r_30days(message: types.Message):
    now = dt.datetime.now(TZ)
    start = now - dt.timedelta(days=30)
    rows = sheets.read_between(start, now)
    await message.answer("📅 Последние 30 дней\n\n" + _fmt_rows(rows))

# Aiogram objects
bot = Bot(token=settings.TELEGRAM_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
dp.include_router(router)

# FastAPI app
app = FastAPI(title="Telegram Bot (aiogram+FastAPI)")

@app.get("/")
async def health():
    return {"status": "ok", "env": settings.ENV}

@app.on_event("startup")
async def on_startup():
    webhook_url = f"{settings.BASE_URL}/webhook/{settings.WEBHOOK_SECRET}"
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info("Webhook set successfully.")

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Shutting down...")

@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    if secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        body = await request.body()
        update = Update.model_validate_json(body)
    except Exception as e:
        logger.exception("Failed to parse update: {}", e)
        raise HTTPException(status_code=400, detail="Bad Request")
    try:
        await dp.feed_update(bot, update)
    except Exception as e:
        logger.exception("Handler error: {}", e)
    return JSONResponse({"ok": True})
