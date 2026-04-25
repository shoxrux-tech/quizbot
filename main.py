import os
import telebot
import psycopg2
import json
import re
import time
from telebot import types
from flask import Flask, request

# --- SOZLAMALAR ---
TOKEN = os.getenv("8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs")
ADMIN_ID = int(os.getenv("5842665369"))
DATABASE_URL = os.getenv("postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a.ohio-postgres.render.com/quizdb_wgm2")
WEBHOOK_URL = os.getenv("https://quizbot-1-eeuf.onrender.com")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Kesh xotira
user_session = {}
active_quizzes = {}

def get_db():
    return psycopg2.connect(DATABASE_URL)

@app.route('/')
def home(): return "OK"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "ok"

# --- MENYU ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        return start_quiz_logic(msg.chat.id, args[1].replace("run_", ""))
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot professional tizimiga xush kelibsiz!**", reply_markup=kb, parse_mode="Markdown")

# --- ADMIN TEKSHIRUVI ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "⛔️ **Kechirasiz, faqat admin test yarata oladi!**", parse_mode="Markdown")

    user_session[msg.from_user.id] = {"step": "name", "questions": []}
    bot.send_message(msg.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.from_user.id in user_session)
def process_creation(msg):
    uid = msg.from_user.id
    s = user_session[uid]

    if s["step"] == "name":
        s["name"] = msg.text
        s["step"] = "time"
        bot.send_message(msg.chat.id, "⏱ **Har bir savolga necha soniya vaqt berilsin?**")

    elif s["step"] == "time":
        s["time"] = int(msg.text) if msg.text.isdigit() else 15
        s["step"] = "questions"
        bot.send_message(msg.chat.id, "✅ Endi savollarni yuboring. Tugagach **Saqlash** tugmasini bosing.")

    elif s["step"] == "questions":
        if "Saqlash" in msg.text:
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s)",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(msg.chat.id, "🎉 **Test saqlandi!**", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📂 Mening testlarim"))
            del user_session[uid]
            return

        blocks = re.split(r'\n\s*\n', msg.text.strip())
        for b in blocks:
            lines = [l.strip() for l in b.split('\n') if l.strip()]
            if len(lines) >= 3:
                s["questions"].append({"q": lines[0], "o": lines[1:]})
        
        bot.send_message(msg.chat.id, f"📥 {len(s['questions'])} ta savol olindi.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

# --- TESTNI O'TKAZISH (ENGINE) ---
def start_quiz_logic(chat_id, quiz_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row: return

    title, questions, t_limit = row[0], json.loads(row[1]), row[2]
    active_quizzes[chat_id] = {"scores": {}, "start_time": time.time(), "total": len(questions)}

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**", parse_mode="Markdown")
    
    for i, q in enumerate(questions):
        options = [o.replace("+", "").strip() for o in q["o"]]
        correct_id = next(idx for idx, o in enumerate(q["o"]) if "+" in o)
        
        bot.send_poll(
            chat_id, f"{i+1}/{len(questions)}: {q['q']}", options,
            type="quiz", correct_option_id=correct_id, is_anonymous=False, open_period=t_limit
        )
        time.sleep(t_limit + 1)
    
    finalize_results(chat_id, title)

def finalize_results(chat_id, title):
    if chat_id not in active_quizzes: return
    data = active_quizzes[chat_id]
    sorted_res = sorted(data["scores"].items(), key=lambda x: x[1]['score'], reverse=True)
    
    res_text = f"🏁 **“{title}” testi yakunlandi!**\n\n📊 **Natijalar:**\n"
    for i, (u_id, info) in enumerate(sorted_res[:5]):
        icon = ["🥇", "🥈", "🥉", "👤"][i] if i < 4 else "👤"
        dur = int(time.time() - data["start_time"])
        m, s = divmod(dur, 60)
        res_text += f"\n{icon} {info['name']} — **{info['score']} ta** ({m}m {s}s)"

    bot.send_message(chat_id, res_text + "\n\n🏆 Tabriklaymiz!", parse_mode="Markdown")
    del active_quizzes[chat_id]

@bot.poll_answer_handler()
def handle_poll(ans):
    for c_id, quiz in active_quizzes.items():
        if ans.user.id not in quiz["scores"]:
            quiz["scores"][ans.user.id] = {"name": ans.user.first_name, "score": 0}
        quiz["scores"][ans.user.id]["score"] += 1

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_list(msg):
    if msg.from_user.id != ADMIN_ID: return
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, title FROM quizzes WHERE user_id=%s", (msg.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    for r in rows:
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚀 Boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{r[0]}"))
        bot.send_message(msg.chat.id, f"🎲 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 10000)))
