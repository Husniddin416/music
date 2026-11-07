"""
Telegram bot — aiogram 3.x
Foydalanuvchi /start bosib raqamini yuborganda tg_contacts ga yoziladi.
sendCode() funksiyasi API tomonidan chaqiriladi.
"""
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, KeyboardButtonRequestContact,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from server.db import db

logger = logging.getLogger(__name__)

bot: Bot = None   # main.py tomonidan ishga tushiriladi
dp = Dispatcher()

_bot_username = ""


def norm_phone(p: str) -> str:
    return "".join(c for c in str(p or "") if c.isdigit())


def get_site_url() -> str:
    return os.getenv("SITE_URL", "https://music-l8kd.onrender.com").rstrip("/")


def get_bot_username() -> str:
    return _bot_username


async def init_bot(token: str):
    global bot, _bot_username
    bot = Bot(token=token)
    me = await bot.get_me()
    _bot_username = me.username
    logger.info(f"Bot ishga tushdi: @{_bot_username}")

    site_url = get_site_url()
    description = (
        f"🎧 MusicUz — Zamonaviy o'zbek musiqa platformasi!\n\n"
        f"Bu bot orqali siz:\n"
        f"✨ Saytga kirish va ro'yxatdan o'tish uchun kod olasiz\n"
        f"🎵 Minglab yangi va sevimli taronalarni tinglaysiz\n"
        f"❤️ Yoqtirgan musiqalarga layk bosib, saqlab qo'yasiz\n\n"
        f"🌐 Rasmiy saytimiz:\n{site_url}\n\n"
        f"Pastdagi \"Start\" tugmasini bosing 👇"
    )
    try:
        await bot.set_my_description(description=description)
        await bot.set_my_short_description(
            short_description=f"MusicUz — Sevimli qo'shiqlaringizni tinglang. Sayt: {site_url}"
        )
        if site_url.startswith("https://"):
            await bot.set_chat_menu_button(
                menu_button=types.MenuButtonWebApp(
                    text="🎵 Saytni ochish",
                    web_app=types.WebAppInfo(url=site_url)
                )
            )
    except Exception as e:
        logger.warning(f"Bot info setup: {e}")

    return bot


async def send_code(chat_id: int, code: str):
    site_url = get_site_url()
    await bot.send_message(
        chat_id,
        f"🔐 MusicUz kirish kodi: <code>{code}</code>\n\n"
        f"⏳ Kod 5 daqiqa amal qiladi. Saytga kirib kodni kiriting:\n"
        f"🔗 <a href=\"{site_url}\">{site_url}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Saytga kirish", url=site_url)
        ]])
    )


# ---- Handlerlar ----

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    site_url = get_site_url()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(
            text="📱 Raqamni yuborish",
            request_contact=True
        )]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        f"🎵 <b>MusicUz</b> botiga xush kelibsiz!\n\n"
        f"🌐 Sayt: <a href=\"{site_url}\">{site_url}</a>\n\n"
        f"Saytga kirish kodini olish uchun pastdagi tugma orqali "
        f"telefon raqamingizni yuboring:",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )


@dp.message(Command(commands=["site", "link", "sayt"]))
async def cmd_site(message: types.Message):
    site_url = get_site_url()
    await message.answer(
        f"🎧 <b>MusicUz rasmiy sayti:</b>\n\n🔗 <a href=\"{site_url}\">{site_url}</a>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Saytni ochish", url=site_url)
        ]])
    )


@dp.message(Command("donate"))
async def cmd_donate(message: types.Message):
    card = os.getenv("DONATE_CARD", "8600 0000 0000 0000")
    owner = os.getenv("DONATE_OWNER", "MusicUz")
    site_url = get_site_url()
    await message.answer(
        f"💜 <b>MusicUz loyihasini qo'llab-quvvatlash:</b>\n\n"
        f"💳 Karta: <code>{card}</code>\n"
        f"👤 Egasi: <b>{owner}</b>\n\n"
        f"🎯 Donatingiz tezkor serverlar va yangi qo'shiqlar uchun sarflanadi ✨",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💜 To'liq ko'rish", url=f"{site_url}/#/donate")],
            [InlineKeyboardButton(text="🌐 Saytga o'tish", url=site_url)],
        ])
    )


@dp.message(F.contact)
async def on_contact(message: types.Message):
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("❌ Iltimos, faqat o'zingizning raqamingizni yuboring.")
        return

    phone = norm_phone(contact.phone_number)
    name_parts = [contact.first_name or "", contact.last_name or ""]
    name = " ".join(p for p in name_parts if p).strip() or "Foydalanuvchi"

    c = db()
    c.execute(
        "INSERT INTO tg_contacts (phone, chat_id, tg_name) VALUES (?,?,?) "
        "ON CONFLICT(phone) DO UPDATE SET chat_id=excluded.chat_id, tg_name=excluded.tg_name",
        (phone, message.chat.id, name)
    )
    c.commit()

    site_url = get_site_url()
    await message.answer(
        f"✅ Raqamingiz bog'landi: +{phone}\n\n"
        f"Endi quyidagi havola orqali saytga kiring va raqamingizni kiriting:\n"
        f"🔗 <a href=\"{site_url}\">{site_url}</a>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🌐 Saytga o'tish", url=site_url)
        ]])
    )
