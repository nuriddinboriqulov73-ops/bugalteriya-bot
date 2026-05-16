import logging
import os
import asyncio
import threading
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8898820544:AAGPrFuYXAut6WGenTNM42MCtVRcCrlLytY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
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
                        tr2 = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                        if rq and nm and any(c.isdigit() for c in rq):
                            data.append({"raqam": rq, "nom": nm, "tur": tr2})
            _cache["data"] = data
        except Exception as e:
            logger.error(f"Fetch: {e}")
            _cache["data"] = []
        _cache["loaded"] = True
    return _cache["data"]

def reload_cache():
    _cache["loaded"] = False
    return get_schyotlar()

def ai_request(prompt, system="", max_tokens=2000):
    if not ANTHROPIC_API_KEY:
        return ""
    body = {
        "model": "claude-opus-4-5",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }
    if system:
        body["system"] = system
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json=body,
                timeout=120
            )
            data = resp.json()
            if "content" in data:
                return data["content"][0]["text"]
            else:
                logger.error(f"AI javob xato: {data}")
                return ""
        except Exception as e:
            logger.error(f"AI urinish {attempt+1}: {e}")
            import time
            time.sleep(5)
    return ""

def ask_ai(question, lang, ctx=""):
    if not ANTHROPIC_API_KEY:
        return "AI yoq - ANTHROPIC_API_KEY sozlanmagan" if lang == "uz" else "AI nedostupen"
    if lang == "uz":
        sys = (
            "Siz Ozbekiston buxgalteriyasi va moliya sohasi boyicha yuqori malakali mutaxassississiz. "
            "Savolga juda aniq, tushunarli va professional tarzda javob bering. "
            "Har doim emoji ishlating. Misollar keltiring. Ozbek tilida yozing."
        )
    else:
        sys = (
            "Vy vysokokvalificirovannyy spetsialist po bukhgalterskomu uchyotu Uzbekistana. "
            "Otvechay chetko, ponyatno i professionalno. "
            "Vsegda ispolzuy emoji. Privodi primery. Pishi na russkom."
        )
    if ctx:
        sys += f" Tegishli schyotlar: {ctx}"
    ans = ai_request(question, system=sys, max_tokens=1500)
    return ans if ans else ("Xato yuz berdi, qayta urining." if lang == "uz" else "Oshibka, poprobuy snova.")

TOPICS_UZ = [
    "Buxgalteriya hisobining asosiy tamoyillari",
    "Aktivlar va ularning tasnifi",
    "Passivlar va kapital",
    "Daromadlar va xarajatlar hisobi",
    "Kassa va bank operatsiyalari",
    "Asosiy vositalar va amortizatsiya",
    "Nomoddiy aktivlar hisobi",
    "Tovar-moddiy boyliklar",
    "Debitorlik va kreditorlik qarzdorligi",
    "Mehnat haqi va ijtimoiy sugurta",
    "QQS va soliq hisoboti",
    "Moliyaviy hisobot tuzish",
    "Balans va uning tuzilishi",
    "Foyda va zarar hisobi",
    "Moliyaviy tahlil asoslari",
    "Ichki nazorat va audit",
    "Budjet buxgalteriyasi",
    "IFRS xalqaro standartlari",
    "Sugurta kompaniyalari buxgalteriyasi",
    "Elektron buxgalteriya va 1C dasturi",
]
TOPICS_RU = [
    "Osnovnye principy bukhgalterskogo uchyota",
    "Klassifikaciya aktivov",
    "Passivy i kapital",
    "Uchet dokhodov i raskhodov",
    "Kassovye i bankovskie operacii",
    "Osnovnye sredstva i amortizaciya",
    "Nematerialnye aktivy",
    "Tovarno-materialnye cennosti",
    "Debitorskaya zadolzhennost",
    "Uchet zarplaty i socstrakhovanie",
    "NDS i nalogovaya otchetnost",
    "Sostavlenie finansovoy otchetnosti",
    "Balans i ego struktura",
    "Uchet pribyley i ubytkov",
    "Finansovyy analiz",
    "Vnutrenniy kontrol i audit",
    "Byudzhetnyy uchet",
    "MSFO standarty",
    "Bukhgalteriya strakhovykh kompaniy",
    "Elektronnaya bukhgalteriya 1S",
]

state = {
    "lesson_n": 1,
    "last_topic_uz": "",
    "last_topic_ru": "",
}

def gen_lesson(lang, n):
    topics = TOPICS_UZ if lang == "uz" else TOPICS_RU
    topic = topics[(n - 1) % len(topics)]
    if lang == "uz":
        p = (
            f"'{topic}' mavzusida {n}-dars yoz.\n"
            "Tuzilma:\n"
            "1) Mavzu va maqsad (2-3 jumla)\n"
            "2) Asosiy nazariya (3-5 band, har biri tushuntirilgan)\n"
            "3) Amaliy misol (Ozbekiston amaliyotidan, raqamlar bilan)\n"
            "4) Asosiy xulosalar (3 band)\n"
            "5) Eslab qolish uchun kalit sozlar\n"
            "Ko'p emoji ishlat. Professional va qiziqarli yoz. Ozbek tilida."
        )
    else:
        p = (
            f"Napishi urok {n} na temu '{topic}'.\n"
            "Struktura:\n"
            "1) Tema i cel (2-3 predlozheniya)\n"
            "2) Osnovnaya teoriya (3-5 punktov s poyasneniyami)\n"
            "3) Prakticheskiy primer (iz praktiki Uzbekistana, s ciframi)\n"
            "4) Klyuchevye vyvody (3 punkta)\n"
            "5) Klyuchevye slova dlya zapominaniya\n"
            "Ispolzuy mnogo emoji. Pishi professionalno i interesno. Na russkom."
        )
    txt = ai_request(p, max_tokens=2000)
    return txt, topic

def gen_test(lang, topic):
    if not topic:
        topic = TOPICS_UZ[0] if lang == "uz" else TOPICS_RU[0]
    if lang == "uz":
        p = (
            f"'{topic}' mavzusida 5 ta test savoli tuz.\n"
            "Har bir savolda A, B, C, D variantlari bolsin.\n"
            "Oxirida togri javoblarni ko'rsat.\n"
            "Format:\n"
            "1. Savol\n"
            "A) ...\nB) ...\nC) ...\nD) ...\n\n"
            "Ko'p emoji ishlat. Ozbek tilida yoz."
        )
    else:
        p = (
            f"Sostavь 5 testovykh voprosov po teme '{topic}'.\n"
            "U kazhdogo 4 varianta A B C D.\n"
            "V konce ukazi pravilnye otvety.\n"
            "Format:\n"
            "1. Vopros\n"
            "A) ...\nB) ...\nC) ...\nD) ...\n\n"
            "Ispolzuy emoji. Na russkom."
        )
    return ai_request(p, max_tokens=1500)

def gen_review(lang, topic):
    if not topic:
        topic = TOPICS_UZ[0] if lang == "uz" else TOPICS_RU[0]
    if lang == "uz":
        p = (
            f"'{topic}' mavzusini qisqacha takrorla.\n"
            "Tuzilma:\n"
            "1) Asosiy tushunchalar (qisqa)\n"
            "2) Muhim formulalar yoki jadvallar\n"
            "3) Tez-tez uchraydigan xatolar\n"
            "4) Amaliy maslahatlar\n"
            "Ko'p emoji ishlat. Qisqa va aniq. Ozbek tilida."
        )
    else:
        p = (
            f"Kratko povtori temu '{topic}'.\n"
            "Struktura:\n"
            "1) Osnovnye ponyatiya (kratko)\n"
            "2) Vazhnye formuly ili tablicy\n"
            "3) Chastye oshibki\n"
            "4) Prakticheskie sovety\n"
            "Ispolzuy emoji. Kratko i chetko. Na russkom."
        )
    return ai_request(p, max_tokens=1200)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[
        InlineKeyboardButton("O'zbekcha", callback_data="lang_uz"),
        InlineKeyboardButton("Ruscha", callback_data="lang_ru")
    ]]
    await update.message.reply_text(
        "Assalomu alaykum! Xush kelibsiz!\n\n"
        "Salom! Dobro pozhalovat!\n\n"
        "Tilni tanlang / Vyberi yazyk:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def show_menu(msg, lang, uid, edit=False):
    sub = uid in subscribers
    n = state["lesson_n"]
    if lang == "uz":
        txt = (
            "Bosh menyu\n\n"
            "Kunlik jadval:\n"
            "04:00 - Yangi dars\n"
            "12:30 - Test\n"
            "18:30 - Takrorlash\n\n"
            f"Joriy dars: #{n}-mavzu\n"
            f"Obuna holati: {'Faol' if sub else 'Yoq'}\n\n"
            "Nima qilmoqchisiz?"
        )
        kb = [
            [InlineKeyboardButton("AI Buxgalterga savol", callback_data="ai_hint")],
            [InlineKeyboardButton("Schyotlar rejasi (lex.uz)", callback_data="sch_menu")],
            [InlineKeyboardButton("Obunadan chiqish" if sub else "Darslarga obuna bolish", callback_data="unsub" if sub else "sub")],
            [InlineKeyboardButton("Tilni ozgartirish", callback_data="chg_lang")],
        ]
    else:
        txt = (
            "Glavnoe menyu\n\n"
            "Raspisanie:\n"
            "04:00 - Urok\n"
            "12:30 - Test\n"
            "18:30 - Povtorenie\n\n"
            f"Tekushchiy urok: #{n}\n"
            f"Podpiska: {'Aktivna' if sub else 'Net'}\n\n"
            "Chto khotite sdelat?"
        )
        kb = [
            [InlineKeyboardButton("Vopros AI bukhgalteru", callback_data="ai_hint")],
            [InlineKeyboardButton("Plan schetov (lex.uz)", callback_data="sch_menu")],
            [InlineKeyboardButton("Otpisatsya" if sub else "Podpisatsya na uroki", callback_data="unsub" if sub else "sub")],
            [InlineKeyboardButton("Smenit yazyk", callback_data="chg_lang")],
        ]
    rm = InlineKeyboardMarkup(kb)
    try:
        if edit: await msg.edit_text(txt, reply_markup=rm)
        else: await msg.reply_text(txt, reply_markup=rm)
    except Exception:
        await msg.reply_text(txt, reply_markup=rm)

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await show_menu(update.message, get_lang(uid), uid)

async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_lang(uid)
    m = await update.message.reply_text("Yangilanmoqda..." if lang == "uz" else "Obnovleniye...")
    s = reload_cache()
    await m.edit_text(
        f"Yangilandi! {len(s)} ta schyot yuklandi." if lang == "uz"
        else f"Obnovleno! Zagruzheno {len(s)} schetov."
    )

async def ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = get_lang(uid)
    q = update.message.text.strip()
    sch = get_schyotlar()
    ctx = "; ".join([
        f"{s['raqam']}: {s['nom']}" for s in sch
        if any(w.lower() in q.lower() for w in s['nom'].split())
    ][:5])
    wm = await update.message.reply_text(
        "Tahlil qilinmoqda, biroz kuting..." if lang == "uz"
        else "Analiziruyetsya, podozhdite..."
    )
    ans = ask_ai(q, lang, ctx)
    await wm.delete()
    await update.message.reply_text("AI Buxgalter:\n\n" + ans)

async def btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    uid = q.from_user.id
    lang = get_lang(uid)

    if d in ("lang_uz", "lang_ru"):
        nl = "uz" if d == "lang_uz" else "ru"
        set_lang(uid, nl)
        subscribers.add(uid)
        if nl == "uz":
            await q.message.reply_text(
                "Til tanlandi!\n\n"
                "Siz avtomatik ravishda darslarga obuna boldingiz!\n\n"
                "Jadval:\n"
                "04:00 - Yangi dars\n"
                "12:30 - Test\n"
                "18:30 - Takrorlash\n\n"
                "Istalgan buxgalteriya savolini yozing!"
            )
        else:
            await q.message.reply_text(
                "Yazyk vybran!\n\n"
                "Vy avtomaticheski podpisany na uroki!\n\n"
                "Raspisanie:\n"
                "04:00 - Urok\n"
                "12:30 - Test\n"
                "18:30 - Povtorenie\n\n"
                "Pishite lyuboy bukhgaltersky vopros!"
            )
        await show_menu(q.message, nl, uid)

    elif d == "chg_lang":
        kb = [[
            InlineKeyboardButton("O'zbekcha", callback_data="lang_uz"),
            InlineKeyboardButton("Ruscha", callback_data="lang_ru")
        ]]
        await q.edit_message_text("Tilni tanlang / Vyberi yazyk:", reply_markup=InlineKeyboardMarkup(kb))

    elif d == "sub":
        subscribers.add(uid)
        if lang == "uz":
            await q.message.reply_text(
                "Muvaffaqiyatli obuna boldingiz!\n\n"
                "Jadval:\n"
                "Ertalab 04:00 - Yangi dars\n"
                "Tushlik 12:30 - Test\n"
                "Kechqurun 18:30 - Takrorlash\n\n"
                "Har kuni buxgalteriya bilimlaringiz oshib boradi!"
            )
        else:
            await q.message.reply_text(
                "Vy uspeshno podpisalis!\n\n"
                "Raspisanie:\n"
                "Utro 04:00 - Urok\n"
                "Obed 12:30 - Test\n"
                "Vecher 18:30 - Povtorenie\n\n"
                "Kazhdyy den vashi znaniyu budu rasti!"
            )
        await show_menu(q.message, lang, uid)

    elif d == "unsub":
        subscribers.discard(uid)
        await q.message.reply_text(
            "Obuna bekor qilindi. Qaytib kelishingizni kutamiz!" if lang == "uz"
            else "Podpiska otmenena. Zhdem vas obratno!"
        )
        await show_menu(q.message, lang, uid)

    elif d == "ai_hint":
        if lang == "uz":
            txt = (
                "AI Buxgalterga savol bering!\n\n"
                "Misol savollar:\n"
                "• QQS qanday hisoblanadi?\n"
                "• Asosiy vosita qanday hisobga olinadi?\n"
                "• 0110 schyot nima uchun?\n"
                "• Amortizatsiya qanday hisoblash kerak?\n"
                "• Balans tuzish tartibi qanday?\n\n"
                "Savolingizni yozing, javob olasiz!"
            )
        else:
            txt = (
                "Zadayte vopros AI bukhgalteru!\n\n"
                "Primery voprosov:\n"
                "• Kak schitat NDS?\n"
                "• Kak uchityvayetsya osnov. sredstvo?\n"
                "• Dlya chego schet 0110?\n"
                "• Kak rasschitat amortizaciyu?\n"
                "• Kak sostavit balans?\n\n"
                "Napishite vopros i poluchite otvet!"
            )
        await q.message.reply_text(txt)

    elif d == "sch_menu":
        sch = get_schyotlar()
        if not sch:
            await q.message.reply_text(
                "Ma'lumot yuklanmadi. /reload buyrug'ini sinab koring." if lang == "uz"
                else "Dannye ne zagruzilis. Poprobuy /reload."
            )
            return
        guruhlar = {}
        for s in sch:
            r = s["raqam"]
            k = (r[0] + "000") if r and r[0].isdigit() else "X"
            guruhlar.setdefault(k, []).append(s)
        kb = [
            [InlineKeyboardButton(f"Seriya {g} ({len(v)} ta schyot)", callback_data=f"g_{g}")]
            for g, v in sorted(guruhlar.items())
        ]
        kb.append([InlineKeyboardButton("Orqaga" if lang == "uz" else "Nazad", callback_data="back")])
        title = (
            f"Schyotlar rejasi (lex.uz)\nJami: {len(sch)} ta schyot\n\nSerirani tanlang:" if lang == "uz"
            else f"Plan schetov (lex.uz)\nVsego: {len(sch)} schetov\n\nVyberi seriyu:"
        )
        await q.edit_message_text(title, reply_markup=InlineKeyboardMarkup(kb))

    elif d.startswith("g_"):
        g = d[2:]
        sch = get_schyotlar()
        res = [s for s in sch if s["raqam"] and s["raqam"][0].isdigit() and (s["raqam"][0] + "000") == g]
        if not res:
            await q.message.reply_text("Bu seriyada schyot topilmadi." if lang == "uz" else "Schetov ne naydeno.")
            return
        hdr = f"Seriya {g} — {len(res)} ta schyot:\n\n" if lang == "uz" else f"Seriya {g} — {len(res)} schetov:\n\n"
        body = "\n".join([
            f"{s['raqam']} — {s['nom']}" + (f" [{s['tur']}]" if s["tur"] else "")
            for s in res
        ])
        txt = hdr + body
        for ch in [txt[i:i+4000] for i in range(0, len(txt), 4000)]:
            await q.message.reply_text(ch)

    elif d == "back":
        await show_menu(q.message, lang, uid, edit=True)

# === KUNLIK DARS 04:00 ===
def send_lesson_sync(app):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(_send_lesson(app))
    finally: loop.close()

async def _send_lesson(app):
    if not subscribers: return
    n = state["lesson_n"]
    lu, tu = gen_lesson("uz", n)
    lr, tr = gen_lesson("ru", n)
    state["lesson_n"] += 1
    state["last_topic_uz"] = tu
    state["last_topic_ru"] = tr
    for uid in list(subscribers):
        try:
            lang = get_lang(uid)
            lesson = lu if lang == "uz" else lr
            topic = tu if lang == "uz" else tr
            if not lesson: continue
            hdr = (
                f"Ertalabki Dars #{n}\nMavzu: {topic}\n\n" if lang == "uz"
                else f"Utrennyy Urok #{n}\nTema: {topic}\n\n"
            )
            txt = hdr + lesson
            for ch in [txt[i:i+4000] for i in range(0, len(txt), 4000)]:
                await app.bot.send_message(chat_id=uid, text=ch)
        except Exception as e:
            logger.error(f"Lesson {uid}: {e}")
            subscribers.discard(uid)

# === TEST 12:30 ===
def send_test_sync(app):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(_send_test(app))
    finally: loop.close()

async def _send_test(app):
    if not subscribers: return
    for uid in list(subscribers):
        try:
            lang = get_lang(uid)
            topic = state["last_topic_uz"] if lang == "uz" else state["last_topic_ru"]
            test = gen_test(lang, topic)
            if not test: continue
            hdr = (
                f"Tushlik Testi\nMavzu: {topic}\n\n" if lang == "uz"
                else f"Obedennoe Testirovanie\nTema: {topic}\n\n"
            )
            txt = hdr + test
            for ch in [txt[i:i+4000] for i in range(0, len(txt), 4000)]:
                await app.bot.send_message(chat_id=uid, text=ch)
        except Exception as e:
            logger.error(f"Test {uid}: {e}")
            subscribers.discard(uid)

# === TAKRORLASH 18:30 ===
def send_review_sync(app):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(_send_review(app))
    finally: loop.close()

async def _send_review(app):
    if not subscribers: return
    for uid in list(subscribers):
        try:
            lang = get_lang(uid)
            topic = state["last_topic_uz"] if lang == "uz" else state["last_topic_ru"]
            review = gen_review(lang, topic)
            if not review: continue
            hdr = (
                f"Kechki Takrorlash\nMavzu: {topic}\n\n" if lang == "uz"
                else f"Vechernee Povtorenie\nTema: {topic}\n\n"
            )
            txt = hdr + review
            for ch in [txt[i:i+4000] for i in range(0, len(txt), 4000)]:
                await app.bot.send_message(chat_id=uid, text=ch)
        except Exception as e:
            logger.error(f"Review {uid}: {e}")
            subscribers.discard(uid)

# === WEB SERVER ===
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running OK")
    def log_message(self, *a): pass

def web():
    HTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8080))), H).serve_forever()

# === MAIN ===
def main():
    threading.Thread(target=web, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))

    sc = BackgroundScheduler()
    # Toshkent UTC+5: 04:00=23:00UTC, 12:30=07:30UTC, 18:30=13:30UTC
    sc.add_job(send_lesson_sync, "cron", hour=23, minute=0,  args=[app])
    sc.add_job(send_test_sync,   "cron", hour=7,  minute=30, args=[app])
    sc.add_job(send_review_sync, "cron", hour=13, minute=30, args=[app])
    sc.start()

    logger.info("Jadval: 04:00 dars | 12:30 test | 18:30 takrorlash (Toshkent)")
    logger.info("Schyotlar yuklanmoqda...")
    get_schyotlar()
    logger.info("Bot ishga tushdi!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
