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
ADMIN_ID = 5842665369 
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
app = Flask('')

user_session = {}

@app.route('/')
def home(): return "Bot faol!"

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except: return None

# --- ASOSIY MENYU ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    return markup

# --- 1. START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎯 Quiz Bot faol!", reply_markup=main_menu())

# --- 2. STATISTIKA (MUHIM: Tartibda birinchi) ---
@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def stats(message):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM users'); u = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM quizzes'); q = cur.fetchone()[0]
        cur.close(); conn.close()
        bot.send_message(message.chat.id, f"🚀 **Bot statistikasi:**\n\n👤 Foydalanuvchilar: {u}\n🎲 Jami testlar: {q}")

# --- 3. MENING TESTLARIM (Sizda ko'rinmayotgan qism) ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        # Foydalanuvchi yaratgan barcha testlarni bazadan qidirish
        cur.execute('SELECT id, title, quiz_data FROM quizzes WHERE user_id = %s', (message.from_user.id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        
        if not rows:
            bot.send_message(message.chat.id, "📭 Sizda hali yaratilgan testlar yo'q.")
            return
            
        for r in rows:
            q_data = json.loads(r[2])
            msg = f"🎲 **“{r[1]}”**\n❓ Savollar soni: {len(q_data)} ta"
            markup = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{r[0]}")
            )
            bot.send_message(message.chat.id, msg, reply_markup=markup)

# --- 4. YO'RIQNOMA ---
@bot.message_handler(func=lambda m: m.text == "❓ Yo'riqnoma")
def help_guide(message):
    bot.send_message(message.chat.id, "📖 Savollarni namunadagidek yuboring va oxirida 'Saqlash' tugmasini bosing.")

# --- 5. TEST YARATISHNI BOSHLASH ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_new(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'subject': '', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, get_subject_name)
    else:
        bot.reply_to(message, "⛔️ Test tuzish faqat admin uchun!")

def get_subject_name(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: **{message.text}**\nSavollarni yuboring.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish"))

# --- 6. SAVOLLARNI YIG'ISH (MUHIM: Tartibda oxirida) ---
@bot.message_handler(func=lambda m: True)
def collect(message):
    uid = message.from_user.id
    # Agar foydalanuvchi admin bo'lsa va test yaratish jarayonida bo'lsa
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
            if uid in user_session: del user_session[uid]
            bot.send_message(message.chat.id, "O'chirildi.", reply_markup=main_menu())
        else:
            # Bu yerda savollarni tahlil qilish (parse) funksiyasi ishlaydi
            raw_blocks = re.split(r'\n\s*\n', message.text.strip())
            for block in raw_blocks:
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if len(lines) >= 3:
                    user_session[uid]['questions'].append({'q': lines[0], 'o': lines[1:], 'c': 0})
            bot.send_message(message.chat.id, f"📥 Savollar olindi. Jami: {len(user_session[uid]['questions'])}")

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
