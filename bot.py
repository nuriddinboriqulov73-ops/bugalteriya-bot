# bot.py (to‘g‘rilangan)

```python
import logging
import os
import asyncio
import threading
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850667627:AAEYJOyVyJzGGKuYbQNlpYnHLBK9GdtPh_U" )
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY","AIzaSyBUlHIHlTGJDcHCwLlXIEvOy3pOcdyP3Os")
LEX_URL = "https://lex.uz/acts/-1357627"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_settings = {}
subscribers = set()

def get_lang(uid):
    return user_settings.get(uid, {}).get("lang", "uz")

def set_lang(uid, lang):
    if uid not in user_settings:
        user_settings[uid] = {}
    user_settings[uid]["lang"] = lang

_cache = {"data": None, "loaded": False}

def get_schyotlar():
    if not _cache["loaded"]:
        try:
            r = requests.get(LEX_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            data = []
            table = soup.find("table")

            if table:
                for row in table.find_all("tr"):
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        rq = cols[0].get_text(strip=True)
                        nm = cols[1].get_text(strip=True)
                        tr = cols[2].get_text(strip=True) if len(cols) > 2 else ""

                        if rq and nm and any(c.isdigit() for c in rq):
                            data.append({"raqam": rq, "nom": nm, "tur": tr})

            _cache["data"] = data

        except Exception as e:
            logger.error(f"Fetch error: {e}")
            _cache["data"] = []

        _cache["loaded"] = True

    return _cache["data"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[
        InlineKeyboardButton("Ozbekcha", callback_data="lang_uz"),
        InlineKeyboardButton("Russkiy", callback_data="lang_ru")
    ]]

    await update.message.reply_text(
        "Xush kelibsiz! / Добро пожаловать!\n\nTilni tanlang:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def menu(msg, lang, uid, edit=False):
    if lang == "uz":
        txt = "Bosh menyu\n\nSavol yozing yoki tugma bosing"
        kb = [[InlineKeyboardButton("Schyotlar", callback_data="sch_menu")]]
    else:
        txt = "Главное меню\n\nНапишите вопрос"
        kb = [[InlineKeyboardButton("План счетов", callback_data="sch_menu")]]

    rm = InlineKeyboardMarkup(kb)

    if edit:
        await msg.edit_text(txt, reply_markup=rm)
    else:
        await msg.reply_text(txt, reply_markup=rm)

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    d = q.data
    uid = q.from_user.id

    if d in ("lang_uz", "lang_ru"):
        lang = "uz" if d == "lang_uz" else "ru"
        set_lang(uid, lang)
        await menu(q.message, lang, uid, edit=True)

    elif d == "sch_menu":
        sch = get_schyotlar()

        if not sch:
            await q.message.reply_text("Ma'lumot topilmadi")
            return

        txt = "\n".join([
            f"{s['raqam']} - {s['nom']}"
            for s in sch[:50]
        ])

        for ch in [txt[i:i+4000] for i in range(0, len(txt), 4000)]:
            await q.message.reply_text(ch)

async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    await update.message.reply_text(f"Siz yozdingiz:\n\n{txt}")

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *a):
        pass


def web():
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8080))), H).serve_forever()


def main():
    threading.Thread(target=web, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))

    logger.info("Bot ishga tushdi!")

    app.run_polling()


if __name__ == "__main__":
    main()
```

# requirements.txt

```txt
python-telegram-bot==20.7
google-generativeai==0.3.2
requests==2.31.0
beautifulsoup4==4.12.3
lxml==5.1.0
```
