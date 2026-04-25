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
def home(): return "Bot 24/7 faol!"

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

# --- 1. MENING TESTLARIM (Rasmdagi barcha tugmalar bilan) ---
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
            
            # Rasmdagi kabi tugmalar iyerarxiyasi
            markup = types.InlineKeyboardMarkup()
            markup.row(types.InlineKeyboardButton("🚀 Shaxsiyda boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}"))
            markup.row(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}"))
            markup.row(types.InlineKeyboardButton("🔗 Testni ulashish (Inline)", switch_inline_query_current_chat=f"share_{q_id}"))
            markup.row(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}"))
            
            bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode="Markdown")

# --- 2. O'CHIRISH VA INLINE FUNKSIYALARI ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def delete_quiz(call):
    q_id = call.data.split("_")[1]
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM quizzes WHERE id = %s AND user_id = %s', (q_id, call.from_user.id))
        conn.commit(); cur.close(); conn.close()
        bot.answer_callback_query(call.id, "✅ Test o'chirildi")
        bot.delete_message(call.message.chat.id, call.message.message_id)

# --- 3. TEST YARATISH (AVTOMATIK PARSER BILAN) ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_create(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'subject': '', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, get_subject)
    else:
        bot.reply_to(message, "⛔️ Faqat admin yaratishi mumkin!")

def get_subject(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: **{message.text}**\nSavollarni yuboring.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish"))

@bot.message_handler(func=lambda m: True)
def global_handler(message):
    uid = message.from_user.id
    
    # Statistika va Yo'riqnoma tugmalarini tekshirish (TUGMALAR ISHLASHI UCHUN)
    if message.text == "📊 Statistika":
        return send_stats(message)
    if message.text == "❓ Yo'riqnoma":
        return bot.send_message(message.chat.id, "Namunadagi kabi savollarni yuboring.")

    # Test yig'ish mantiqi
    if uid == ADMIN_ID and uid in user_session:
        if message.text == "🏁 Saqlash":
            save_quiz(message)
        elif message.text == "❌ Bekor qilish":
            del user_session[uid]
            bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=main_menu())
        else:
            parse_questions(message)

def parse_questions(message):
    uid = message.from_user.id
    raw_blocks = re.split(r'\n\s*\n', message.text.strip())
    count = 0
    for block in raw_blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) >= 3:
            user_session[uid]['questions'].append({'q': lines[0], 'o': lines[1:], 'c': 0})
            count += 1
    bot.send_message(message.chat.id, f"📥 {count} ta savol olindi. Jami: {len(user_session[uid]['questions'])}")

def save_quiz(message):
    uid = message.from_user.id
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

def send_stats(message):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM quizzes'); q = cur.fetchone()[0]
        cur.close(); conn.close()
        bot.send_message(message.chat.id, f"🚀 Jami testlar: {q}")

# --- BOTNI UYQUTDAN SAQLASH ---
if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
