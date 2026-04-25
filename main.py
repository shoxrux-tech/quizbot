import os
import telebot
import psycopg2
import json
from telebot import types
from flask import Flask, request
from threading import Timer

# --- ENV ---
TOKEN = os.getenv("8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs")
ADMIN_ID = int(os.getenv("5842665369"))
DATABASE_URL = os.getenv("postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2")
WEBHOOK_URL = os.getenv("https://quizbot-1-fvab.onrender.com") 

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")
app = Flask(__name__)

user_session = {}
active_quizzes = {}
poll_map = {}

# --- DB ---
def db():
    return psycopg2.connect(DATABASE_URL)

# --- WEBHOOK ---
@app.route('/')
def home():
    return "Bot ishlayapti"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "ok"

# --- START ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()

    if len(args) > 1 and args[1].startswith("quiz_"):
        return start_quiz(msg.chat.id, args[1].split("_")[1])

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📚 Test yaratish", "📂 Testlarim")

    bot.send_message(msg.chat.id, "Quiz botga xush kelibsiz!", reply_markup=kb)

# --- CREATE ---
@bot.message_handler(func=lambda m: m.text == "📚 Test yaratish")
def create(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "Faqat admin!")

    user_session[msg.from_user.id] = {"step": "name", "questions": []}
    bot.send_message(msg.chat.id, "Test nomi?")

@bot.message_handler(func=lambda m: m.from_user.id in user_session)
def steps(msg):
    s = user_session[msg.from_user.id]

    if s["step"] == "name":
        s["name"] = msg.text
        s["step"] = "time"
        bot.send_message(msg.chat.id, "Vaqt (sekund)?")

    elif s["step"] == "time":
        s["time"] = int(msg.text) if msg.text.isdigit() else 15
        s["step"] = "q"
        bot.send_message(msg.chat.id,
"""Savol yubor:

Poytaxt?
Toshkent +
Samarqand
Buxoro

Tugatish: Saqlash""")

    elif s["step"] == "q":
        if msg.text.lower() == "saqlash":
            conn = db()
            cur = conn.cursor()

            cur.execute(
                "INSERT INTO quizzes (user_id,title,quiz_data,time_limit) VALUES (%s,%s,%s,%s)",
                (msg.from_user.id, s["name"], json.dumps(s["questions"]), s["time"])
            )
            conn.commit()
            cur.close()
            conn.close()

            bot.send_message(msg.chat.id, "Saqlandi!")
            del user_session[msg.from_user.id]
            return

        blocks = msg.text.strip().split("\n\n")

        for b in blocks:
            lines = b.split("\n")
            if len(lines) < 3:
                continue

            if not any("+" in x for x in lines[1:]):
                bot.send_message(msg.chat.id, "Har savolda + bo‘lishi kerak")
                return

            s["questions"].append({"q": lines[0], "o": lines[1:]})

        bot.send_message(msg.chat.id, f"{len(s['questions'])} ta savol qo‘shildi")

# --- START QUIZ ---
def start_quiz(chat_id, quiz_id):
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT title,quiz_data,time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return bot.send_message(chat_id, "Topilmadi")

    title, data, t = row
    questions = json.loads(data)

    active_quizzes[chat_id] = {
        "questions": questions,
        "index": 0,
        "scores": {},
        "time": t,
        "title": title
    }

    bot.send_message(chat_id, f"🏁 {title} boshlandi!")
    send_next(chat_id)

def send_next(chat_id):
    quiz = active_quizzes.get(chat_id)
    if not quiz:
        return

    if quiz["index"] >= len(quiz["questions"]):
        return finish(chat_id)

    q = quiz["questions"][quiz["index"]]

    opts = []
    correct = 0

    for i, o in enumerate(q["o"]):
        if "+" in o:
            correct = i
            o = o.replace("+", "")
        opts.append(o.strip())

    msg = bot.send_poll(
        chat_id,
        f"{quiz['index']+1}. {q['q']}",
        opts,
        type="quiz",
        correct_option_id=correct,
        is_anonymous=False,
        open_period=quiz["time"]
    )

    poll_map[msg.poll.id] = {
        "chat_id": chat_id,
        "correct": correct
    }

    Timer(quiz["time"], lambda: next_q(chat_id)).start()

def next_q(chat_id):
    if chat_id in active_quizzes:
        active_quizzes[chat_id]["index"] += 1
        send_next(chat_id)

# --- ANSWER ---
@bot.poll_answer_handler()
def answer(ans):
    if ans.poll_id not in poll_map:
        return

    data = poll_map[ans.poll_id]
    chat_id = data["chat_id"]

    if chat_id not in active_quizzes:
        return

    quiz = active_quizzes[chat_id]
    uid = ans.user.id

    if uid not in quiz["scores"]:
        quiz["scores"][uid] = {"name": ans.user.first_name, "score": 0}

    if ans.option_ids and ans.option_ids[0] == data["correct"]:
        quiz["scores"][uid]["score"] += 1

# --- FINISH ---
def finish(chat_id):
    quiz = active_quizzes.get(chat_id)
    if not quiz:
        return

    res = sorted(quiz["scores"].values(), key=lambda x: x["score"], reverse=True)

    text = f"🏁 {quiz['title']} tugadi!\n\n"

    for i, u in enumerate(res[:10]):
        text += f"{i+1}. {u['name']} — {u['score']}\n"

    bot.send_message(chat_id, text)

    del active_quizzes[chat_id]

# --- MY TESTS ---
@bot.message_handler(func=lambda m: m.text == "📂 Testlarim")
def my(msg):
    if msg.from_user.id != ADMIN_ID:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT id,title FROM quizzes WHERE user_id=%s", (ADMIN_ID,))
    rows = cur.fetchall()

    username = bot.get_me().username

    for r in rows:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🚀 Boshlash", url=f"https://t.me/{username}?start=quiz_{r[0]}"))
        kb.add(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{username}?startgroup=quiz_{r[0]}"))

        bot.send_message(msg.chat.id, r[1], reply_markup=kb)

    cur.close()
    conn.close()

# --- RUN ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + "/" + TOKEN)
    app.run(host="0.0.0.0", port=8080)
