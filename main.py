import os
import telebot
import psycopg2
import json
import time
import threading
import re
from telebot import types
from flask import Flask
from threading import Thread

# --- RENDER UCHUN UYG'OQ TUTUVCHI QISM ---
app = Flask('')
@app.route('/')
def home():
    return "Bot tirik va ishlamoqda!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- SOZLAMALAR (Environment Variables orqali) ---
TOKEN = os.getenv("TOKEN", "8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5842665369"))
DATABASE_URL = os.getenv("postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a.ohio-postgres.render.com/quizdb_wgm2")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

bot = telebot.TeleBot(TOKEN)
user_session = {}

# --- BAZA BILAN ISHLASH (PostgreSQL) ---
def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Jadvallarni professional PostgreSQL formatida yaratish
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            title TEXT,
            quiz_data JSONB,
            time_limit INTEGER DEFAULT 15
        );
    """)
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

# --- KLAVIATURALAR ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish")
    markup.row("📂 Mening testlarim", "📊 Statistika")
    markup.row("👨‍💻 Admin")
    return markup

def creation_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📦 Blokni yopish")
    markup.add("🏁 Fanni yakunlash (Saqlash)")
    markup.add("❌ Bekor qilish")
    return markup

def time_markup(q_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("15 sek", callback_data=f"t_15_{q_id}"),
               types.InlineKeyboardButton("30 sek", callback_data=f"t_30_{q_id}"))
    markup.add(types.InlineKeyboardButton("✏️ O'z vaqtimni kiritish", callback_data=f"custom_{q_id}"))
    return markup

# --- TEST YUBORISH LOGIKASI ---
def run_quiz_logic(chat_id, q_id, interval):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    
    if res:
        title, data = res[0], res[1]
        qs = data if isinstance(data, list) else json.loads(data)
        bot.send_message(chat_id, f"🏁 **{title}** testi boshlandi!\n⏱ Interval: {interval}s", parse_mode="Markdown")
        
        for idx, i in enumerate(qs, 1):
            try:
                bot.send_poll(
                    chat_id, 
                    f"[{idx}/{len(qs)}] {i['q']}", 
                    i['o'], 
                    type='quiz', 
                    correct_option_id=i['c'], 
                    is_anonymous=False,
                    open_period=interval
                )
                time.sleep(interval + 1)
            except Exception as e:
                print(f"Xato: {e}")
                break
        bot.send_message(chat_id, "✅ Test yakunlandi!", reply_markup=main_menu())

# --- HANDLERLAR ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    if uid in user_session: del user_session[uid]
    bot.send_message(message.chat.id, "👋 Quiz Bot professional tizimi ishga tushdi!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_new(message):
    if message.from_user.id != ADMIN_ID:
        return bot.send_message(message.chat.id, "⛔️ Faqat admin test yarata oladi!")
    user_session[message.from_user.id] = {'subject': '', 'questions': []}
    bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, get_subject_name)

def get_subject_name(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: **{message.text}**\nSavollarni yuboring (Namuna:\nSavol?\nJavob 1\nJavob 2+)", reply_markup=creation_menu())

@bot.message_handler(func=lambda m: m.text == "📦 Blokni yopish")
def block_close(message):
    uid = message.from_user.id
    if uid in user_session:
        num = len(user_session[uid]['questions'])
        bot.send_message(message.chat.id, f"📦 Blok yopildi. Jami savollar: {num}", reply_markup=creation_menu())

@bot.message_handler(func=lambda m: m.text == "🏁 Fanni yakunlash (Saqlash)")
def finish_creation(message):
    uid = message.from_user.id
    if uid in user_session and user_session[uid]['questions']:
        s = user_session[uid]
        conn = get_db()
        cur = conn.cursor()
        cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', 
                    (uid, s['subject'], json.dumps(s['questions'])))
        conn.commit()
        cur.close()
        conn.close()
        bot.send_message(message.chat.id, "🎉 Test PostgreSQL bazasiga muvaffaqiyatli saqlandi!", reply_markup=main_menu())
        del user_session[uid]

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        bot.send_message(message.chat.id, "📭 Hozircha testlaringiz yo'q.")
        return
    for r in rows:
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{r[0]}"))
        m.add(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{r[0]}"))
        bot.send_message(message.chat.id, f"📂 **{r[1]}**", reply_markup=m, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def query_handler(call):
    data_parts = call.data.split('_')
    q_id = data_parts[-1]
    
    if call.data.startswith('run_'):
        bot.edit_message_text("⏱ Testlar orasidagi vaqtni tanlang:", call.message.chat.id, call.message.message_id, reply_markup=time_markup(q_id))
    
    elif call.data.startswith('t_'):
        sec = int(data_parts[1])
        bot.delete_message(call.message.chat.id, call.message.message_id)
        threading.Thread(target=run_quiz_logic, args=(call.message.chat.id, q_id, sec)).start()
    
    elif call.data.startswith('custom_'):
        msg = bot.send_message(call.message.chat.id, "🔢 Soniyani raqamda yozing:")
        bot.register_next_step_handler(msg, start_with_custom, q_id)
    
    elif call.data.startswith('del_'):
        conn = get_db()
        cur = conn.cursor()
        cur.execute('DELETE FROM quizzes WHERE id = %s', (q_id,))
        conn.commit()
        cur.close()
        conn.close()
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "Test o'chirildi")

def start_with_custom(message, q_id):
    if message.text.isdigit():
        threading.Thread(target=run_quiz_logic, args=(message.chat.id, q_id, int(message.text))).start()
    else:
        bot.send_message(message.chat.id, "❌ Faqat raqam kiriting!")

@bot.message_handler(func=lambda m: True)
def collect(message):
    uid = message.from_user.id
    if uid in user_session:
        if message.text in ["📦 Blokni yopish", "🏁 Fanni yakunlash (Saqlash)", "❌ Bekor qilish"]:
            return
        new_qs = parse_multiline_questions(message.text)
        if new_qs:
            user_session[uid]['questions'].extend(new_qs)
            bot.send_message(message.chat.id, f"📥 {len(new_qs)} ta savol qabul qilindi.")
        else:
            bot.send_message(message.chat.id, "⚠️ Format xato!")

if __name__ == '__main__':
    init_db()
    keep_alive() 
    print("Bot Render + PostgreSQL'da ishga tushdi...")
    bot.infinity_polling()
