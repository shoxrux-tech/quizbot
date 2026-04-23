import telebot
import psycopg2
import json
import time
import threading
import re
from telebot import types
from flask import Flask
from threading import Thread

# --- RENDER UCHUN UYG'OQ TUTUVCHI ---
app = Flask('')
@app.route('/')
def home(): return "Baza ulangan va bot ishlayapti!"

def run_web(): app.run(host='0.0.0.0', port=8080)

# --- KONFIGURATSIYA ---
TOKEN = '8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs'
# NUSXALANGAN INTERNAL URL'NI SHU YERGA QO'YING:
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
user_session = {}

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS quizzes (id SERIAL PRIMARY KEY, user_id BIGINT, title TEXT, quiz_data TEXT)')
    conn.commit()
    cur.close()
    conn.close()

# --- SAVOLLARNI TAHLIL QILISH ---
def parse_multiline_questions(text):
    raw_blocks = re.split(r'\n\s*\n', text.strip())
    parsed_questions = []
    for block in raw_blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) >= 3:
            q_text = lines[0]
            opts, corr = [], 0
            for i, opt in enumerate(lines[1:]):
                if opt.endswith('+'):
                    opts.append(opt[:-1].strip())
                    corr = i
                else:
                    opts.append(opt)
            parsed_questions.append({'q': q_text, 'o': opts, 'c': corr})
    return parsed_questions

# --- MENYULAR ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish")
    markup.row("📂 Mening testlarim")
    return markup

def creation_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🏁 Fanni yakunlash (Saqlash)", "❌ Bekor qilish")
    return markup

# --- TEST YUBORISH LOGIKASI ---
def run_quiz_logic(chat_id, q_id, interval):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    if res:
        title, data = res
        qs = json.loads(data)
        bot.send_message(chat_id, f"🏁 **{title}** testi boshlandi!")
        for idx, i in enumerate(qs, 1):
            try:
                bot.send_poll(chat_id, f"[{idx}/{len(qs)}] {i['q']}", i['o'], type='quiz', correct_option_id=i['c'], is_anonymous=False)
                time.sleep(interval)
            except: break
        bot.send_message(chat_id, "✅ Test yakunlandi!", reply_markup=main_menu())

# --- HANDLERLAR ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "👋 Bot Postgres bazasi bilan tayyor!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_new(message):
    user_session[message.from_user.id] = {'subject': '', 'questions': []}
    bot.send_message(message.chat.id, "📖 Fan nomini yozing:")
    bot.register_next_step_handler(message, get_subject_name)

def get_subject_name(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: {message.text}. Savollarni yuboring.", reply_markup=creation_menu())

@bot.message_handler(func=lambda m: m.text == "🏁 Fanni yakunlash (Saqlash)")
def finish_creation(message):
    uid = message.from_user.id
    if uid in user_session and user_session[uid]['questions']:
        s = user_session[uid]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', (uid, s['subject'], json.dumps(s['questions'])))
        conn.commit()
        cur.close()
        conn.close()
        bot.send_message(message.chat.id, "🎉 Test bazaga saqlandi!", reply_markup=main_menu())
        del user_session[uid]

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📭 Hozircha testlar yo'q.")
        return
    for r in rows:
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🚀 15 sek interval", callback_data=f"run_15_{r[0]}"))
        m.add(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{r[0]}"))
        bot.send_message(message.chat.id, f"📂 **{r[1]}**", reply_markup=m)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    p = call.data.split('_')
    if p[0] == 'run':
        threading.Thread(target=run_quiz_logic, args=(call.message.chat.id, int(p[2]), int(p[1]))).start()
    elif p[0] == 'del':
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM quizzes WHERE id = %s', (p[1],))
        conn.commit()
        cur.close()
        conn.close()
        bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: True)
def collect(message):
    uid = message.from_user.id
    if uid in user_session:
        if message.text in ["🏁 Fanni yakunlash (Saqlash)", "❌ Bekor qilish"]: return
        new_qs = parse_multiline_questions(message.text)
        if new_qs:
            user_session[uid]['questions'].extend(new_qs)
            bot.send_message(message.chat.id, f"📥 {len(new_qs)} ta savol olindi.")

if __name__ == '__main__':
    init_db()
    Thread(target=run_web).start()
    bot.polling(none_stop=True)
