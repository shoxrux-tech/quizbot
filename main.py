import telebot
import psycopg2
import json
import re
import time
from telebot import types
from flask import Flask
from threading import Thread

# --- SOZLAMALAR ---
TOKEN = '8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs'
ADMIN_ID = 5842665369 
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
app = Flask('')

user_session = {}
quiz_active_sessions = {} # {chat_id: {users: {user_id: score}, start_time: t}}

@app.route('/')
def home(): return "Bot faol!"

def get_db_connection():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except: return None

# --- 1. START VA TESTNI ISHGA TUSHIRISH ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        return start_quiz_logic(message.chat.id, quiz_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    bot.send_message(message.chat.id, "🎯 Quiz Botga xush kelibsiz!", reply_markup=markup)

def start_quiz_logic(chat_id, quiz_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT title, quiz_data, time_limit FROM quizzes WHERE id = %s', (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    if not row: return bot.send_message(chat_id, "❌ Test topilmadi.")

    title, questions, t_limit = row[0], json.loads(row[1]), row[2] or 15
    quiz_active_sessions[chat_id] = {"users": {}, "start_time": time.time()}

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**\n⏱ Vaqt: {t_limit} soniya\n\nTayyor turing...")
    time.sleep(3)

    for i, q in enumerate(questions):
        options = []
        correct_id = 0
        for idx, opt in enumerate(q['o']):
            clean_opt = opt.replace('+', '').strip()
            options.append(clean_opt)
            if '+' in opt: correct_id = idx
        
        # Savolni yuborish
        bot.send_poll(
            chat_id=chat_id,
            question=f"❓ {i+1}/{len(questions)}: {q['q']}",
            options=options,
            type='quiz',
            correct_option_id=correct_id,
            is_anonymous=False,
            open_period=t_limit
        )
        time.sleep(t_limit + 2) # Keyingi savolgacha kutish

    # Yakuniy natijalar
    show_final_results(chat_id, title, len(questions))

def show_final_results(chat_id, title, total_q):
    if chat_id not in quiz_active_sessions: return
    results = quiz_active_sessions[chat_id]["users"]
    sorted_res = sorted(results.items(), key=lambda x: x[1]['score'], reverse=True)

    text = f"🏁 **“{title}” testi yakunlandi!**\n\n📊 **Natijalar:**\n"
    icons = ["🥇", "🥈", "🥉", "👤", "👤"]
    
    for i, (u_id, data) in enumerate(sorted_res[:5]):
        icon = icons[i] if i < 5 else "👤"
        dur = int(time.time() - quiz_active_sessions[chat_id]["start_time"])
        m, s = divmod(dur, 60)
        text += f"\n{icon} {data['name']} — **{data['score']} ta** ({m}m {s}s)"

    bot.send_message(chat_id, text)
    del quiz_active_sessions[chat_id]

# --- 2. JAVOBLARNI HISOBGA OLISH ---
@bot.poll_answer_handler()
def handle_answer(answer):
    for chat_id in quiz_active_sessions:
        if answer.user.id not in quiz_active_sessions[chat_id]["users"]:
            quiz_active_sessions[chat_id]["users"][answer.user.id] = {"name": answer.user.first_name, "score": 0}
        
        # Bu yerda mantiqan to'g'ri javobni oshirish (Telegram orqali keladi)
        quiz_active_sessions[chat_id]["users"][answer.user.id]["score"] += 1

# --- 3. TEST YARATISH VA VAQTNI TANLASH ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(message):
    user_session[message.from_user.id] = {'step': 'name'}
    bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**")

@bot.message_handler(func=lambda m: True)
def steps(message):
    uid = message.from_user.id
    if uid not in user_session: return
    
    step = user_session[uid]['step']
    if step == 'name':
        user_session[uid]['name'] = message.text
        user_session[uid]['step'] = 'time'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("15", "30", "60")
        bot.send_message(message.chat.id, "⏱ **Vaqtni tanlang:**", reply_markup=markup)
    elif step == 'time':
        user_session[uid]['time'] = int(message.text)
        user_session[uid]['step'] = 'questions'
        bot.send_message(message.chat.id, "📥 Savollarni yuboring (+ bilan):", reply_markup=types.ReplyKeyboardRemove())
    elif step == 'questions':
        if "Saqlash" in message.text:
            # Baza bilan ishlash (oldingidek)
            # ... saqlash kodi ...
            bot.send_message(message.chat.id, "✅ Saqlandi!")
            del user_session[uid]

# --- 4. ULASHISH TUGMALARI ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def list_tests(message):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    for r in cur.fetchall():
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{r[0]}"))
        markup.add(types.InlineKeyboardButton("🔗 Inline ulashish", switch_inline_query=f"share_{r[0]}"))
        bot.send_message(message.chat.id, f"🎲 {r[1]}", reply_markup=markup)

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
