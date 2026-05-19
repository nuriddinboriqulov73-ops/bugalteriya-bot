import logging
import os
import asyncio
import threading
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
# Sug'urtalovchilar uchun schyotlar rejasi (lex.uz dan olindi)
SCHYOTLAR_DATA = [
    {"raqam":"0110","nom":"Nomoddiy aktivlar","tur":"A"},
    {"raqam":"0111","nom":"Dasturiy ta'minot","tur":"A"},
    {"raqam":"0112","nom":"Patentlar va litsenziyalar","tur":"A"},
    {"raqam":"0113","nom":"Tovar belgilari","tur":"A"},
    {"raqam":"0120","nom":"Nomoddiy aktivlarning amortizatsiyasi","tur":"P"},
    {"raqam":"0130","nom":"Nomoddiy aktivlarning qadrsizlanishi","tur":"P"},
    {"raqam":"0160","nom":"Tugallanmagan nomoddiy aktivlar","tur":"A"},
    {"raqam":"0170","nom":"Goodvill","tur":"A"},
    {"raqam":"0180","nom":"Goodvilning qadrsizlanishi","tur":"P"},
    {"raqam":"0200","nom":"Asosiy vositalar","tur":"A"},
    {"raqam":"0210","nom":"Yer uchastkasi","tur":"A"},
    {"raqam":"0211","nom":"Binolar va inshootlar","tur":"A"},
    {"raqam":"0212","nom":"Mashina va uskunalar","tur":"A"},
    {"raqam":"0213","nom":"Kompyuter texnikasi","tur":"A"},
    {"raqam":"0214","nom":"Transport vositalari","tur":"A"},
    {"raqam":"0215","nom":"Mebel va inventar","tur":"A"},
    {"raqam":"0220","nom":"Asosiy vositalar amortizatsiyasi","tur":"P"},
    {"raqam":"0230","nom":"Asosiy vositalar qadrsizlanishi","tur":"P"},
    {"raqam":"0240","nom":"Ijaraga olingan asosiy vositalar","tur":"A"},
    {"raqam":"0260","nom":"Tugallanmagan kapital qurilish","tur":"A"},
    {"raqam":"0270","nom":"Kapital qo'yilmalar","tur":"A"},
    {"raqam":"0400","nom":"Uzoq muddatli investitsiyalar","tur":"A"},
    {"raqam":"0410","nom":"Qimmatli qog'ozlar","tur":"A"},
    {"raqam":"0420","nom":"Sho''ba korxonalardagi investitsiyalar","tur":"A"},
    {"raqam":"0430","nom":"Assotsirlangan korxonalardagi investitsiyalar","tur":"A"},
    {"raqam":"0440","nom":"Uzoq muddatli qarzlar","tur":"A"},
    {"raqam":"0500","nom":"Uzoq muddatli debitorlik qarzlari","tur":"A"},
    {"raqam":"0510","nom":"Xaridorlar va buyurtmachilardan","tur":"A"},
    {"raqam":"0520","nom":"Sug'urta bo'yicha uzoq muddatli debitorlik","tur":"A"},
    {"raqam":"0600","nom":"Kechiktirilgan xarajatlar","tur":"A"},
    {"raqam":"0610","nom":"Kechiktirilgan sug'urta xarajatlari","tur":"A"},
    {"raqam":"1000","nom":"Tovar-moddiy boyliklar","tur":"A"},
    {"raqam":"1010","nom":"Xom ashyo va materiallar","tur":"A"},
    {"raqam":"1020","nom":"Yarim tayyor mahsulotlar","tur":"A"},
    {"raqam":"1030","nom":"Tayyor mahsulotlar","tur":"A"},
    {"raqam":"1040","nom":"Tovarlar","tur":"A"},
    {"raqam":"1050","nom":"Boshqa moddiy aktivlar","tur":"A"},
    {"raqam":"1060","nom":"Tugallanmagan ishlab chiqarish","tur":"A"},
    {"raqam":"1100","nom":"Qisqa muddatli investitsiyalar","tur":"A"},
    {"raqam":"1110","nom":"Aksiyalar","tur":"A"},
    {"raqam":"1120","nom":"Obligatsiyalar","tur":"A"},
    {"raqam":"1130","nom":"Depozitlar","tur":"A"},
    {"raqam":"1200","nom":"Debitorlik qarzlari","tur":"A"},
    {"raqam":"1210","nom":"Xaridorlar va buyurtmachilardan debitorlik","tur":"A"},
    {"raqam":"1220","nom":"Sug'urta mukofotlari bo'yicha debitorlik","tur":"A"},
    {"raqam":"1230","nom":"Sug'urta shartnomalari bo'yicha debitorlik","tur":"A"},
    {"raqam":"1240","nom":"Qayta sug'urtalash bo'yicha debitorlik","tur":"A"},
    {"raqam":"1250","nom":"Boshqa debitorlik qarzlari","tur":"A"},
    {"raqam":"1260","nom":"Ta'sis hissasiga debitorlik","tur":"A"},
    {"raqam":"1270","nom":"Xodimlardan debitorlik","tur":"A"},
    {"raqam":"1280","nom":"Byudjetdan debitorlik","tur":"A"},
    {"raqam":"1290","nom":"Boshqa joriy aktivlar","tur":"A"},
    {"raqam":"1300","nom":"Bo'naklardan debitorlik","tur":"A"},
    {"raqam":"1310","nom":"Yetkazib beruvchilarga berilgan bo'naklar","tur":"A"},
    {"raqam":"1400","nom":"Pul mablag'lari","tur":"A"},
    {"raqam":"1410","nom":"Kassa","tur":"A"},
    {"raqam":"1420","nom":"Hisob-kitob schyoti","tur":"A"},
    {"raqam":"1430","nom":"Valyuta schyoti","tur":"A"},
    {"raqam":"1440","nom":"Maxsus schyotlar","tur":"A"},
    {"raqam":"1450","nom":"Akkreditivlar","tur":"A"},
    {"raqam":"1460","nom":"Chek daftarchalari","tur":"A"},
    {"raqam":"1470","nom":"Boshqa pul mablag'lari","tur":"A"},
    {"raqam":"1500","nom":"Kechiktirilgan xarajatlar (joriy)","tur":"A"},
    {"raqam":"1510","nom":"Keyingi davrlarga tegishli xarajatlar","tur":"A"},
    {"raqam":"2000","nom":"Ustav kapital","tur":"P"},
    {"raqam":"2010","nom":"Oddiy aksiyalar","tur":"P"},
    {"raqam":"2020","nom":"Imtiyozli aksiyalar","tur":"P"},
    {"raqam":"2030","nom":"Pay va hissalar","tur":"P"},
    {"raqam":"2100","nom":"Qo'shimcha kapital","tur":"P"},
    {"raqam":"2110","nom":"Emissiya daromadi","tur":"P"},
    {"raqam":"2120","nom":"Mol-mulkni qayta baholash","tur":"P"},
    {"raqam":"2200","nom":"Zaxira kapital","tur":"P"},
    {"raqam":"2210","nom":"Qonuniy zaxiralar","tur":"P"},
    {"raqam":"2220","nom":"Ustav bo'yicha zaxiralar","tur":"P"},
    {"raqam":"2300","nom":"Taqsimlanmagan foyda","tur":"P"},
    {"raqam":"2310","nom":"Hisobot yili foydasi","tur":"P"},
    {"raqam":"2320","nom":"O'tgan yillar foydasi","tur":"P"},
    {"raqam":"2400","nom":"Maqsadli mablag'lar","tur":"P"},
    {"raqam":"2410","nom":"Davlat subsidiyalari","tur":"P"},
    {"raqam":"2420","nom":"Boshqa maqsadli mablag'lar","tur":"P"},
    {"raqam":"3000","nom":"Uzoq muddatli majburiyatlar","tur":"P"},
    {"raqam":"3010","nom":"Uzoq muddatli bank kreditlari","tur":"P"},
    {"raqam":"3020","nom":"Uzoq muddatli qarzlar","tur":"P"},
    {"raqam":"3030","nom":"Uzoq muddatli ijara majburiyatlari","tur":"P"},
    {"raqam":"3040","nom":"Qayta sug'urtalash bo'yicha majburiyatlar","tur":"P"},
    {"raqam":"3100","nom":"Kechiktirilgan soliq majburiyatlari","tur":"P"},
    {"raqam":"3200","nom":"Pensiya majburiyatlari","tur":"P"},
    {"raqam":"4000","nom":"Joriy majburiyatlar","tur":"P"},
    {"raqam":"4010","nom":"Qisqa muddatli bank kreditlari","tur":"P"},
    {"raqam":"4020","nom":"Joriy qarz ulushi","tur":"P"},
    {"raqam":"4100","nom":"Kreditorlik qarzlari","tur":"P"},
    {"raqam":"4110","nom":"Yetkazib beruvchilar va pudratchilar","tur":"P"},
    {"raqam":"4120","nom":"Sug'urta mukofotlari bo'yicha","tur":"P"},
    {"raqam":"4130","nom":"Sug'urta shartnomalari bo'yicha","tur":"P"},
    {"raqam":"4140","nom":"Qayta sug'urtalash bo'yicha","tur":"P"},
    {"raqam":"4150","nom":"Boshqa kreditorlik qarzlari","tur":"P"},
    {"raqam":"4200","nom":"Mehnat haqi bo'yicha qarz","tur":"P"},
    {"raqam":"4210","nom":"Xodimlarga mehnat haqi","tur":"P"},
    {"raqam":"4220","nom":"Ijtimoiy sug'urta bo'yicha","tur":"P"},
    {"raqam":"4300","nom":"Byudjet bilan hisob-kitoblar","tur":"P"},
    {"raqam":"4310","nom":"Daromad solig'i","tur":"P"},
    {"raqam":"4320","nom":"QQS bo'yicha","tur":"P"},
    {"raqam":"4330","nom":"Mulk solig'i","tur":"P"},
    {"raqam":"4340","nom":"Yer solig'i","tur":"P"},
    {"raqam":"4350","nom":"Boshqa soliqlar","tur":"P"},
    {"raqam":"4400","nom":"Bo'naklardan kreditorlik","tur":"P"},
    {"raqam":"4410","nom":"Xaridorlardan olingan bo'naklar","tur":"P"},
    {"raqam":"4500","nom":"Kechiktirilgan daromadlar","tur":"P"},
    {"raqam":"4510","nom":"Keyingi davrlarga tegishli daromadlar","tur":"P"},
    {"raqam":"4520","nom":"Sug'urta zaxiralari","tur":"P"},
    {"raqam":"4521","nom":"Hayot sug'urtasi zaxiralari","tur":"P"},
    {"raqam":"4522","nom":"Baxtsiz hodisalar sug'urtasi zaxiralari","tur":"P"},
    {"raqam":"4523","nom":"Tibbiy sug'urta zaxiralari","tur":"P"},
    {"raqam":"4524","nom":"Mol-mulk sug'urtasi zaxiralari","tur":"P"},
    {"raqam":"4525","nom":"Mas'uliyat sug'urtasi zaxiralari","tur":"P"},
    {"raqam":"4526","nom":"Qayta sug'urtalash zaxiralari","tur":"P"},
    {"raqam":"5000","nom":"Sug'urta mukofotlari daromadi","tur":"D"},
    {"raqam":"5010","nom":"Hayot sug'urtasi bo'yicha mukofotlar","tur":"D"},
    {"raqam":"5020","nom":"Shaxsiy sug'urta mukofotlari","tur":"D"},
    {"raqam":"5030","nom":"Mulk sug'urtasi mukofotlari","tur":"D"},
    {"raqam":"5040","nom":"Mas'uliyat sug'urtasi mukofotlari","tur":"D"},
    {"raqam":"5050","nom":"Qayta sug'urtalashdan mukofotlar","tur":"D"},
    {"raqam":"5100","nom":"Investitsion daromadlar","tur":"D"},
    {"raqam":"5110","nom":"Dividendlar","tur":"D"},
    {"raqam":"5120","nom":"Foizlar","tur":"D"},
    {"raqam":"5130","nom":"Ijara daromadi","tur":"D"},
    {"raqam":"5200","nom":"Boshqa daromadlar","tur":"D"},
    {"raqam":"5210","nom":"Mol-mulk sotishdan daromad","tur":"D"},
    {"raqam":"5220","nom":"Kurs farqi daromadi","tur":"D"},
    {"raqam":"6000","nom":"Sug'urta to'lovlari xarajatlari","tur":"X"},
    {"raqam":"6010","nom":"Hayot sug'urtasi bo'yicha to'lovlar","tur":"X"},
    {"raqam":"6020","nom":"Shaxsiy sug'urta to'lovlari","tur":"X"},
    {"raqam":"6030","nom":"Mulk sug'urtasi to'lovlari","tur":"X"},
    {"raqam":"6040","nom":"Mas'uliyat sug'urtasi to'lovlari","tur":"X"},
    {"raqam":"6050","nom":"Qayta sug'urtalashga to'lovlar","tur":"X"},
    {"raqam":"6100","nom":"Xodimlar xarajatlari","tur":"X"},
    {"raqam":"6110","nom":"Mehnat haqi xarajatlari","tur":"X"},
    {"raqam":"6120","nom":"Ijtimoiy sug'urta xarajatlari","tur":"X"},
    {"raqam":"6200","nom":"Amortizatsiya xarajatlari","tur":"X"},
    {"raqam":"6210","nom":"Asosiy vositalar amortizatsiyasi","tur":"X"},
    {"raqam":"6220","nom":"Nomoddiy aktivlar amortizatsiyasi","tur":"X"},
    {"raqam":"6300","nom":"Boshqa operatsion xarajatlar","tur":"X"},
    {"raqam":"6310","nom":"Ijara xarajatlari","tur":"X"},
    {"raqam":"6320","nom":"Kommunal xarajatlar","tur":"X"},
    {"raqam":"6330","nom":"Reklama xarajatlari","tur":"X"},
    {"raqam":"6340","nom":"Kommunikatsiya xarajatlari","tur":"X"},
    {"raqam":"6350","nom":"Xizmat safari xarajatlari","tur":"X"},
    {"raqam":"6400","nom":"Moliyaviy xarajatlar","tur":"X"},
    {"raqam":"6410","nom":"Kredit foizlari","tur":"X"},
    {"raqam":"6420","nom":"Kurs farqi zararlari","tur":"X"},
    {"raqam":"6500","nom":"Soliq xarajatlari","tur":"X"},
    {"raqam":"6510","nom":"Daromad solig'i xarajati","tur":"X"},
    {"raqam":"9000","nom":"Moliyaviy natijalar","tur":""},
    {"raqam":"9010","nom":"Foyda va zarar","tur":""},
    {"raqam":"9020","nom":"Taqsimlanmagan foyda (zarar)","tur":""},
]

def get_schyotlar():
    if not _cache["loaded"]:
        _cache["data"] = SCHYOTLAR_DATA
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
        InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
        InlineKeyboardButton("🇷🇺 Ruscha", callback_data="lang_ru")
    ]]
    text = (
        "🌟 Assalomu alaykum! Xush kelibsiz!\n"
        "👋 Salom! Dobro pozhalovat!\n\n"
        "📚 Bu bot siz uchun:\n"
        "🌅 04:00 — Yangi buxgalteriya darsi\n"
        "📝 12:30 — Bilimni tekshirish testi\n"
        "🔄 18:30 — Kechki takrorlash\n"
        "🤖 — AI buxgalter (24/7 savollarga javob)\n\n"
        "🌐 Tilni tanlang / Vyberi yazyk:"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def show_menu(msg, lang, uid, edit=False):
    sub = uid in subscribers
    n = state["lesson_n"]
    if lang == "uz":
        txt = (
            "🏠 Bosh menyu\n\n"
            "📅 Kunlik jadval:\n"
            "🌅 04:00 — Yangi dars\n"
            "📝 12:30 — Test\n"
            "🔄 18:30 — Takrorlash\n\n"
            f"📖 Joriy dars: #{n}-mavzu\n"
            f"🔔 Obuna: {'✅ Faol' if sub else '❌ Yoq'}\n\n"
            "👇 Nima qilmoqchisiz?"
        )
        kb = [
            [InlineKeyboardButton("🤖 AI Buxgalterga savol", callback_data="ai_hint")],
            [InlineKeyboardButton("📋 Schyotlar rejasi (lex.uz)", callback_data="sch_menu")],
            [InlineKeyboardButton("🔕 Obunadan chiqish" if sub else "🔔 Darslarga obuna bolish", callback_data="unsub" if sub else "sub")],
            [InlineKeyboardButton("🌐 Tilni ozgartirish", callback_data="chg_lang")],
        ]
    else:
        txt = (
            "🏠 Glavnoe menyu\n\n"
            "📅 Raspisanie:\n"
            "🌅 04:00 — Urok\n"
            "📝 12:30 — Test\n"
            "🔄 18:30 — Povtorenie\n\n"
            f"📖 Tekushchiy urok: #{n}\n"
            f"🔔 Podpiska: {'✅ Aktivna' if sub else '❌ Net'}\n\n"
            "👇 Chto khotite sdelat?"
        )
        kb = [
            [InlineKeyboardButton("🤖 Vopros AI bukhgalteru", callback_data="ai_hint")],
            [InlineKeyboardButton("📋 Plan schetov (lex.uz)", callback_data="sch_menu")],
            [InlineKeyboardButton("🔕 Otpisatsya" if sub else "🔔 Podpisatsya na uroki", callback_data="unsub" if sub else "sub")],
            [InlineKeyboardButton("🌐 Smenit yazyk", callback_data="chg_lang")],
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
    m = await update.message.reply_text("🔄 Yangilanmoqda..." if lang == "uz" else "🔄 Obnovleniye...")
    s = reload_cache()
    await m.edit_text(
        f"✅ Yangilandi! {len(s)} ta schyot yuklandi." if lang == "uz"
        else f"✅ Obnovleno! Zagruzheno {len(s)} schetov."
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
        "🤔 Tahlil qilinmoqda, biroz kuting..." if lang == "uz"
        else "🤔 Analiziruyetsya, podozhdite..."
    )
    ans = ask_ai(q, lang, ctx)
    await wm.delete()
    await update.message.reply_text("🤖 AI Buxgalter:\n\n" + ans)

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
                "✅ Til tanlandi!\n\n"
                "🎉 Siz avtomatik ravishda darslarga obuna boldingiz!\n\n"
                "📅 Jadval:\n"
                "🌅 04:00 — Yangi dars\n"
                "📝 12:30 — Test\n"
                "🔄 18:30 — Takrorlash\n\n"
                "💬 Istalgan buxgalteriya savolini yozing!"
            )
        else:
            await q.message.reply_text(
                "✅ Yazyk vybran!\n\n"
                "🎉 Vy avtomaticheski podpisany na uroki!\n\n"
                "📅 Raspisanie:\n"
                "🌅 04:00 — Urok\n"
                "📝 12:30 — Test\n"
                "🔄 18:30 — Povtorenie\n\n"
                "💬 Pishite lyuboy bukhgaltersky vopros!"
            )
        await show_menu(q.message, nl, uid)

    elif d == "chg_lang":
        kb = [[
            InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
            InlineKeyboardButton("🇷🇺 Ruscha", callback_data="lang_ru")
        ]]
        await q.edit_message_text("🌐 Tilni tanlang / Vyberi yazyk:", reply_markup=InlineKeyboardMarkup(kb))

    elif d == "sub":
        subscribers.add(uid)
        if lang == "uz":
            await q.message.reply_text(
                "🎉 Muvaffaqiyatli obuna boldingiz!\n\n"
                "📅 Jadval:\n"
                "🌅 Ertalab 04:00 — Yangi dars\n"
                "📝 Tushlik 12:30 — Test\n"
                "🔄 Kechqurun 18:30 — Takrorlash\n\n"
                "📈 Har kuni buxgalteriya bilimlaringiz oshib boradi!"
            )
        else:
            await q.message.reply_text(
                "🎉 Vy uspeshno podpisalis!\n\n"
                "📅 Raspisanie:\n"
                "🌅 Utro 04:00 — Urok\n"
                "📝 Obed 12:30 — Test\n"
                "🔄 Vecher 18:30 — Povtorenie\n\n"
                "📈 Kazhdyy den vashi znaniyu budu rasti!"
            )
        await show_menu(q.message, lang, uid)

    elif d == "unsub":
        subscribers.discard(uid)
        await q.message.reply_text(
            "😔 Obuna bekor qilindi. Qaytib kelishingizni kutamiz!" if lang == "uz"
            else "😔 Podpiska otmenena. Zhdem vas obratno!"
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
            [InlineKeyboardButton(f"📁 {g} seriya — {len(v)} ta schyot", callback_data=f"g_{g}")]
            for g, v in sorted(guruhlar.items())
        ]
        kb.append([InlineKeyboardButton("⬅️ Orqaga" if lang == "uz" else "⬅️ Nazad", callback_data="back")])
        title = (
            f"📋 Schyotlar rejasi\n📊 Jami: {len(sch)} ta schyot\n\n👇 Serirani tanlang:" if lang == "uz"
            else f"📋 Plan schetov\n📊 Vsego: {len(sch)} schetov\n\n👇 Vyberi seriyu:"
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
                f"🌅 Ertalabki Dars #{n}\n📖 Mavzu: {topic}\n\n" if lang == "uz"
                else f"🌅 Urok #{n}\n📖 Tema: {topic}\n\n"
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
                f"📝 Tushlik Testi\n📖 Mavzu: {topic}\n\n" if lang == "uz"
                else f"📝 Obedennoe Testirovanie\n📖 Tema: {topic}\n\n"
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
                f"🔄 Kechki Takrorlash\n📖 Mavzu: {topic}\n\n" if lang == "uz"
                else f"🔄 Vechernee Povtorenie\n📖 Tema: {topic}\n\n"
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
async def main():
    threading.Thread(target=web, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(CallbackQueryHandler(btn_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))

    # AsyncIOScheduler - event loop bilan birga ishlaydi
    sc = AsyncIOScheduler()
    # Toshkent UTC+5: 04:00=23:00UTC, 12:30=07:30UTC, 18:30=13:30UTC
    sc.add_job(_send_lesson, "cron", hour=23, minute=0,  args=[app])
    sc.add_job(_send_test,   "cron", hour=7,  minute=30, args=[app])
    sc.add_job(_send_review, "cron", hour=13, minute=30, args=[app])
    sc.start()

    logger.info("Jadval: 04:00 dars | 12:30 test | 18:30 takrorlash (Toshkent)")
    logger.info("Schyotlar yuklanmoqda...")
    get_schyotlar()
    logger.info("Bot ishga tushdi!")

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
