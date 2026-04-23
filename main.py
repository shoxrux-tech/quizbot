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
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2' # Internal URL'ni qo'ying

bot = telebot.TeleBot(TOKEN)
app = Flask('')
user_session = {}

@app.route('/')
def home(): return "Bot barcha tugmalari bilan faol!"

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

# --- MENYULAR ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    markup.row("👨‍💻 Adminga murojaat")
    return markup

# --- HANDLERLAR ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "🎯 Quiz Botga xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu())

# 📊 Statistika tugmasi
@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def show_stat(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM quizzes')
    total_quizzes = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT user_id) FROM quizzes')
    total_users = cur.fetchone()[0]
    cur.close()
    conn.close()
    bot.send_message(message.chat.id, f"📈 **Bot statistikasi:**\n\n👥 Umumiy foydalanuvchilar: {total_users}\n📝 Jami yaratilgan testlar: {total_quizzes}")

# ❓ Yo'riqnoma tugmasi
@bot.message_handler(func=lambda m: m.text == "❓ Yo'riqnoma")
def help_guide(message):
    text = ("📖 **Botdan foydalanish bo'yicha yo'riqnoma:**\n\n"
            "1. 'Yangi fan testi yaratish' tugmasini bosing.\n"
            "2. Fan nomini yuboring.\n"
            "3. Savollarni quyidagi formatda yuboring:\n"
            "   `Savol matni`\n"
            "   `Variant 1`\n"
            "   `Variant 2+` (To'g'risiga + belgisini qo'ying)\n"
            "4. 'Saqlash' tugmasini bosing.")
    bot.send_message(message.chat.id, text)

# 📂 Mening testlarim (Tahrirlash tugmasi bilan)
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        bot.send_message(message.chat.id, "📭 Sizda hali testlar yo'q.")
        return
        
    for r in rows:
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_15_{r[0]}"))
        m.add(types.InlineKeyboardButton("📝 Tahrirlash", callback_data=f"edit_{r[0]}"))
        m.add(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{r[0]}"))
        bot.send_message(message.chat.id, f"📂 **{r[1]}**", reply_markup=m)

# 📝 Tahrirlash funksiyasi
@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def edit_quiz(call):
    q_id = int(call.data.split('_')[1])
    user_session[call.from_user.id] = {'edit_id': q_id, 'subject': '', 'questions': []}
    bot.send_message(call.message.chat.id, "📝 Test uchun yangi fan nomini yuboring (yoki eskisi qolsin):")
    bot.register_next_step_handler(call.message, get_edit_subject)

def get_edit_subject(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, "📥 Endi yangi savollar blokini yuboring. Bu eski savollarni to'liq almashtiradi.")
        bot.register_next_step_handler(message, finalize_edit)

def finalize_edit(message):
    uid = message.from_user.id
    if uid in user_session:
        new_qs = parse_multiline_questions(message.text) # Avvalgi parse funksiyasi kodi ishlatiladi
        if new_qs:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('UPDATE quizzes SET title = %s, quiz_data = %s WHERE id = %s', 
                        (user_session[uid]['subject'], json.dumps(new_qs), user_session[uid]['edit_id']))
            conn.commit()
            cur.close()
            conn.close()
            bot.send_message(message.chat.id, "✅ Test muvaffaqiyatli tahrirlandi!", reply_markup=main_menu())
            del user_session[uid]

# --- Qolgan funksiyalar (parse, run_quiz_logic, collect) avvalgidek qoladi ---
