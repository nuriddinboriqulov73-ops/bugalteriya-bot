import logging
import os
import asyncio
import threading
import requests
from datetime import time
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import anthropic

# ===================== SOZLAMALAR =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8850667627:AAEYJOyVyJzGGKuYbQNlpYnHLBK9GdtPh_U")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "AIzaSyBUlHIHlTGJDcHCwLlXIEvOy3pOcdyP3Os")
LEX_URL = "https://lex.uz/acts/-1357627"
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "6911800755")  # Optional: admin chat ID

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== FOYDALANUVCHI SOZLAMALARI =====================
# user_id -> {"lang": "uz" | "ru", "subscribed": True/False}
user_settings = {}
# Barcha subscribe bo'lgan foydalanuvchilar
subscribers = set()

def get_lang(user_id):
    return user_settings.get(user_id, {}).get("lang", "uz")

def set_lang(user_id, lang):
    if user_id not in user_settings:
        user_settings[user_id] = {}
    user_settings[user_id]["lang"] = lang

# ===================== SCHYOTLAR CACHE =====================
_cache = {"data": None, "loaded": False}

def fetch_schyotlar():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(LEX_URL, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        schyotlar = []
        table = soup.find("table")
        if not table:
            return []
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 2:
                raqam = cols[0].get_text(strip=True)
                nom = cols[1].get_text(strip=True)
                tur = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                if raqam and nom and any(c.isdigit() for c in raqam):
                    schyotlar.append({"raqam": raqam, "nom": nom, "tur": tur})
        return schyotlar
    except Exception as e:
        logger.error(f"Fetch xatosi: {e}")
        return []

def get_schyotlar():
    if not _cache["loaded"]:
        _cache["data"] = fetch_schyotlar()
        _cache["loaded"] = True
    return _cache["data"]

def reload_cache():
    _cache["loaded"] = False
    _cache["data"] = None
    return get_schyotlar()

# ===================== AI FUNKSIYALARI =====================
def ask_claude(question: str, lang: str, schyotlar_context: str = "") -> str:
    """Claude AI ga savol yuboradi"""
    if not ANTHROPIC_API_KEY:
        if lang == "ru":
            return "⚠️ AI функция временно недоступна. Пожалуйста, обратитесь к администратору."
        return "⚠️ AI funksiyasi hozircha mavjud emas. Iltimos, administratorga murojaat qiling."

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        if lang == "ru":
            system = (
                "Ты — профессиональный бухгалтер и финансовый консультант, специализирующийся "
                "на бухгалтерском учёте Узбекистана. Отвечай чётко, профессионально и понятно. "
                "Используй примеры из узбекского законодательства. "
                f"{('Контекст — план счетов: ' + schyotlar_context) if schyotlar_context else ''}"
            )
        else:
            system = (
                "Siz O'zbekiston buxgalteriya hisobi bo'yicha mutaxassis va moliyaviy maslahatchi siz. "
                "Savollarga aniq, professional va tushunarli javob bering. "
                "O'zbek qonunchiligi va me'yorlari asosida misollar keltiring. "
                f"{('Schyotlar rejasi konteksti: ' + schyotlar_context) if schyotlar_context else ''}"
            )

        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"Claude API xatosi: {e}")
        if lang == "ru":
            return f"❌ Ошибка AI: {str(e)}"
        return f"❌ AI xatosi: {str(e)}"

def generate_daily_lesson(lang: str, lesson_number: int) -> str:
    """Har kuni yangi dars mavzusi va tarkibini AI yordamida yaratadi"""
    if not ANTHROPIC_API_KEY:
        return ""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Mavzular ro'yxati - AI o'zi ketma-ketlikda tanlaydi
        topics_uz = [
            "Buxgalteriya hisobining asosiy tamoyillari",
            "Aktivlar va ularning tasnifi",
            "Passivlar va kapital",
            "Daromadlar va xarajatlar hisobi",
            "Naqd pul va bank operatsiyalari",
            "Asosiy vositalar hisobi va amortizatsiya",
            "Nomoddiy aktivlar",
            "Tovar-moddiy boyliklar hisobi",
            "Debitorlik va kreditorlik qarzdorligi",
            "Mehnat haqi va ijtimoiy sug'urta hisobi",
            "QQS hisobi va soliq hisoboti",
            "Moliyaviy hisobot tuzish",
            "Balans va uning tuzilishi",
            "Foyda va zarar hisobi",
            "Moliyaviy tahlil asoslari",
            "Ichki nazorat va audit",
            "Budjet buxgalteriyasi",
            "Xalqaro moliyaviy hisobot standartlari (IFRS)",
            "Sug'urta kompaniyalari buxgalteriyasi",
            "Elektron buxgalteriya va 1C dasturi",
        ]

        topics_ru = [
            "Основные принципы бухгалтерского учёта",
            "Активы и их классификация",
            "Пассивы и капитал",
            "Учёт доходов и расходов",
            "Кассовые и банковские операции",
            "Учёт основных средств и амортизация",
            "Нематериальные активы",
            "Учёт товарно-материальных ценностей",
            "Дебиторская и кредиторская задолженность",
            "Учёт заработной платы и соцстрахования",
            "Учёт НДС и налоговая отчётность",
            "Составление финансовой отчётности",
            "Баланс и его структура",
            "Учёт прибылей и убытков",
            "Основы финансового анализа",
            "Внутренний контроль и аудит",
            "Бюджетный учёт",
            "МСФО (Международные стандарты)",
            "Бухгалтерия страховых компаний",
            "Электронная бухгалтерия и 1С",
        ]

        topics = topics_uz if lang == "uz" else topics_ru
        topic = topics[(lesson_number - 1) % len(topics)]

        if lang == "ru":
            prompt = (
                f"Напиши обучающий урок №{lesson_number} по теме: '{topic}'.\n\n"
                "Структура урока:\n"
                "1. 📌 Тема и цель урока (2-3 предложения)\n"
                "2. 📚 Основная теория (чётко и понятно, 3-5 пунктов)\n"
                "3. 💡 Практический пример из узбекской практики (с проводками если нужно)\n"
                "4. ✅ Ключевые выводы (3 пункта)\n"
                "5. 📝 Вопрос для самопроверки\n\n"
                "Пиши на русском языке, профессионально но доступно. Используй эмодзи."
            )
        else:
            prompt = (
                f"'{topic}' mavzusida №{lesson_number} o'quv darsi yoz.\n\n"
                "Dars tuzilmasi:\n"
                "1. 📌 Mavzu va dars maqsadi (2-3 jumla)\n"
                "2. 📚 Asosiy nazariya (aniq va tushunarli, 3-5 nuqta)\n"
                "3. 💡 O'zbek amaliyotidan amaliy misol (agar kerak bo'lsa buxgalteriya o'tkazmalari bilan)\n"
                "4. ✅ Asosiy xulosalar (3 ta nuqta)\n"
                "5. 📝 O'z-o'zini tekshirish uchun savol\n\n"
                "O'zbek tilida, professional lekin tushunarli yoz. Emoji ishlat."
            )

        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text, topic
    except Exception as e:
        logger.error(f"Dars yaratish xatosi: {e}")
        return "", ""

# ===================== DARS RAQAMI =====================
lesson_counter = {"count": 1}

# ===================== HANDLERS =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)

    keyboard = [
        [
            InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 *Xush kelibsiz! / Добро пожаловать!*\n\n"
        "🌐 Tilni tanlang / Выберите язык:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_main_menu(update_or_message, lang: str, user_id: int, edit=False):
    subscribed = user_id in subscribers

    if lang == "uz":
        obuna_status = "✅ Obuna bor" if subscribed else "❌ Obuna yoq"
        text = (
            "🏠 *Bosh menyu*\n\n"
            "📚 *Imkoniyatlar:*\n"
            "• 🤖 AI buxgalter — har qanday savol bering\n"
            "• 📋 Schyotlar rejasi — lex.uz dan malumot\n"
            f"• 📅 Kunlik darslar — {obuna_status}\n\n"
            "Pastdagi tugmani bosing yoki savol yozing:"
        )
        keyboard = [
            [InlineKeyboardButton("🤖 AI Buxgalterga savol", callback_data="ai_hint")],
            [InlineKeyboardButton("📋 Schyotlar rejasi", callback_data="schyotlar_menu")],
            [
                InlineKeyboardButton(
                    "🔔 Darsdan chiqish" if subscribed else "🔔 Kunlik darslarga obuna",
                    callback_data="unsub" if subscribed else "sub"
                )
            ],
            [InlineKeyboardButton("🌐 Tilni o'zgartirish", callback_data="change_lang")],
        ]
    else:
        text = (
            "🏠 *Главное меню*\n\n"
            "📚 *Возможности:*\n"
            "• 🤖 AI бухгалтер — задайте любой вопрос\n"
            "• 📋 План счетов — данные с lex.uz\n"
            f"• 📅 Ежедневные уроки — {'✅ Подписан' if subscribed else '❌ Не подписан'}\n\n"
            "Нажмите кнопку или напишите вопрос:"
        )
        keyboard = [
            [InlineKeyboardButton("🤖 Вопрос AI бухгалтеру", callback_data="ai_hint")],
            [InlineKeyboardButton("📋 План счетов", callback_data="schyotlar_menu")],
            [
                InlineKeyboardButton(
                    "🔕 Отписаться от уроков" if subscribed else "🔔 Подписаться на уроки",
                    callback_data="unsub" if subscribed else "sub"
                )
            ],
            [InlineKeyboardButton("🌐 Сменить язык", callback_data="change_lang")],
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if edit and hasattr(update_or_message, 'edit_text'):
        await update_or_message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif hasattr(update_or_message, 'reply_text'):
        await update_or_message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update_or_message.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_ai_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi matn yozganda AI ga savol sifatida yuboradi"""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    question = update.message.text.strip()

    # Schyotlardan kontekst olish
    schyotlar = get_schyotlar()
    relevant = [s for s in schyotlar if any(w.lower() in question.lower() for w in s['nom'].split())]
    context_str = ""
    if relevant[:5]:
        context_str = "; ".join([f"{s['raqam']}: {s['nom']}" for s in relevant[:5]])

    if lang == "ru":
        wait_msg = await update.message.reply_text("🤔 AI анализирует ваш вопрос...")
    else:
        wait_msg = await update.message.reply_text("🤔 AI savolingizni tahlil qilmoqda...")

    answer = ask_claude(question, lang, context_str)

    await wait_msg.delete()
    await update.message.reply_text(
        f"🤖 *AI Buxgalter / AI Бухгалтер:*\n\n{answer}",
        parse_mode="Markdown"
    )

async def send_daily_lesson_to_all(app):
    """Barcha obunachilarga kunlik dars yuboradi"""
    if not subscribers:
        logger.info("Obunachi yo'q, dars yuborilmadi")
        return

    lesson_num = lesson_counter["count"]

    # Ikki tilda dars tayyorla
    lesson_uz, topic_uz = generate_daily_lesson("uz", lesson_num)
    lesson_ru, topic_ru = generate_daily_lesson("ru", lesson_num)

    lesson_counter["count"] += 1

    for user_id in list(subscribers):
        try:
            lang = get_lang(user_id)
            lesson = lesson_uz if lang == "uz" else lesson_ru
            topic = topic_uz if lang == "uz" else topic_ru

            if not lesson:
                continue

            if lang == "uz":
                header = f"📅 *Kunlik Dars #{lesson_num}*\n📖 *Mavzu: {topic}*\n\n"
            else:
                header = f"📅 *Ежедневный Урок #{lesson_num}*\n📖 *Тема: {topic}*\n\n"

            full_text = header + lesson

            # Telegram 4096 belgi chekovi
            chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
            for chunk in chunks:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=chunk,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"User {user_id} ga dars yuborishda xato: {e}")
            subscribers.discard(user_id)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    lang = get_lang(user_id)

    # --- Til tanlash ---
    if data in ("lang_uz", "lang_ru"):
        new_lang = "uz" if data == "lang_uz" else "ru"
        set_lang(user_id, new_lang)
        subscribers.add(user_id)  # Avtomatik obuna
        await show_main_menu(query.message, new_lang, user_id, edit=True)

    elif data == "change_lang":
        keyboard = [
            [
                InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            ]
        ]
        await query.edit_message_text(
            "🌐 Tilni tanlang / Выберите язык:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # --- Obuna ---
    elif data == "sub":
        subscribers.add(user_id)
        msg = "✅ Kunlik darslarga muvaffaqiyatli obuna bo'ldingiz!\nHar kuni soat 10:00 da dars keladi." if lang == "uz" else "✅ Вы успешно подписались на ежедневные уроки!\nУрок будет приходить каждый день в 10:00."
        await query.message.reply_text(msg)
        await show_main_menu(query.message, lang, user_id)

    elif data == "unsub":
        subscribers.discard(user_id)
        msg = "❌ Kunlik darslardan obuna bekor qilindi." if lang == "uz" else "❌ Вы отписались от ежедневных уроков."
        await query.message.reply_text(msg)
        await show_main_menu(query.message, lang, user_id)

    # --- AI ---
    elif data == "ai_hint":
        if lang == "uz":
            text = (
                "🤖 *AI Buxgalterga savol bering*\n\n"
                "Shunchaki savolingizni yozing, masalan:\n"
                "• _Asosiy vosita qanday hisobga olinadi?_\n"
                "• _QQS hisoblash tartibi_\n"
                "• _0110 schyot nima uchun ishlatiladi?_\n\n"
                "✍️ Savolingizni yozing:"
            )
        else:
            text = (
                "🤖 *Задайте вопрос AI бухгалтеру*\n\n"
                "Просто напишите вопрос, например:\n"
                "• _Как учитывается основное средство?_\n"
                "• _Порядок расчёта НДС_\n"
                "• _Для чего используется счёт 0110?_\n\n"
                "✍️ Напишите ваш вопрос:"
            )
        await query.message.reply_text(text, parse_mode="Markdown")

    # --- Schyotlar ---
    elif data == "schyotlar_menu":
        schyotlar = get_schyotlar()
        if not schyotlar:
            msg = "❌ Ma'lumot olib bo'lmadi." if lang == "uz" else "❌ Не удалось загрузить данные."
            await query.message.reply_text(msg)
            return

        # Seriyalar bo'yicha guruhlash
        guruhlar = {}
        for s in schyotlar:
            r = s["raqam"]
            if r and r[0].isdigit():
                guruh_key = r[0] + "000"
            else:
                guruh_key = "Boshqa"
            guruhlar.setdefault(guruh_key, []).append(s)

        keyboard = []
        for guruh in sorted(guruhlar.keys()):
            cnt = len(guruhlar[guruh])
            keyboard.append([InlineKeyboardButton(
                f"📁 {guruh} seriya ({cnt} ta)",
                callback_data=f"guruh_{guruh}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga" if lang == "uz" else "🔙 Назад", callback_data="back_main")])

        title = f"📋 *Schyotlar rejasi* — jami {len(schyotlar)} ta\nSerirani tanlang:" if lang == "uz" else f"📋 *План счетов* — всего {len(schyotlar)}\nВыберите серию:"
        await query.edit_message_text(title, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("guruh_"):
        guruh = data[6:]
        schyotlar = get_schyotlar()
        results = [s for s in schyotlar if s["raqam"] and s["raqam"][0].isdigit() and (s["raqam"][0] + "000") == guruh]

        if not results:
            await query.message.reply_text("❌ Bo'sh seriya." if lang == "uz" else "❌ Пустая серия.")
            return

        text = f"📁 *{guruh} seriyasi — {len(results)} ta schyot:*\n\n"
        for s in results:
            tur_str = f" `[{s['tur']}]`" if s['tur'] else ""
            text += f"• *{s['raqam']}* — {s['nom']}{tur_str}\n"

        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await query.message.reply_text(chunk, parse_mode="Markdown")

    elif data == "back_main":
        await show_main_menu(query.message, lang, user_id, edit=True)

    elif data == "reload_schyotlar":
        schyotlar = reload_cache()
        msg = f"✅ Yangilandi! Jami *{len(schyotlar)}* ta schyot yuklandi." if lang == "uz" else f"✅ Обновлено! Загружено *{len(schyotlar)}* счетов."
        await query.edit_message_text(msg, parse_mode="Markdown")

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    await show_main_menu(update.message, lang, user_id)

async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    msg = "🔄 Yangilanmoqda..." if lang == "uz" else "🔄 Обновление..."
    m = await update.message.reply_text(msg)
    schyotlar = reload_cache()
    result = f"✅ Yangilandi! Jami *{len(schyotlar)}* ta schyot." if lang == "uz" else f"✅ Обновлено! Загружено *{len(schyotlar)}* счетов."
    await m.edit_text(result, parse_mode="Markdown")

# ===================== WEB SERVER (Render uchun) =====================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running OK")
    def log_message(self, format, *args):
        pass  # Logni o'chirish

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Web server port {port} da ishlamoqda")
    server.serve_forever()

# ===================== MAIN =====================
async def main():
    # Web server ni alohida threadda ishga tushirish (Render uchun)
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

    # Bot application
    app = Application.builder().token(BOT_TOKEN).build()

    # Handlerlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("reload", reload_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_question))

    # Scheduler — har kuni soat 10:00 (UTC+5 = 05:00 UTC)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_lesson_to_all,
        trigger="cron",
        hour=5,      # UTC 05:00 = Toshkent 10:00
        minute=0,
        args=[app]
    )
    scheduler.start()
    logger.info("Scheduler ishga tushdi — har kuni 10:00 (Toshkent) da dars yuboriladi")

    # Schyotlarni oldindan yuklash
    logger.info("Schyotlar yuklanmoqda...")
    get_schyotlar()
    logger.info("Bot ishga tushdi!")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # Davom etish
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
