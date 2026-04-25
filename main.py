import os
import telebot
import psycopg2
import json
import re
import time
from telebot import types
from flask import Flask, request

# --- KONFIGURATSIYA (Render Environment Variables dan oladi) ---
TOKEN = os.getenv("8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs")
ADMIN_ID = int(os.getenv("5842665369")) # O'zingizning ID raqamingiz
DATABASE_URL = os.getenv("postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2")
WEBHOOK_URL = os.getenv("https://quizbot-1-fvab.onrender.com")

# Postgres URL ni Render uchun to'g'irlash
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Kesh xotira
user_session = {}
active_quizzes = {} # {chat_id: {scores: {}, start_time: t, questions: [], index: n, title: str, time: int}}

def get_db():
    return psycopg2.connect(DATABASE_URL)

@app.route('/')
def home(): return "Bot Faol!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "ok"

# --- ASOSIY MENYU ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        return start_quiz_engine(msg.chat.id, args[1].replace("run_", ""))
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Test yaratish", "📂 Testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot professional tizimiga xush kelibsiz!**", reply_markup=kb, parse_mode="Markdown")

# --- FAQAT ADMIN TEST YARATA OLADI ---
@bot.message_handler(func=lambda m: m.text == "📚 Test yaratish")
def create_init(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "⛔️ **Faqat admin test yarata oladi!**", parse_mode="Markdown")

    user_session[msg.from_user.id] = {"step": "name", "questions": []}
    bot.send_message(msg.chat.id, "📖 **Test nomini (fanni) kiriting:**", reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.from_user.id in user_session)
def creation_steps(msg):
    uid = msg.from_user.id
    s = user_session[uid]

    if s["step"] == "name":
        s["name"] = msg.text
        s["step"] = "time"
        bot.send_message(msg.chat.id, "⏱ **Har bir savolga necha soniya vaqt berilsin? (Masalan: 15)**", parse_mode="Markdown")

    elif s["step"] == "time":
        s["time"] = int(msg.text) if msg.text.isdigit() else 15
        s["step"] = "q"
        bot.send_message(msg.chat.id, "📥 **Savollarni namunadagidek yuboring:**\n\nSavol matni?\nVariant 1+\nVariant 2\n\n*Tugatish uchun 'Saqlash' tugmasini bosing.*", parse_mode="Markdown")

    elif s["step"] == "q":
        if msg.text.lower() == "saqlash":
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s)",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(msg.chat.id, "✅ **Test muvaffaqiyatli saqlandi!**", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📂 Testlarim"), parse_mode="Markdown")
            del user_session[uid]
            return

        blocks = re.split(r'\n\s*\n', msg.text.strip())
        for b in blocks:
            lines = [l.strip() for l in b.split('\n') if l.strip()]
            if len(lines) >= 3:
                s["questions"].append({"q": lines[0], "o": lines[1:]})
        
        bot.send_message(msg.chat.id, f"📥 {len(s['questions'])} ta savol olindi.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Saqlash"))

# --- TESTNI O'TKAZISH MANTIQI ---
def start_quiz_engine(chat_id, quiz_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    if not row: return bot.send_message(chat_id, "❌ Test topilmadi.")

    title, data, t_limit = row[0], json.loads(row[1]), row[2]
    active_quizzes[chat_id] = {"scores": {}, "start_time": time.time(), "questions": data, "index": 0, "title": title, "time": t_limit}
    
    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**", parse_mode="Markdown")
    send_question(chat_id)

def send_question(chat_id):
    quiz = active_quizzes.get(chat_id)
    if not quiz or quiz["index"] >= len(quiz["questions"]):
        return finalize(chat_id)

    q = quiz["questions"][quiz["index"]]
    options = [o.replace("+", "").strip() for o in q["o"]]
    correct = next(i for i, o in enumerate(q["o"]) if "+" in o)

    bot.send_poll(
        chat_id, f"{quiz['index']+1}. {q['q']}", options,
        type="quiz", correct_option_id=correct, is_anonymous=False, open_period=quiz["time"]
    )
    # Timer o'rniga keyingi savolga o'tishni poll yopilganda qilamiz
    time.sleep(quiz["time"] + 1)
    quiz["index"] += 1
    send_question(chat_id)

@bot.poll_answer_handler()
def handle_answer(ans):
    # Bu yerda natijalar hisoblanadi
    for c_id, quiz in active_quizzes.items():
        if ans.user.id not in quiz["scores"]:
            quiz["scores"][ans.user.id] = {"name": ans.user.first_name, "score": 0}
        # Javobni tekshirish mantiqi (avtomatik quiz rejimi Telegram'da)
        quiz["scores"][ans.user.id]["score"] += 1 

def finalize(chat_id):
    quiz = active_quizzes.get(chat_id)
    if not quiz: return
    
    res = sorted(quiz["scores"].values(), key=lambda x: x["score"], reverse=True)
    text = f"🏁 **“{quiz['title']}” testi yakunlandi!**\n\n📊 **Natijalar:**\n"
    icons = ["🥇", "🥈", "🥉", "👤"]
    
    for i, u in enumerate(res[:5]):
        icon = icons[i] if i < 4 else "👤"
        text += f"\n{icon} {u['name']} — **{u['score']} ta**"

    bot.send_message(chat_id, text + "\n\n🏆 Tabriklaymiz!", parse_mode="Markdown")
    del active_quizzes[chat_id]

@bot.message_handler(func=lambda m: m.text == "📂 Testlarim")
def list_tests(msg):
    if msg.from_user.id != ADMIN_ID: return
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, title FROM quizzes WHERE user_id=%s", (msg.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    for r in rows:
        markup = types.InlineKeyboardMarkup()
        u = bot.get_me().username
        markup.add(types.InlineKeyboardButton("🚀 Boshlash", url=f"https://t.me/{u}?start=run_{r[0]}"))
        bot.send_message(msg.chat.id, f"🎲 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 10000)))
