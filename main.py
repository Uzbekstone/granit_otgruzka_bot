# main.py
from __future__ import annotations

import os
import re
import json
import random
import string
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from loguru import logger

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from settings import settings  # TELEGRAM_TOKEN, BASE_URL, WEBHOOK_SECRET

# ===== Timezone (mahalliy vaqt) =====
LOCAL_TZ_NAME = os.getenv("LOCAL_TZ", "Asia/Tashkent")
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)

# ===== Google Sheets (ixtiyoriy) =====
sheets_instance = None
try:
    from sheets_client import Sheets
    SHEETS_SPREADSHEET_ID = os.getenv("SHEETS_SPREADSHEET_ID", "")
    GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
    GOOGLE_CREDENTIALS_JSON_B64 = os.getenv("GOOGLE_CREDENTIALS_JSON_B64")
except Exception:
    Sheets = None
    SHEETS_SPREADSHEET_ID = ""
    GOOGLE_CREDENTIALS_JSON = None
    GOOGLE_CREDENTIALS_JSON_B64 = None

# ===== FastAPI =====
app = FastAPI()

@app.get("/", response_class=PlainTextResponse)
@app.head("/", response_class=PlainTextResponse)
def health():
    return "ok"

# ===== Aiogram =====
bot = Bot(
    token=settings.TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()

# ===== Keyboards =====
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🚚 Отгрузка", callback_data="ship")
    kb.button(text="📆 Отчет: Сегодня", callback_data="rpt:today")
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

# ===== FSM (Отгрузка) =====
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

# ===== Commands =====
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Salom! Bot ishga tushdi.\n\n<b>Menyu</b>dan bo‘lim tanlang:",
        reply_markup=main_menu(),
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Yordam: /start — menyu, 🚚 Отгрузка — yangi yozuv, hisobot tugmalari — ko‘rish.")

# ===== Отгрузка oqimi =====
@router.callback_query(F.data == "ship")
async def ship_start(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ShipForm.type_size)
    await cb.message.edit_text(
        "1) <b>Granit tosh turi va o‘lchami</b>ni yozing (masalan: Gabbro 600×300×30).",
        reply_markup=cancel_menu(),
    )
    await cb.answer()

@router.message(ShipForm.type_size, F.text.len() > 2)
async def ship_type_size(message: types.Message, state: FSMContext):
    await state.update_data(type_size=message.text.strip())
    await state.set_state(ShipForm.qty)
    await message.answer(
        "2) <b>Hajm</b> — kv.m yoki metr: masalan <code>23.5 m²</code> yoki <code>12.4 m</code>.",
        reply_markup=cancel_menu(),
    )

@router.message(ShipForm.qty, F.text)
async def ship_qty(message: types.Message, state: FSMContext):
    await state.update_data(qty=message.text.strip())
    await state.set_state(ShipForm.pallets)
    await message.answer("3) <b>Poddonlar soni</b>ni kiriting (butun son).", reply_markup=cancel_menu())

@router.message(ShipForm.pallets, F.text.regexp(r"^\d{1,4}$"))
async def ship_pallets(message: types.Message, state: FSMContext):
    await state.update_data(pallets=int(message.text))
    await state.set_state(ShipForm.dest)
    await message.answer("4) <b>Qayerga ketayapti</b> — viloyat / respublika / joy nomi yozing.", reply_markup=cancel_menu())

@router.message(ShipForm.dest, F.text.len() > 2)
async def ship_dest(message: types.Message, state: FSMContext):
    await state.update_data(dest=message.text.strip())
    await state.set_state(ShipForm.driver)
    await message.answer("5) <b>Haydovchi telefon raqami</b>ni kiriting (faqat raqamlar, + ham bo‘lishi mumkin).", reply_markup=cancel_menu())

PHONE_RE = re.compile(r"^\+?\d{9,15}$")

@router.message(ShipForm.driver, F.text)
async def ship_driver(message: types.Message, state: FSMContext):
    txt = message.text.strip().replace(" ", "")
    if not PHONE_RE.match(txt):
        await message.answer("Telefon formati noto‘g‘ri. Masalan: <code>+998901234567</code>")
        return
    await state.update_data(driver=txt)
    await state.set_state(ShipForm.photos)
    await message.answer(
        "6) <b>3–4 dona mashina fotosi</b>ni yuboring (ketma-ket).\nYuborib bo‘lgach, <b>➡️ Далее</b> ni bosing.",
        reply_markup=next_cancel_menu(),
    )

@router.message(ShipForm.photos, F.photo)
async def ship_photos_collect(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photos = list(data.get("photos", []))
    fid = message.photo[-1].file_id
    if len(photos) >= 4:
        await message.answer("Allaqachon 4 ta foto olindi. <b>➡️ Далее</b> ni bosing.", reply_markup=next_cancel_menu())
        return
    photos.append(fid)
    await state.update_data(photos=photos)
    await message.answer(f"Foto qabul qilindi ✅  ({len(photos)}/4). Yana yuborishingiz mumkin yoki ➡️ Далее.")

@router.callback_query(ShipForm.photos, F.data == "ship:next")
async def ship_photos_next(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data.get("photos", [])) < 1:
        await cb.answer("Kamida 1 ta foto yuboring.", show_alert=True)
        return
    await state.set_state(ShipForm.price)
    await cb.message.edit_text("7) <b>Yetkazib berish summasi</b>ni kiriting (masalan: 2 500 000).", reply_markup=cancel_menu())
    await cb.answer()

@router.message(ShipForm.price, F.text)
async def ship_price(message: types.Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await state.set_state(ShipForm.loader)
    await message.answer("8) <b>Kim yukladi?</b> (FIO yoki brigada nomi).", reply_markup=cancel_menu())

@router.message(ShipForm.loader, F.text)
async def ship_loader(message: types.Message, state: FSMContext):
    local_now = datetime.now(LOCAL_TZ)
    await state.update_data(loader=message.text.strip(), ts=local_now.strftime("%Y-%m-%d %H:%M"))

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
        f"• Sana: {data.get('ts')} ({LOCAL_TZ_NAME})"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash", callback_data="ship:ok")
    kb.button(text="✏️ Bekor/yangidan", callback_data="ship:cancel")
    kb.adjust(2)
    await state.set_state(ShipForm.confirm)
    await message.answer(preview, reply_markup=kb.as_markup())

@router.callback_query(ShipForm.confirm, F.data == "ship:ok")
async def ship_save(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    rand = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    order_id = f"{data.get('ts').replace(' ', '_')}_{rand}"

    main_row = [
        order_id,
        data.get("ts"),
        data.get("type_size"),
        data.get("qty"),
        data.get("pallets"),
        data.get("dest"),
        data.get("driver"),
        data.get("price"),
        data.get("loader"),
        cb.from_user.full_name,
    ]

    file_ids = data.get("photos", [])
    p_row = [order_id] + [file_ids[i] if i < len(file_ids) else "" for i in range(4)]

    try:
        if Sheets and SHEETS_SPREADSHEET_ID and sheets_instance:
            # 1) Otgruzka
            try:
                ws_main = sheets_instance.sh.worksheet("Otgruzka")
            except Exception:
                ws_main = sheets_instance.sh.add_worksheet(title="Otgruzka", rows=1, cols=20)
                ws_main.append_row([
                    "order_id", "time", "type_size", "qty", "pallets",
                    "dest", "driver", "price", "loader", "user"
                ])
            ws_main.append_row(main_row)

            # 2) Photos
            try:
                ws_ph = sheets_instance.sh.worksheet("Photos")
            except Exception:
                ws_ph = sheets_instance.sh.add_worksheet(title="Photos", rows=1, cols=10)
                ws_ph.append_row(["order_id", "file1", "file2", "file3", "file4"])
            ws_ph.append_row(p_row)

            # === 3) Otgruzka (Hisobot) — foydalanuvchi ko‘rinishi ===
            # Tartib: Sana | Granit turi | Kvadrati | Paddon soni | Qayerga ketyapti |
            #         Haydovchi raqami | Foto surat | Yetkazish summasi | Kim yukladi
            VIEW_SHEET_TITLE = "Otgruzka (Hisobot)"
            desired_header = [
                "Sana",
                "Granit turi",
                "Kvadrati",
                "Paddon soni",
                "Qayerga ketyapti",
                "Haydovchi raqami",
                "Foto surat",
                "Yetkazish summasi",
                "Kim yukladi",
            ]

            try:
                ws_view = sheets_instance.sh.worksheet(VIEW_SHEET_TITLE)
            except Exception:
                ws_view = sheets_instance.sh.add_worksheet(title=VIEW_SHEET_TITLE, rows=1, cols=20)
                ws_view.append_row(desired_header)

            # birinchi qatordagi sarlavhani tekshirib, kerak bo‘lsa to‘g‘rilab qo‘yamiz
            try:
                first_row = ws_view.row_values(1)
                if first_row != desired_header:
                    ws_view.delete_rows(1)
                    ws_view.insert_rows([desired_header], 1)
            except Exception:
                pass

            photo_cell = " ".join([fid for fid in file_ids if fid])

            view_row = [
                data.get("ts"),             # Sana (mahalliy tz)
                data.get("type_size"),      # Granit turi
                data.get("qty"),            # Kvadrati/uzunligi
                str(data.get("pallets")),   # Paddon soni
                data.get("dest"),           # Qayerga ketyapti
                data.get("driver"),         # Haydovchi raqami
                photo_cell,                 # Foto file_id lar bitta katakda
                data.get("price"),          # Yetkazish summasi
                data.get("loader"),         # Kim yukladi
            ]
            ws_view.append_row(view_row)

            await cb.message.edit_text("✅ Yozuv saqlandi. Rahmat!", reply_markup=main_menu())
        else:
            await cb.message.edit_text("⚠️ Sheets ulanmagan. Admin sozlamalarini tekshiring.", reply_markup=main_menu())
    except Exception as e:
        logger.exception("Sheets yozishda xato: {}", e)
        await cb.message.edit_text("❌ Saqlashda xato. Keyinroq urinib ko‘ring.", reply_markup=main_menu())

    await state.clear()
    await cb.answer()

@router.callback_query(F.data == "ship:cancel")
async def ship_cancel(cb: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ Amal bekor qilindi.", reply_markup=main_menu())
    await cb.answer()

# ===== Hisobot yordamchilari =====
def _split_chunks(text: str, limit: int = 3500):
    if len(text) <= limit:
        return [text]
    parts, buf = [], []
    current = 0
    for line in text.splitlines():
        if current + len(line) + 1 > limit:
            parts.append("\n".join(buf))
            buf, current = [line], len(line) + 1
        else:
            buf.append(line)
            current += len(line) + 1
    if buf:
        parts.append("\n".join(buf))
    return parts

async def _report_text(days: int) -> str:
    if not (Sheets and SHEETS_SPREADSHEET_ID and sheets_instance):
        return "⚠️ Sheets ulanmagan. Hisobot uchun admin sozlashi kerak."
    since = (datetime.now(LOCAL_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    return f"📄 Hisobot (oxirgi {days} kun, {since} dan):\n\n— (bu yerda real raqamlar chiqadi)"

async def _report_summary_for(date_str: str) -> str:
    """
    Bugungi hisobot: faqat Zakazlar/Poddon/Hajm yig‘indi
    va har bir zakaz alohida: Sana, Soat, granit turi, kvadrati, poddon.
    """
    if not (Sheets and SHEETS_SPREADSHEET_ID and sheets_instance):
        return "⚠️ Sheets ulanmagan. Hisobot uchun admin sozlashi kerak."

    try:
        ws = sheets_instance.sh.worksheet("Otgruzka")
    except Exception:
        return "Hali 'Otgruzka' jadvali yo‘q."

    rows_all = ws.get_all_values()
    if not rows_all or len(rows_all) < 2:
        return f"📆 <b>{date_str}</b> uchun yozuv topilmadi."

    headers = rows_all[0]
    rows = rows_all[1:]
    idx = {h: i for i, h in enumerate(headers)}
    required = ("time", "type_size", "qty", "pallets", "dest")
    if not all(k in idx for k in required):
        return "Jadval sarlavhalari kutilgandek emas. Keraklilar: time/type_size/qty/pallets/dest."

    selected = []
    for r in rows:
        t = r[idx["time"]] if idx["time"] < len(r) else ""
        if t[:10] == date_str:
            selected.append(r)

    if not selected:
        return f"📆 <b>{date_str}</b> uchun yozuv topilmadi."

    def _float_in_text(s: str) -> float:
        m = re.findall(r"[\d]+(?:[.,]\d+)?", s or "")
        return float(m[0].replace(",", ".")) if m else 0.0

    total_orders = len(selected)
    total_pallets = 0
    total_qty = 0.0

    for r in selected:
        pallets = r[idx["pallets"]] if idx["pallets"] < len(r) else ""
        qty     = r[idx["qty"]]     if idx["qty"]     < len(r) else ""
        total_pallets += int(pallets) if str(pallets).isdigit() else 0
        total_qty     += _float_in_text(qty)

    # Har bir zakaz: Sana, Soat, type, qty, pallets
    lines = []
    for r in selected:
        full_time = r[idx["time"]] if idx["time"] < len(r) else ""
        d = full_time[:10]
        tm = full_time[11:16] if len(full_time) >= 16 else ""
        tsize = r[idx["type_size"]] if idx["type_size"] < len(r) else ""
        qty   = r[idx["qty"]] if idx["qty"] < len(r) else ""
        pal   = r[idx["pallets"]] if idx["pallets"] < len(r) else ""
        lines.append(f"— {d} {tm} • {tsize} • {qty} • {pal} pod")

    header = (
        f"📆 <b>{date_str}</b> kunlik hisobot\n"
        f"• Zakazlar: <b>{total_orders}</b>\n"
        f"• Poddon: <b>{total_pallets}</b>\n"
        f"• Hajm yig‘indi: <b>{total_qty:g}</b>\n\n"
    )
    return header + "\n".join(lines)

# ===== Hisobot handlerlari =====
@router.callback_query(F.data == "rpt:today")
async def report_today(cb: types.CallbackQuery):
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    text = await _report_summary_for(today)
    chunks = _split_chunks(text)
    await cb.message.edit_text(chunks[0], reply_markup=main_menu())
    for part in chunks[1:]:
        await cb.message.answer(part)
    await cb.answer()

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

# ===== Routerni ulash =====
dp.include_router(router)

# ===== Webhook =====
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

# ===== Startup/Shutdown =====
@app.on_event("startup")
async def on_startup():
    base = str(settings.BASE_URL).rstrip("/")
    webhook_url = f"{base}/webhook/{settings.WEBHOOK_SECRET}"
    logger.info(f"Setting webhook to: {webhook_url}")
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logger.info("Webhook set successfully.")

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
