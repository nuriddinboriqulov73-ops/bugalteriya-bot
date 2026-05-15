import logging
import os
import asyncio
import threading
import requests
from openai import OpenAI

from bs4 import BeautifulSoup

from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.environ.get("BOT_TOKEN" )
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

LEX_URL = "https://lex.uz/acts/-1357627"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)


# ===================== GEMINI =====================

client = OpenAI(api_key=OPENAI_API_KEY)



# ===================== USER DATA =====================

user_settings = {}

subscribers = set()


def get_lang(user_id):

    return user_settings.get(user_id, {}).get("lang", "uz")


def set_lang(user_id, lang):

    if user_id not in user_settings:
        user_settings[user_id] = {}

    user_settings[user_id]["lang"] = lang


# ===================== SCHYOTLAR =====================

_cache = {
    "data": None,
    "loaded": False
}


def fetch_schyotlar():

    try:

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        resp = requests.get(
            LEX_URL,
            headers=headers,
            timeout=15
        )

        resp.encoding = "utf-8"

        soup = BeautifulSoup(
            resp.text,
            "html.parser"
        )

        schyotlar = []

        table = soup.find("table")

        if not table:
            return []

        for row in table.find_all("tr"):

            cols = row.find_all("td")

            if len(cols) >= 2:

                raqam = cols[0].get_text(strip=True)

                nom = cols[1].get_text(strip=True)

                tur = (
                    cols[2].get_text(strip=True)
                    if len(cols) > 2 else ""
                )

                if (
                    raqam and
                    nom and
                    any(c.isdigit() for c in raqam)
                ):

                    schyotlar.append({
                        "raqam": raqam,
                        "nom": nom,
                        "tur": tur
                    })

        return schyotlar

    except Exception as e:

        logger.error(f"Fetch xato: {e}")

        return []


def get_schyotlar():

    if not _cache["loaded"]:

        _cache["data"] = fetch_schyotlar()

        _cache["loaded"] = True

    return _cache["data"]


# ===================== GEMINI AI =====================

def ask_ai(question, lang, context_text=""):

    try:

        prompt = f"""
        Sen professional buxgaltersan.

        Kontekst:
        {context_text}

        Savol:
        {question}

        Til:
        {lang}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content

    except Exception as e:

        logger.error(f"AI xato: {e}")

        return f"❌ Xato: {e}"
    


# ===================== DARS =====================

def generate_daily_lesson(lang, lesson_number):

    try:

        topic = (
            f"Buxgalteriya darsi #{lesson_number}"
            if lang == "uz"
            else f"Урок бухгалтерии #{lesson_number}"
        )

        prompt = (
            f"{topic} haqida professional dars yoz"
            if lang == "uz"
            else f"Напиши урок про {topic}"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content, topic

    except Exception as e:

        logger.error(f"Dars xato: {e}")

        return "", ""

# ===================== START =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [[
        InlineKeyboardButton(
            "🇺🇿 O'zbekcha",
            callback_data="lang_uz"
        ),

        InlineKeyboardButton(
            "🇷🇺 Русский",
            callback_data="lang_ru"
        )
    ]]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 Xush kelibsiz!\n\nTilni tanlang:",
        reply_markup=reply_markup
    )


# ===================== MENU =====================

async def show_main_menu(
        msg,
        lang,
        user_id,
        edit=False
):

    subscribed = user_id in subscribers

    if lang == "uz":

        text = (
            "🏠 Bosh menyu\n\n"
            "🤖 AI Buxgalter\n"
            "📋 Schyotlar rejasi\n"
            f"📅 Darslar: {'✅ Obuna bor' if subscribed else '❌ Obuna yoq'}"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🤖 AI Savol",
                    callback_data="ai"
                )
            ],

            [
                InlineKeyboardButton(
                    "📋 Schyotlar",
                    callback_data="sch"
                )
            ],

            [
                InlineKeyboardButton(
                    "🔔 Obuna"
                    if not subscribed
                    else "🔕 Chiqish",

                    callback_data="sub"
                    if not subscribed
                    else "unsub"
                )
            ]
        ]

    else:

        text = (
            "🏠 Главное меню\n\n"
            "🤖 AI Бухгалтер\n"
            "📋 План счетов"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🤖 AI",
                    callback_data="ai"
                )
            ],

            [
                InlineKeyboardButton(
                    "📋 Счета",
                    callback_data="sch"
                )
            ]
        ]

    rm = InlineKeyboardMarkup(keyboard)

    if edit:

        await msg.edit_text(
            text,
            reply_markup=rm
        )

    else:

        await msg.reply_text(
            text,
            reply_markup=rm
        )


# ===================== BUTTONS =====================

async def button_handler(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data

    user_id = query.from_user.id

    lang = get_lang(user_id)

    if data in ("lang_uz", "lang_ru"):

        new_lang = (
            "uz"
            if data == "lang_uz"
            else "ru"
        )

        set_lang(user_id, new_lang)

        await show_main_menu(
            query.message,
            new_lang,
            user_id,
            edit=True
        )

    elif data == "sub":

        subscribers.add(user_id)

        await query.message.reply_text(
            "✅ Obuna boldingiz"
        )

    elif data == "unsub":

        subscribers.discard(user_id)

        await query.message.reply_text(
            "❌ Obuna bekor qilindi"
        )

    elif data == "ai":

        await query.message.reply_text(
            "✍️ Savolingizni yozing"
        )

    elif data == "sch":

        sch = get_schyotlar()

        if not sch:

            await query.message.reply_text(
                "❌ Malumot topilmadi"
            )

            return

        text = "\n".join([
            f"{s['raqam']} - {s['nom']}"
            for s in sch[:100]
        ])

        chunks = [
            text[i:i + 4000]
            for i in range(0, len(text), 4000)
        ]

        for ch in chunks:

            await query.message.reply_text(ch)


# ===================== AI MESSAGE =====================

async def handle_ai_question(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    lang = get_lang(user_id)

    question = update.message.text

    wait = await update.message.reply_text(
        "🤔 AI oylayapti..."
    )

    sch = get_schyotlar()

    context_text = "; ".join([
        f"{s['raqam']} {s['nom']}"
        for s in sch[:10]
    ])

    answer = ask_ai(
        question,
        lang,
        context_text
    )

    await wait.delete()

    await update.message.reply_text(answer)


# ===================== DAILY LESSON =====================

async def send_daily_lesson(app):

    if not subscribers:
        return

    lesson_num = lesson_counter["count"]

    lesson_uz, topic_uz = generate_daily_lesson(
        "uz",
        lesson_num
    )

    lesson_ru, topic_ru = generate_daily_lesson(
        "ru",
        lesson_num
    )

    lesson_counter["count"] += 1

    for user_id in list(subscribers):

        try:

            lang = get_lang(user_id)

            lesson = (
                lesson_uz
                if lang == "uz"
                else lesson_ru
            )

            topic = (
                topic_uz
                if lang == "uz"
                else topic_ru
            )

            text = f"""
📚 {topic}

{lesson}
"""

            chunks = [
                text[i:i + 4000]
                for i in range(0, len(text), 4000)
            ]

            for ch in chunks:

                await app.bot.send_message(
                    chat_id=user_id,
                    text=ch
                )

        except Exception as e:

            logger.error(f"Dars xato: {e}")


# ===================== WEB SERVER =====================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.end_headers()

        self.wfile.write(b"OK")

    def log_message(self, *args):

        pass


def run_web_server():

    port = int(os.environ.get("PORT", 8080))

    HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    ).serve_forever()

# ===================== MAIN =====================

async def main():

    # WEB SERVER
    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    # BOT
    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # HANDLERS

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_ai_question
        )
    )

    logger.info("Bot ishga tushdi")

    # BOT START

    await app.initialize()

    await app.start()

    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES
    )

    # LOOP

    await asyncio.Event().wait()


# ===================== RUN =====================

if __name__ == "__main__":

    asyncio.run(main())
