import telebot
import psycopg2
import json
import time
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
def home(): return "Bot 24/7 faol!"

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

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎯 Quiz Bot faol!", reply_markup=main_menu())

# --- 1. TESTLARNI BOSHQARISH (ULASHISH, TAHRIRLASH, O'CHIRISH) ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('SELECT id, title, quiz_data FROM quizzes WHERE user_id = %s', (message.from_user.id,))
        rows = cur.fetchall(); cur.close(); conn.close()
        if not rows:
            bot.send_message(message.chat.id, "📭 Sizda hali testlar yo'q.")
            return
        for r in rows:
            msg = f"🎲 **“{r[1]}”**\n❓ Savollar: {len(json.loads(r[2]))} ta"
            markup = types.InlineKeyboardMarkup()
            # Tugmalarni qaytaramiz:
            markup.row(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{r[0]}"))
            markup.row(
                types.InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_{r[0]}"),
                types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"delete_{r[0]}")
            )
            bot.send_message(message.chat.id, msg, reply_markup=markup)

# --- 2. CALLBACK HANDLER (O'chirish va Tahrirlash uchun) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()
    
    if call.data.startswith("delete_"):
        q_id = call.data.split("_")[1]
        cur.execute('DELETE FROM quizzes WHERE id = %s AND user_id = %s', (q_id, call.from_user.id))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ Test o'chirildi")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        
    elif call.data.startswith("edit_"):
        bot.answer_callback_query(call.id, "🛠 Tez kunda: Tahrirlash funksiyasi qo'shiladi", show_alert=True)
    
    cur.close(); conn.close()

# --- 3. STATISTIKA ---
@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def stats(message):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM users'); u = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM quizzes'); q = cur.fetchone()[0]
        cur.close(); conn.close()
        bot.send_message(message.chat.id, f"🚀 **Statistika:**\n👤 Users: {u}\n🎲 Testlar: {q}")

# --- 4. TEST YARATISH (AVVALGI FUNKSIYALAR BILAN) ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_new(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'subject': '', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, get_subject_name)
    else:
        bot.reply_to(message, "⛔️ Faqat admin uchun!")

def get_subject_name(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: **{message.text}**\nSavollarni yuboring.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish"))

@bot.message_handler(func=lambda m: True)
def collect_logic(message):
    uid = message.from_user.id
    if uid == ADMIN_ID and uid in user_session:
        if message.text == "🏁 Saqlash":
            s = user_session[uid]
            if s['questions']:
                conn = get_db_connection()
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
            # Savollarni avtomatik tahlil qilish
            raw_blocks = re.split(r'\n\s*\n', message.text.strip())
            for block in raw_blocks:
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if len(lines) >= 3:
                    user_session[uid]['questions'].append({'q': lines[0], 'o': lines[1:], 'c': 0})
            bot.send_message(message.chat.id, f"📥 {len(user_session[uid]['questions'])} ta savol yig'ildi.")

# --- ISHGA TUSHIRISH ---
if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
