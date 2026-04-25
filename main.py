import telebot
import psycopg2
import json
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

def get_db_connection():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except: return None

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    return markup

# --- 1. TESTNI BOSHLASH MANTIQI (Deep Linking) ---
@bot.message_handler(commands=['start'])
def start(message):
    if len(message.text.split()) > 1:
        param = message.text.split()[1]
        if param.startswith("run_"):
            quiz_id = param.split("_")[1]
            return start_quiz_session(message, quiz_id)
    
    bot.send_message(message.chat.id, "🎯 Quiz Bot faol!", reply_markup=main_menu())

def start_quiz_session(message, quiz_id):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (quiz_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if row:
            bot.send_message(message.chat.id, f"🎬 **{row[0]}** testi boshlanmoqda...\n\n(Bu yerda savollarni chiqarish mantiqi bo'ladi)")
        else:
            bot.send_message(message.chat.id, "❌ Test topilmadi.")

# --- 2. MENING TESTLARIM VA TUGMALAR ---
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
            q_id, title = r[0], r[1]
            q_count = len(json.loads(r[2]))
            msg = f"🎲 **“{title}”** testi\n🖋 {q_count} ta savol"
            
            # Tugmalarni sozlash
            markup = types.InlineKeyboardMarkup()
            bot_username = bot.get_me().username
            
            # Shaxsiyda boshlash
            markup.row(types.InlineKeyboardButton("🚀 Shaxsiyda boshlash", url=f"https://t.me/{bot_username}?start=run_{q_id}"))
            # Guruhga ulashish
            markup.row(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot_username}?startgroup=run_{q_id}"))
            # Inline ulashish
            markup.row(types.InlineKeyboardButton("🔗 Testni ulashish (Inline)", switch_inline_query_current_chat=f"share_{q_id}"))
            # O'chirish (Callback)
            markup.row(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}"))
            
            bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- 3. O'CHIRISH TUGMASI UCHUN CALLBACK ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def delete_callback(call):
    q_id = call.data.split("_")[1]
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM quizzes WHERE id = %s AND user_id = %s', (q_id, call.from_user.id))
        conn.commit(); cur.close(); conn.close()
        bot.answer_callback_query(call.id, "✅ Test muvaffaqiyatli o'chirildi")
        bot.delete_message(call.message.chat.id, call.message.message_id)

# --- 4. INLINE SO'ROVLARNI QAYTA ISHLASH ---
@bot.inline_handler(lambda query: query.query.startswith("share_"))
def inline_handler(query):
    try:
        q_id = query.query.split("_")[1]
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
        row = cur.fetchone(); cur.close(); conn.close()
        
        if row:
            title = row[0]
            q_count = len(json.loads(row[1]))
            result = types.InlineQueryResultArticle(
                id=q_id,
                title=f"🎲 {title}",
                description=f"Savollar soni: {q_count} ta",
                input_message_content=types.InputTextMessageContent(
                    message_text=f"🎲 **“{title}” testi**\n\nBoshlash uchun tugmani bosing 👇",
                    parse_mode="Markdown"
                ),
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🚀 Testni boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}")
                )
            )
            bot.answer_inline_query(query.id, [result], cache_time=1)
    except: pass

# --- 5. TEST YARATISH (ADMIN) ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'step': 'name', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, save_name)

def save_name(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['name'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: {message.text}\nEndi savollarni namunadagidek yuboring.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish"))

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid = message.from_user.id
    if message.text == "📊 Statistika":
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM quizzes'); count = cur.fetchone()[0]
        cur.close(); conn.close()
        return bot.send_message(message.chat.id, f"🚀 Jami testlar: {count}")
    
    if uid == ADMIN_ID and uid in user_session:
        if message.text == "🏁 Saqlash":
            # Saqlash mantiqi (avvalgi koddagidek)
            bot.send_message(message.chat.id, "🎉 Saqlandi!", reply_markup=main_menu())
            del user_session[uid]
        elif message.text == "❌ Bekor qilish":
            del user_session[uid]
            bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=main_menu())

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
