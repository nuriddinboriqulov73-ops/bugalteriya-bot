import logging
import os
import asyncio
import threading
import json
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler


BOT_TOKEN = os.environ.get("BOT_TOKEN")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

LEX_URL = "https://lex.uz/acts/-1357627"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_settings = {}
subscribers = set()

def get_lang(uid): return user_settings.get(uid, {}).get("lang", "uz")
def set_lang(uid, lang):
    if uid not in user_settings: user_settings[uid] = {}
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
            logger.error(f"Fetch: {e}")
            _cache["data"] = []
        _cache["loaded"] = True
    return _cache["data"]

def reload_cache():
    _cache["loaded"] = False
    return get_schyotlar()

# === AI - requests orqali (anthropic kutubxonasisiz) ===
def ask_ai(question, lang, ctx=""):

    if not ANTHROPIC_API_KEY:
        return (
            "AI yoq - ANTHROPIC_API_KEY sozlanmagan"
            if lang == "uz"
            else "AI недоступен"
        )

    try:

        if lang == "uz":
            system = (
                "Siz Ozbekiston buxgalteriyasi mutaxassisiiz. "
                "Ozbek tilida aniq javob bering."
            )
        else:
            system = (
                "Ty buxgalter Uzbekistana. "
                "Otvechay na russkom yazyke."
            )

        if ctx:
            system += f" Schyotlar: {ctx}"

        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
         "model": "claude-opus-4-7",
                "max_tokens": 1500,
                "system": system,
                "messages": [
                    {
                        "role": "user",
                        "content": question
                    }
                ]
            },
            timeout=300
        )

        data = resp.json()

        if "content" in data:
            return data["content"][0]["text"]

        return str(data)

    except Exception as e:

        logger.error(f"AI xato: {e}")

        return f"AI xatosi: {e}"

TOPICS_UZ = ["Buxgalteriya tamoyillari","Aktivlar tasnifi","Passivlar va kapital",
              "Daromad va xarajatlar","Kassa va bank","Asosiy vositalar amortizatsiya",
              "Nomoddiy aktivlar","Tovar-moddiy boyliklar","Debitorlik qarzdorligi",
              "Ish haqi hisobi","QQS va soliq hisoboti","Moliyaviy hisobot",
              "Balans tuzilishi","Foyda va zarar","Moliyaviy tahlil","Audit va nazorat",
              "Budjet hisobi","IFRS standartlari","Sugurta buxgalteriyasi","1C dasturi"]
TOPICS_RU = ["Principy buxuchyota","Klassifikaciya aktivov","Passivy i kapital",
              "Dokhody i raskhody","Kassa i bank","Osnovnye sredstva amortizaciya",
              "Nematerialnye aktivy","TMC","Debitorka","Uchet zarplaty",
              "NDS i nalogi","Finansovaya otchetnost","Balans","Pribyl i ubytok",
              "Finansovyy analiz","Audit","Byudzhet","MSFO","Strakhovanie","1S"]

lesson_counter = {"n": 1}

def gen_lesson(lang, n):
    if not ANTHROPIC_API_KEY: return "", ""
    topics = TOPICS_UZ if lang == "uz" else TOPICS_RU
    topic = topics[(n-1) % len(topics)]
    try:
        if lang == "uz":
            p = f"{topic} mavzusida {n}-dars yoz. 1)Mavzu va maqsad 2)Nazariya 3-5 band 3)Amaliy misol 4)Xulosalar 5)Savol. Emoji ishlat."
        else:
            p = f"Urok {n} na temu {topic}. 1)Tema 2)Teoriya 3-5 punktov 3)Primer 4)Vyvody 5)Vopros. Ispolzuy emoji."
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
          "model": "claude-opus-4-7",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": p}]
            },
            timeout=60
        )
        data = resp.json()
        return data["content"][0]["text"], topic
    except Exception as e:
        logger.error(f"Lesson: {e}")
        return "", ""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("Ozbekcha", callback_data="lang_uz"),
           InlineKeyboardButton("Russkiy", callback_data="lang_ru")]]
    await update.message.reply_text(
        "Xush kelibsiz! / Dobro pozhalovat!\n\nTilni tanlang / Vyberi yazyk:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def menu(msg, lang, uid, edit=False):
    sub = uid in subscribers
    if lang == "uz":
        txt = (f"Bosh menyu\n\n"
               f"- AI buxgalter: har qanday savol\n"
               f"- Schyotlar rejasi: lex.uz\n"
               f"- Kunlik darslar: {'Obuna bor' if sub else 'Obuna yoq'}\n\n"
               f"Savol yozing yoki tugma bosing:")
        kb = [[InlineKeyboardButton("AI ga savol", callback_data="ai_hint")],
              [InlineKeyboardButton("Schyotlar rejasi", callback_data="sch_menu")],
              [InlineKeyboardButton("Darsdan chiqish" if sub else "Darslarga obuna", callback_data="unsub" if sub else "sub")],
              [InlineKeyboardButton("Tilni ozgartirish", callback_data="chg_lang")]]
    else:
        txt = (f"Glavnoe menyu\n\n"
               f"- AI buxgalter: lyuboy vopros\n"
               f"- Plan schetov: lex.uz\n"
               f"- Uroki: {'Podpisan' if sub else 'Ne podpisan'}\n\n"
               f"Zadayte vopros ili nazhite knopku:")
        kb = [[InlineKeyboardButton("Vopros AI", callback_data="ai_hint")],
              [InlineKeyboardButton("Plan schetov", callback_data="sch_menu")],
              [InlineKeyboardButton("Otpisatsya" if sub else "Podpisatsya", callback_data="unsub" if sub else "sub")],
              [InlineKeyboardButton("Smenit yazyk", callback_data="chg_lang")]]
    rm = InlineKeyboardMarkup(kb)
    try:
        if edit: await msg.edit_text(txt, reply_markup=rm)
        else: await msg.reply_text(txt, reply_markup=rm)
    except Exception:
        await msg.reply_text(txt, reply_markup=rm)

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await menu(update.message, get_lang(uid), uid)

async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_lang(uid)
    m = await update.message.reply_text("Yangilanmoqda..." if lang == "uz" else "Obnovleniye...")
    s = reload_cache()
    await m.edit_text(f"Yangilandi! {len(s)} ta." if lang == "uz" else f"Obnovleno! {len(s)}.")

async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_lang(uid)
    q = update.message.text.strip()
    sch = get_schyotlar()
    ctx = "; ".join([f"{s['raqam']}: {s['nom']}" for s in sch
                     if any(w.lower() in q.lower() for w in s['nom'].split())][:5])
    wm = await update.message.reply_text("Tahlil qilinmoqda..." if lang == "uz" else "Analiziruyetsya...")
    ans = ask_ai(q, lang, ctx)
    await wm.delete()
    await update.message.reply_text("AI Buxgalter:\n\n" + ans)

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id
    lang = get_lang(uid)

    if d in ("lang_uz", "lang_ru"):
        nl = "uz" if d == "lang_uz" else "ru"
        set_lang(uid, nl)
        subscribers.add(uid)
        await menu(q.message, nl, uid, edit=True)
    elif d == "chg_lang":
        kb = [[InlineKeyboardButton("Ozbekcha", callback_data="lang_uz"),
               InlineKeyboardButton("Russkiy", callback_data="lang_ru")]]
        await q.edit_message_text("Tilni tanlang:", reply_markup=InlineKeyboardMarkup(kb))
    elif d == "sub":
        subscribers.add(uid)
        await q.message.reply_text("Obuna boldingiz! Har kuni soat 10:00 da dars keladi." if lang == "uz"
                                   else "Podpisalis! Kazhdyy den v 10:00.")
        await menu(q.message, lang, uid)
    elif d == "unsub":
        subscribers.discard(uid)
        await q.message.reply_text("Obuna bekor." if lang == "uz" else "Otpisalis.")
        await menu(q.message, lang, uid)
    elif d == "ai_hint":
        await q.message.reply_text(
            "Savolingizni yozing:\nMasalan: QQS qanday hisoblanadi?" if lang == "uz"
            else "Napishite vopros:\nNaprimer: Kak schitat NDS?"
        )
    elif d == "sch_menu":
        sch = get_schyotlar()
        if not sch:
            await q.message.reply_text("Malumot yuklanmadi.")
            return
        guruhlar = {}
        for s in sch:
            r = s["raqam"]
            k = (r[0]+"000") if r and r[0].isdigit() else "X"
            guruhlar.setdefault(k, []).append(s)
        kb = [[InlineKeyboardButton(f"{g} seriya ({len(v)} ta)", callback_data=f"g_{g}")]
              for g, v in sorted(guruhlar.items())]
        kb.append([InlineKeyboardButton("Orqaga" if lang == "uz" else "Nazad", callback_data="back")])
        await q.edit_message_text(
            f"Schyotlar: {len(sch)} ta" if lang == "uz" else f"Schety: {len(sch)}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    elif d.startswith("g_"):
        g = d[2:]
        sch = get_schyotlar()
        res = [s for s in sch if s["raqam"] and s["raqam"][0].isdigit() and (s["raqam"][0]+"000") == g]
        txt = f"{g} seriyasi {len(res)} ta:\n\n" + "\n".join(
            [f"{s['raqam']} - {s['nom']}" + (f" [{s['tur']}]" if s['tur'] else "") for s in res])
        for ch in [txt[i:i+4000] for i in range(0, len(txt), 4000)]:
            await q.message.reply_text(ch)
    elif d == "back":
        await menu(q.message, lang, uid, edit=True)

def send_lessons_sync(app):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(_send(app))
    finally: loop.close()

async def _send(app):
    if not subscribers: return
    n = lesson_counter["n"]
    lu, tu = gen_lesson("uz", n)
    lr, tr = gen_lesson("ru", n)
    lesson_counter["n"] += 1
    for uid in list(subscribers):
        try:
            lang = get_lang(uid)
            lesson = lu if lang == "uz" else lr
            topic = tu if lang == "uz" else tr
            if not lesson: continue
            hdr = f"Kunlik Dars #{n}\nMavzu: {topic}\n\n" if lang == "uz" else f"Urok #{n}\nTema: {topic}\n\n"
            txt = hdr + lesson
            for ch in [txt[i:i+4000] for i in range(0, len(txt), 4000)]:
                await app.bot.send_message(chat_id=uid, text=ch)
        except Exception as e:
            logger.error(f"User {uid}: {e}")
            subscribers.discard(uid)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *a): pass

def web():
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8080))), H).serve_forever()

def main():
    threading.Thread(target=web, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(CallbackQueryHandler(btn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
    sc = BackgroundScheduler()
    sc.add_job(send_lessons_sync, "cron", hour=5, minute=0, args=[app])
    sc.start()
    logger.info("Schyotlar yuklanmoqda...")
    get_schyotlar()
    logger.info("Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
