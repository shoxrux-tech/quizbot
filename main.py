import telebot
import psycopg2
import json
import time
import threading
import re
from telebot import types
from flask import Flask
from threading import Thread

# --- SOZLAMALAR ---
TOKEN = '8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs'
ADMIN_ID = 5842665369  # Faqat shu ID test yarata oladi
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
app = Flask('')

user_session = {}
quiz_results = {}

@app.route('/')
def home(): return "Bot 24/7 faol!"

# --- BAZA BILAN ISHLASH (XATOLIKLARSIZ) ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except Exception as e:
        print(f"Database error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY)')
        cur.execute('CREATE TABLE IF NOT EXISTS quizzes (id SERIAL PRIMARY KEY, user_id BIGINT, title TEXT, quiz_data TEXT)')
        conn.commit()
        cur.close(); conn.close()

def register_user(user_id):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING', (user_id,))
        cur.execute('SELECT COUNT(*) FROM users')
        count = cur.fetchone()[0]
        conn.commit(); cur.close(); conn.close()
        # Profilni avtomatik yangilash
        try: bot.set_my_description(f"📊 {count} ta foydalanuvchi bilimini sinamoqda!")
        except: pass
        return count
    return 0

# --- ASOSIY MENYU ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    return markup

# --- TEST YIG'ISH VA ADMIN NAZORATI ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_new(message):
    uid = message.from_user.id
    if uid == ADMIN_ID:
        user_session[uid] = {'subject': '', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, get_subject_name)
    else:
        bot.reply_to(message, "⛔️ Test tuzish faqat admin uchun!")
        bot.send_message(ADMIN_ID, f"🔔 So'rov: {message.from_user.first_name} (@{message.from_user.username})")

def get_subject_name(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: **{message.text}**\nSavollarni namunadagidek yuboring.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish"))

@bot.message_handler(func=lambda m: True)
def collect(message):
    uid = message.from_user.id
    if uid == ADMIN_ID and uid in user_session:
        if message.text == "🏁 Saqlash":
            s = user_session[uid]
            if not s['questions']: return
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', 
                            (uid, s['subject'], json.dumps(s['questions'])))
                conn.commit(); cur.close(); conn.close()
                bot.send_message(message.chat.id, "🎉 Test saqlandi!", reply_markup=main_menu())
                del user_session[uid]
        elif message.text == "❌ Bekor qilish":
            del user_session[uid]
            bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=main_menu())
        else:
            # Savollarni qabul qilish
            new_qs = parse_multiline_questions(message.text)
            if new_qs:
                user_session[uid]['questions'].extend(new_qs)
                bot.send_message(message.chat.id, f"📥 {len(new_qs)} ta savol olindi.")

# --- INLINE VA POLL HANDLERLARINI QO'SHING ---
# (Avvalgi koddagi parse_multiline_questions, handle_poll_answer va inline_share qismlarini o'zgarishsiz qoldiring)

if __name__ == '__main__':
    init_db()
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
