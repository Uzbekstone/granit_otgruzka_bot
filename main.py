# main.py
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from loguru import logger

# aiogram 3.10 importlar
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from settings import settings  # TELEGRAM_TOKEN, BASE_URL, WEBHOOK_SECRET va b.

# (ixtiyoriy) Sheets: sizda bo‘lsa shu modul bo‘yicha ishlaydi
sheets_instance = None
try:
    from sheets_client import Sheets  # Sheets(spreadsheet_id, credentials_json=None, credentials_b64=None)
    SHEETS_SPREADSHEET_ID = os.getenv("SHEETS_SPREADSHEET_ID", "")
    GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
    GOOGLE_CREDENTIALS_JSON_B64 = os.getenv("GOOGLE_CREDENTIALS_JSON_B64")
except Exception:
    Sheets = None
    SHEETS_SPREADSHEET_ID = ""
    GOOGLE_CREDENTIALS_JSON = None
    GOOGLE_CREDENTIALS_JSON_B64 = None

# -------------------------------
# FastAPI ilovasi
# -------------------------------
app = FastAPI()

# Healthcheck: Render HEAD/GET / yuboradi → 200 qaytaramiz
@app.get("/", response_class=PlainTextResponse)
@app.head("/", response_class=PlainTextResponse)
def health():
    return "ok"

# -------------------------------
# Aiogram: bot, dispatcher, router
# -------------------------------
bot = Bot(
    token=settings.TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()

# -------------------------------
# Klaviaturalar
# -------------------------------
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🚚 Отгрузка", callback_data="ship")
    kb.button(text="📊 Отчет: Вчера", callback_data="rpt:yesterday")
    kb.button(text="🗓️ Отчет: Позавчера", callback_data="rpt:prev")
    kb.button(text="📅 Отчет: 30 дней", callback_data="rpt:30")
    kb.adjust(1)
    return kb.as_markup()

def next_cancel_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ Далее", callback_data="ship:next")
    kb.button(text="❌ Отмена", callback_data="ship:cancel")
    kb.adjust(2)
    return kb.as_markup()

def cancel_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="ship:cancel")
    kb.adjust(1)
    return kb.as_markup()

# -------------------------------
# Holatlar (FSM) — Отгрузка
# -------------------------------
class ShipForm(StatesGroup):
    type_size = State()
    qty = State()
    pallets = State()
    dest = State()
    driver = State()
    photos = State()
    price = State()
    loader = State()
    confirm = State()

# -------------------------------
# /start
# -------------------------------
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Salom! Bot ishga tushdi.\n\n"
        "<b>Menyu</b>dan bo‘lim tanlang:",
        reply_markup=main_menu(),
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Yordam: /start — menyu, 🚚 Отгрузка — yangi yuklash yozuvi, hisobot tugmalari — ko‘rish.")

# -------------------------------
# Отгрузка: boshlash
# -------------------------------
@router.callback_query(F.data == "ship")
async def ship_start(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ShipForm.type_size)
    await cb.message.edit_text(
        "1) <b>Granit tosh turi va o‘lchami</b>ni yozing (masalan: Gabbro 600×300×30).",
        reply_markup=cancel_menu(),
    )
    await cb.answer()

# 1) type_size
@router.message(ShipForm.type_size, F.text.len() > 2)
async def ship_type_size(message: types.Message, state: FSMContext):
    await state.update_data(type_size=message.text.strip())
    await state.set_state(ShipForm.qty)
    await message.answer(
        "2) <b>Hajm</b> — kv.m yoki metr: masalan <code>23.5 m²</code> yoki <code>12.4 m</code>.",
        reply_markup=cancel_menu(),
    )

# 2) qty
@router.message(ShipForm.qty, F.text)
async def ship_qty(message: types.Message, state: FSMContext):
    await state.update_data(qty=message.text.strip())
    await state.set_state(ShipForm.pallets)
    await message.answer("3) <b>Poddonlar soni</b>ni kiriting (butun son).", reply_markup=cancel_menu())

# 3) pallets
@router.message(ShipForm.pallets, F.text.regexp(r"^\d{1,4}$"))
async def ship_pallets(message: types.Message, state: FSMContext):
    await state.update_data(pallets=int(message.text))
    await state.set_state(ShipForm.dest)
    await message.answer(
        "4) <b>Qayerga ketayapti</b> — viloyat / respublika / joy nomi yozing.",
        reply_markup=cancel_menu(),
    )

# 4) dest
@router.message(ShipForm.dest, F.text.len() > 2)
async def ship_dest(message: types.Message, state: FSMContext):
    await state.update_data(dest=message.text.strip())
    await state.set_state(ShipForm.driver)
    await message.answer(
        "5) <b>Haydovchi telefon raqami</b>ni kiriting (faqat raqamlar, + bilan ham bo‘lishi mumkin).",
        reply_markup=cancel_menu(),
    )

PHONE_RE = re.compile(r"^\+?\d{9,15}$")

# 5) driver
@router.message(ShipForm.driver, F.text)
async def ship_driver(message: types.Message, state: FSMContext):
    txt = message.text.strip().replace(" ", "")
    if not PHONE_RE.match(txt):
        await message.answer("Telefon formati noto‘g‘ri. Masalan: <code>+998901234567</code>")
        return
    await state.update_data(driver=txt)
    await state.set_state(ShipForm.photos)
    await message.answer(
        "6) <b>3–4 dona mashina fotosi</b>ni yuboring (ketma-ket).\n"
        "Hamma rasmlarni yuborgach, <b>➡️ Далее</b> tugmasini bosing.",
        reply_markup=next_cancel_menu(),
    )

# 6) photos — 3–4 ta photo qabul qilamiz
@router.message(ShipForm.photos, F.photo)
async def ship_photos_collect(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = list(data.get("photos", []))
    # eng katta resolution file_id
    file_id = message.photo[-1].file_id
    if len(photos) >= 4:
        await message.answer("Allaqachon 4 ta foto olindi. <b>➡️ Далее</b> ni bosing.", reply_markup=next_cancel_menu())
        return
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(f"Foto qabul qilindi ✅  ({len(photos)}/4). Yana yuborishingiz mumkin yoki ➡️ Далее.")

# photos → next
@router.callback_query(ShipForm.photos, F.data == "ship:next")
async def ship_photos_next(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data.get("photos", [])) < 1:
        await cb.answer("Kamida 1 ta foto yuboring.", show_alert=True)
        return
    await state.set_state(ShipForm.price)
    await cb.message.edit_text("7) <b>Yetkazib berish summasi</b>ni kiriting (masalan: 2 500 000).", reply_markup=cancel_menu())
    await cb.answer()

# 7) price
@router.message(ShipForm.price, F.text)
async def ship_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await state.set_state(ShipForm.loader)
    await message.answer("8) <b>Kim yukladi?</b> (FIO yoki brigada nomi).", reply_markup=cancel_menu())

# 8) loader → confirm
@router.message(ShipForm.loader, F.text)
async def ship_loader(message: types.Message, state: FSMContext):
    await state.update_data(loader=message.text.strip(), ts=datetime.now().strftime("%Y-%m-%d %H:%M"))
    data = await state.get_data()

    preview = (
        "<b>Yuklash ma’lumotlari:</b>\n"
        f"• Turi/o‘lchami: {data.get('type_size')}\n"
        f"• Hajm: {data.get('qty')}\n"
        f"• Poddon: {data.get('pallets')}\n"
        f"• Manzil: {data.get('dest')}\n"
        f"• Haydovchi: {data.get('driver')}\n"
        f"• Narx: {data.get('price')}\n"
        f"• Yuklagan: {data.get('loader')}\n"
        f"• Foto: {len(data.get('photos', []))} ta\n"
        f"• Sana: {data.get('ts')}"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash", callback_data="ship:ok")
    kb.button(text="✏️ Bekor/yangidan", callback_data="ship:cancel")
    kb.adjust(2)
    await state.set_state(ShipForm.confirm)
    await message.answer(preview, reply_markup=kb.as_markup())

# Tasdiqlash
@router.callback_query(ShipForm.confirm, F.data == "ship:ok")
async def ship_save(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Sheetsga yozish
    try:
        if Sheets and SHEETS_SPREADSHEET_ID and sheets_instance:
            # Sizning Sheets klassingizdagi metodga moslang:
            # Misol: sheets_instance.append_row([...]) yoki sheets_instance.save_otgruzka(data_dict)
            # Bu yerda universal ko‘rinishda yozamiz:
            payload = {
                "time": data.get("ts"),
                "type_size": data.get("type_size"),
                "qty": data.get("qty"),
                "pallets": data.get("pallets"),
                "dest": data.get("dest"),
                "driver": data.get("driver"),
                "photos": ", ".join(data.get("photos", [])),  # file_id larni yozamiz
                "price": data.get("price"),
                "loader": data.get("loader"),
                "user": cb.from_user.full_name,
            }
            # Agar sizda Sheets.save_otgruzka bo‘lsa, shuni chaqiring:
            try:
                sheets_instance.save_otgruzka(payload)  # <-- agar sizda shu metod bor bo‘lsa
            except AttributeError:
                # generik append_row varianti (ustunlar ketma-ketligini siz belgilaysiz)
                sheets_instance.ws_data.append_row(
                    [
                        payload["time"],
                        payload["type_size"],
                        payload["qty"],
                        payload["pallets"],
                        payload["dest"],
                        payload["driver"],
                        payload["photos"],
                        payload["price"],
                        payload["loader"],
                        payload["user"],
                    ]
                )
            await cb.message.edit_text("✅ Yozuv saqlandi. Rahmat!", reply_markup=main_menu())
        else:
            await cb.message.edit_text(
                "⚠️ Sheets ulanmagan. Yozuvni saqlash uchun admin Google Sheets sozlamalarini tekshirishi kerak.",
                reply_markup=main_menu(),
            )
    except Exception as e:
        logger.exception("Sheets yozishda xato: {}", e)
        await cb.message.edit_text("❌ Saqlashda xato. Keyinroq urinib ko‘ring.", reply_markup=main_menu())

    await state.clear()
    await cb.answer()

# Bekor qilish
@router.callback_query(F.data == "ship:cancel")
async def ship_cancel(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Amal bekor qilindi.", reply_markup=main_menu())
    await cb.answer()

# -------------------------------
# Hisobotlar
# -------------------------------
async def _report_text(days: int) -> str:
    if not (Sheets and SHEETS_SPREADSHEET_ID and sheets_instance):
        return "⚠️ Sheets ulanmagan. Hisobotni olish uchun admin sozlashi kerak."
    # Bu yerda real hisobotni sheets_instance dan oling (masalan, sanaga qarab filtr).
    # Hozircha oddiy sarlavha chiqaramiz.
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    return f"📄 Hisobot (oxirgi {days} kun, {since} dan):\n\n— (bu yerda real raqamlar chiqadi)"

@router.callback_query(F.data == "rpt:yesterday")
async def report_yesterday(cb: types.CallbackQuery):
    text = await _report_text(1)
    await cb.message.edit_text(text, reply_markup=main_menu())
    await cb.answer()

@router.callback_query(F.data == "rpt:prev")
async def report_prev(cb: types.CallbackQuery):
    text = await _report_text(2)
    await cb.message.edit_text(text, reply_markup=main_menu())
    await cb.answer()

@router.callback_query(F.data == "rpt:30")
async def report_30(cb: types.CallbackQuery):
    text = await _report_text(30)
    await cb.message.edit_text(text, reply_markup=main_menu())
    await cb.answer()

# Routerni DP ga ulaymiz
dp.include_router(router)

# -------------------------------
# Webhook endpoint (TRAILING SLASHSIZ yo‘l!)
# -------------------------------
@app.post("/webhook/{secret}")
async def tg_webhook(secret: str, request: Request):
    if secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        update_dict = await request.json()
    except Exception:
        update_dict = await request.body()
    await dp.feed_webhook_update(bot, update_dict)
    return {"ok": True}

# -------------------------------
# Startup / Shutdown
# -------------------------------
@app.on_event("startup")
async def on_startup():
    # BASE_URL oxiridagi '/' ni olib tashlaymiz → `//webhook/...` 404 yo‘q
    base = str(settings.BASE_URL).rstrip("/")
    webhook_url = f"{base}/webhook/{settings.WEBHOOK_SECRET}"
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info("Webhook set successfully.")

    # Sheetsga ulanish (bo‘lsa)
    global sheets_instance
    if Sheets and SHEETS_SPREADSHEET_ID:
        try:
            sheets_instance = Sheets(
                SHEETS_SPREADSHEET_ID,
                credentials_json=GOOGLE_CREDENTIALS_JSON,
                credentials_b64=GOOGLE_CREDENTIALS_JSON_B64,
            )
            logger.info("Google Sheets: connected.")
        except Exception as e:
            logger.warning(
                "Google Sheets ulanmagan: {}. "
                "Tekshiring: SHEETS_SPREADSHEET_ID (faqat ID), service-account email Editor, "
                "Sheets/Drive API enable qilingan.",
                e,
            )

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as e:
        logger.warning(f"Webhook delete failed: {e}")
