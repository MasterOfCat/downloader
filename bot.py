import asyncio
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import Command, Text
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
    ReplyKeyboardMarkup,
)
from aiogram.utils import executor
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    stars_price: int
    max_video_size_mb: int
    default_language: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    default_language = os.getenv("DEFAULT_LANGUAGE", "ru").strip().lower()
    if default_language not in {"ru", "en"}:
        default_language = "ru"

    return Config(
        bot_token=token,
        stars_price=int(os.getenv("STARS_PRICE", "50")),
        max_video_size_mb=int(os.getenv("MAX_VIDEO_SIZE_MB", "49")),
        default_language=default_language,
    )


TEXTS = {
    "ru": {
        "welcome": (
            "👋 Привет! Я бот для скачивания видео из TikTok и YouTube.\n\n"
            "🎁 Первое скачивание бесплатно.\n"
            "⭐️ Все следующие скачивания — за {price} Stars.\n\n"
            "Просто пришли ссылку на видео."
        ),
        "language_set": "Язык переключён на русский.",
        "choose_language": "Выберите язык:",
        "unsupported": "Пока я умею работать только с ссылками TikTok и YouTube.",
        "processing": "⏬ Скачиваю видео... Это может занять до минуты.",
        "download_error": "Не удалось скачать видео. Проверь ссылку и попробуй ещё раз.",
        "video_too_big": "Видео слишком большое для отправки в Telegram.",
        "send_link": "Отправь ссылку на видео из TikTok или YouTube.",
        "payment_needed": "Для следующего скачивания нужна оплата: {price} Stars.",
        "pay_button": "Оплатить ⭐️",
        "invoice_title": "Скачивание видео",
        "invoice_desc": "Одно скачивание видео из TikTok/YouTube",
        "payment_success": "✅ Оплата прошла. Начинаю скачивание.",
        "payment_cancel": "Платёж не найден. Отправьте ссылку ещё раз.",
        "payment_invalid": "Не удалось создать платёж. Попробуйте отправить ссылку снова.",
        "payment_already_paid": "Этот запрос уже оплачен. Отправьте новую ссылку для следующего скачивания.",
        "payment_amount_mismatch": "Сумма платежа не совпадает с ценой скачивания.",
        "faq_title": "❓ FAQ — Частые вопросы",
        "faq_intro": "Выберите раздел, и я покажу ответ.",
        "faq_download": (
            "📥 <b>Как скачать видео?</b>\n"
            "1) Нажмите /start (если запускаете впервые).\n"
            "2) Отправьте ссылку на TikTok или YouTube.\n"
            "3) Я скачаю и пришлю файл."
        ),
        "faq_payment": (
            "⭐️ <b>Как работает оплата?</b>\n"
            "• Первое скачивание для каждого пользователя бесплатно.\n"
            "• Начиная со второго — оплата {price} Stars за одно скачивание.\n"
            "• Нажмите кнопку оплаты и подтвердите платёж."
        ),
        "faq_limits": (
            "📌 <b>Ограничения</b>\n"
            "• Поддерживаются только tiktok.com, youtube.com и youtu.be.\n"
            "• Очень большие видео Telegram может не принять.\n"
            "• Некоторые ролики могут быть недоступны из-за региональных ограничений."
        ),
        "faq_privacy": (
            "🔐 <b>Что с приватностью?</b>\n"
            "• Бот хранит минимум данных: язык, флаг бесплатного скачивания и историю платных запросов.\n"
            "• Данные хранятся в локальной SQLite базе."
        ),
        "faq_button": "❓ FAQ",
        "lang_button": "🌐 Язык",
        "help_button": "ℹ️ Как пользоваться",
        "help_text": (
            "ℹ️ <b>Как пользоваться ботом</b>\n"
            "• Отправьте ссылку TikTok/YouTube.\n"
            "• Для часто задаваемых вопросов нажмите кнопку FAQ.\n"
            "• Для смены языка нажмите кнопку Язык."
        ),
        "faq_topic_download": "Как скачать",
        "faq_topic_payment": "Оплата",
        "faq_topic_limits": "Ограничения",
        "faq_topic_privacy": "Приватность",
    },
    "en": {
        "welcome": (
            "👋 Hi! I'm a bot for downloading videos from TikTok and YouTube.\n\n"
            "🎁 First download is free.\n"
            "⭐️ All next downloads cost {price} Stars.\n\n"
            "Just send me a video link."
        ),
        "language_set": "Language switched to English.",
        "choose_language": "Choose a language:",
        "unsupported": "I currently support TikTok and YouTube links only.",
        "processing": "⏬ Downloading video... It may take up to a minute.",
        "download_error": "Could not download this video. Please check the link and try again.",
        "video_too_big": "The video is too large to send via Telegram.",
        "send_link": "Send a TikTok or YouTube video link.",
        "payment_needed": "Next download requires payment: {price} Stars.",
        "pay_button": "Pay ⭐️",
        "invoice_title": "Video download",
        "invoice_desc": "One TikTok/YouTube video download",
        "payment_success": "✅ Payment successful. Starting download.",
        "payment_cancel": "Payment was not found. Please send the link again.",
        "payment_invalid": "Unable to create payment. Please send the link again.",
        "payment_already_paid": "This request is already paid. Send a new link for the next download.",
        "payment_amount_mismatch": "Payment amount does not match the download price.",
        "faq_title": "❓ FAQ",
        "faq_intro": "Choose a section and I will show the answer.",
        "faq_download": (
            "📥 <b>How to download a video?</b>\n"
            "1) Press /start (first launch).\n"
            "2) Send a TikTok or YouTube link.\n"
            "3) I download and send the file."
        ),
        "faq_payment": (
            "⭐️ <b>How does payment work?</b>\n"
            "• First download is free per user.\n"
            "• Starting from the second download, it costs {price} Stars per video.\n"
            "• Press the payment button and confirm purchase."
        ),
        "faq_limits": (
            "📌 <b>Limits</b>\n"
            "• Supported links: tiktok.com, youtube.com, youtu.be.\n"
            "• Very large videos may be rejected by Telegram.\n"
            "• Some videos can be unavailable due to regional restrictions."
        ),
        "faq_privacy": (
            "🔐 <b>Privacy</b>\n"
            "• The bot stores minimal data: language, free-use flag, and paid request history.\n"
            "• Data is stored in a local SQLite database."
        ),
        "faq_button": "❓ FAQ",
        "lang_button": "🌐 Language",
        "help_button": "ℹ️ How to use",
        "help_text": (
            "ℹ️ <b>How to use this bot</b>\n"
            "• Send a TikTok/YouTube link.\n"
            "• Use FAQ button for common questions.\n"
            "• Use Language button to switch language."
        ),
        "faq_topic_download": "How to download",
        "faq_topic_payment": "Payment",
        "faq_topic_limits": "Limits",
        "faq_topic_privacy": "Privacy",
    },
}

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


class DB:
    def __init__(self, path: str = "bot.db") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL,
                free_used INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                paid INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def ensure_user(self, user_id: int, default_lang: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO users(user_id, language, free_used) VALUES(?, ?, 0)",
            (user_id, default_lang),
        )
        self.conn.commit()

    def get_user(self, user_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT user_id, language, free_used FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("User not found")
        return row

    def set_language(self, user_id: int, language: str) -> None:
        self.conn.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
        self.conn.commit()

    def mark_free_used(self, user_id: int) -> None:
        self.conn.execute("UPDATE users SET free_used = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def create_request(self, user_id: int, url: str, platform: str, paid: int) -> int:
        cursor = self.conn.execute(
            "INSERT INTO requests(user_id, url, platform, paid) VALUES(?, ?, ?, ?)",
            (user_id, url, platform, paid),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def mark_request_paid(self, request_id: int) -> None:
        self.conn.execute("UPDATE requests SET paid = 1 WHERE id = ?", (request_id,))
        self.conn.commit()

    def get_request(self, request_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, user_id, url, platform, paid FROM requests WHERE id = ?", (request_id,)
        ).fetchone()


def t(lang: str, key: str, **kwargs: object) -> str:
    if lang not in TEXTS:
        lang = "en"
    return TEXTS[lang][key].format(**kwargs)


def platform_from_url(url: str) -> Optional[str]:
    lowered = url.lower()
    if "tiktok.com" in lowered:
        return "tiktok"
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    return None


def language_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="English", callback_data="lang:en"),
    )
    return keyboard


def payment_keyboard(lang: str, request_id: int) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(text=t(lang, "pay_button"), callback_data=f"pay:{request_id}"))
    return keyboard


def faq_keyboard(lang: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(text=t(lang, "faq_topic_download"), callback_data="faq:download"))
    keyboard.add(InlineKeyboardButton(text=t(lang, "faq_topic_payment"), callback_data="faq:payment"))
    keyboard.add(InlineKeyboardButton(text=t(lang, "faq_topic_limits"), callback_data="faq:limits"))
    keyboard.add(InlineKeyboardButton(text=t(lang, "faq_topic_privacy"), callback_data="faq:privacy"))
    return keyboard


def main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton(t(lang, "faq_button")), KeyboardButton(t(lang, "lang_button")))
    keyboard.row(KeyboardButton(t(lang, "help_button")))
    return keyboard


def parse_first_url(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = URL_RE.search(text)
    return match.group(0) if match else None


def build_invoice_payload(request_id: int) -> str:
    return f"download:{request_id}"


def parse_invoice_payload(payload: str) -> Optional[int]:
    if not payload.startswith("download:"):
        return None
    value = payload.split(":", 1)[1]
    if not value.isdigit():
        return None
    return int(value)


async def download_video(url: str) -> Optional[Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="tg_video_"))
    output_template = str(temp_dir / "video.%(ext)s")

    process = await asyncio.create_subprocess_exec(
        "yt-dlp",
        "--no-playlist",
        "--merge-output-format",
        "mp4",
        "-f",
        "mp4/best",
        "-o",
        output_template,
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()

    if process.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    files = list(temp_dir.glob("video.*"))
    if not files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    return files[0]


config = load_config()
db = DB()
bot = Bot(token=config.bot_token, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)


async def send_faq(message: types.Message, lang: str) -> None:
    await message.answer(
        f"{t(lang, 'faq_title')}\n\n{t(lang, 'faq_intro')}",
        reply_markup=faq_keyboard(lang),
    )


async def process_request(message: types.Message, url: str, is_free: bool) -> None:
    user_id = message.from_user.id
    user = db.get_user(user_id)
    lang = user["language"]

    await message.answer(t(lang, "processing"))
    video_path = await download_video(url)

    if video_path is None:
        await message.answer(t(lang, "download_error"))
        return

    try:
        size_mb = video_path.stat().st_size / (1024 * 1024)
        if size_mb > config.max_video_size_mb:
            await message.answer(t(lang, "video_too_big"))
            return

        await message.answer_video(types.InputFile(str(video_path)))
        if is_free:
            db.mark_free_used(user_id)
    finally:
        shutil.rmtree(video_path.parent, ignore_errors=True)


@dp.message_handler(commands=["start"])
async def start(message: types.Message) -> None:
    user_id = message.from_user.id
    db.ensure_user(user_id, config.default_language)
    user = db.get_user(user_id)
    lang = user["language"]

    await message.answer(
        t(lang, "welcome", price=config.stars_price),
        reply_markup=main_menu_keyboard(lang),
    )
    await message.answer(t(lang, "choose_language"), reply_markup=language_keyboard())


@dp.message_handler(Command("faq"))
async def faq_command(message: types.Message) -> None:
    user_id = message.from_user.id
    db.ensure_user(user_id, config.default_language)
    lang = db.get_user(user_id)["language"]
    await send_faq(message, lang)


@dp.message_handler(Command("help"))
async def help_command(message: types.Message) -> None:
    user_id = message.from_user.id
    db.ensure_user(user_id, config.default_language)
    lang = db.get_user(user_id)["language"]
    await message.answer(t(lang, "help_text"), reply_markup=main_menu_keyboard(lang))


@dp.callback_query_handler(Text(startswith="lang:"))
async def change_lang(call: types.CallbackQuery) -> None:
    user_id = call.from_user.id
    db.ensure_user(user_id, config.default_language)

    lang = call.data.split(":", 1)[1]
    if lang not in TEXTS:
        lang = config.default_language

    db.set_language(user_id, lang)
    await call.message.answer(t(lang, "language_set"), reply_markup=main_menu_keyboard(lang))
    await call.answer()


@dp.callback_query_handler(Text(startswith="faq:"))
async def faq_details(call: types.CallbackQuery) -> None:
    user_id = call.from_user.id
    db.ensure_user(user_id, config.default_language)
    lang = db.get_user(user_id)["language"]

    topic = call.data.split(":", 1)[1]
    topic_key = {
        "download": "faq_download",
        "payment": "faq_payment",
        "limits": "faq_limits",
        "privacy": "faq_privacy",
    }.get(topic)

    if not topic_key:
        await call.answer()
        return

    await call.message.answer(t(lang, topic_key, price=config.stars_price), reply_markup=faq_keyboard(lang))
    await call.answer()


@dp.callback_query_handler(Text(startswith="pay:"))
async def create_invoice(call: types.CallbackQuery) -> None:
    user_id = call.from_user.id
    db.ensure_user(user_id, config.default_language)
    lang = db.get_user(user_id)["language"]

    value = call.data.split(":", 1)[1]
    if not value.isdigit():
        await call.answer(t(lang, "payment_invalid"), show_alert=True)
        return

    request_id = int(value)
    req = db.get_request(request_id)
    if req is None or req["user_id"] != user_id:
        await call.answer(t(lang, "payment_cancel"), show_alert=True)
        return
    if req["paid"] == 1:
        await call.answer(t(lang, "payment_already_paid"), show_alert=True)
        return

    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title=t(lang, "invoice_title"),
        description=t(lang, "invoice_desc"),
        payload=build_invoice_payload(request_id),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=t(lang, "invoice_title"), amount=config.stars_price)],
        start_parameter="video-download",
    )
    await call.answer()


@dp.pre_checkout_query_handler(lambda q: True)
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery) -> None:
    request_id = parse_invoice_payload(pre_checkout_query.invoice_payload)
    if request_id is None:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Invalid payload")
        return

    req = db.get_request(request_id)
    if req is None:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Request not found")
        return
    if req["user_id"] != pre_checkout_query.from_user.id:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Invalid request owner")
        return
    if req["paid"] == 1:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, error_message="Request already paid")
        return

    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message_handler(content_types=types.ContentTypes.SUCCESSFUL_PAYMENT)
async def successful_payment_handler(message: types.Message) -> None:
    user_id = message.from_user.id
    db.ensure_user(user_id, config.default_language)
    lang = db.get_user(user_id)["language"]

    request_id = parse_invoice_payload(message.successful_payment.invoice_payload)
    if request_id is None:
        await message.answer(t(lang, "payment_cancel"))
        return

    req = db.get_request(request_id)
    if req is None or req["user_id"] != user_id:
        await message.answer(t(lang, "payment_cancel"))
        return
    if req["paid"] == 1:
        await message.answer(t(lang, "payment_already_paid"), reply_markup=main_menu_keyboard(lang))
        return

    payment = message.successful_payment
    if payment.currency != "XTR" or payment.total_amount != config.stars_price:
        await message.answer(t(lang, "payment_amount_mismatch"), reply_markup=main_menu_keyboard(lang))
        return

    db.mark_request_paid(request_id)
    await message.answer(t(lang, "payment_success"), reply_markup=main_menu_keyboard(lang))
    await process_request(message, req["url"], is_free=False)


@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def on_text(message: types.Message) -> None:
    user_id = message.from_user.id
    db.ensure_user(user_id, config.default_language)
    user = db.get_user(user_id)
    lang = user["language"]

    text = (message.text or "").strip()
    if text in {t(lang, "faq_button"), "/faq"}:
        await send_faq(message, lang)
        return
    if text in {t(lang, "lang_button"), "/language"}:
        await message.answer(t(lang, "choose_language"), reply_markup=language_keyboard())
        return
    if text in {t(lang, "help_button"), "/help"}:
        await message.answer(t(lang, "help_text"), reply_markup=main_menu_keyboard(lang))
        return

    url = parse_first_url(text)
    if not url:
        await message.answer(t(lang, "send_link"), reply_markup=main_menu_keyboard(lang))
        return

    platform = platform_from_url(url)
    if not platform:
        await message.answer(t(lang, "unsupported"), reply_markup=main_menu_keyboard(lang))
        return

    if user["free_used"] == 0:
        await process_request(message, url, is_free=True)
        return

    request_id = db.create_request(user_id=user_id, url=url, platform=platform, paid=0)
    await message.answer(
        t(lang, "payment_needed", price=config.stars_price),
        reply_markup=payment_keyboard(lang, request_id),
    )


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
