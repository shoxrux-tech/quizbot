import os
import telebot
import psycopg2
import json
import time
import threading
from telebot import types

# --- SOZLAMALAR ---
TOKEN = "8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs"
DATABASE_URL = os.getenv("postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a.ohio-postgres.render.com/quizdb_wgm2")
bot = telebot.TeleBot(TOKEN)

def get_db():
    return psycopg2.connect(DATABASE_URL)

# --- BAZANI AVTOMATIK TO'G'IRLASH (Terminal kerak emas!) ---
def auto_fix_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        # Jadval yo'q bo'lsa yaratadi, bor bo'lsa vaqt ustunini qo'shadi
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                title TEXT,
                quiz_data JSONB,
                time_limit INTEGER DEFAULT 15
            );
            ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS time_limit INTEGER DEFAULT 15;
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Baza muvaffaqiyatli sozlandi!")
    except Exception as e:
        print(f"❌ Baza xatosi: {e}")

# --- INLINE QUERY (Guruhga ulashish) ---
@bot.inline_handler(lambda query: query.query.startswith("share_"))
def share_quiz(inline_query):
    try:
        q_id = inline_query.query.split("_")[1]
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT title FROM quizzes WHERE id = %s', (q_id,))
        res = cur.fetchone()
        cur.close(); conn.close()
        
        if res:
            r = types.InlineQueryResultArticle(
                id=q_id,
                title=f"📝 Test: {res[0]}",
                input_message_content=types.InputTextMessageContent(
                    f"📚 **Yangi test: {res[0]}**\n\nTestni ishlash uchun pastdagi tugmani bosing 👇",
                    parse_mode="Markdown"
                ),
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🚀 Testni boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}")
                )
            )
            bot.answer_inline_query(inline_query.id, [r], cache_time=1)
    except: pass

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('run_'):
        q_id = args[1].split('_')[1]
        return show_timer(message.chat.id, q_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📚 Yangi test yaratish", "📂 Mening testlarim")
    bot.send_message(message.chat.id, "🎯 Quiz Bot professional tizimi tayyor!", reply_markup=markup)

def show_timer(chat_id, q_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("15 sek", callback_data=f"t_15_{q_id}"),
               types.InlineKeyboardButton("30 sek", callback_data=f"t_30_{q_id}"))
    bot.send_message(chat_id, "⏱ Savollar vaqtini tanlang:", reply_markup=markup)

# --- TESTLARNI CHIQARISH ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def list_tests(message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    
    if not rows:
        return bot.send_message(message.chat.id, "📭 Testlar yo'q.")
        
    for r in rows:
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{r[0]}"))
        markup.add(types.InlineKeyboardButton("📤 Guruhga ulashish", switch_inline_query=f"share_{r[0]}"))
        bot.send_message(message.chat.id, f"📂 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")

# --- TEST MANTIQI ---
def run_quiz(chat_id, q_id, interval):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
    res = cur.fetchone()
    cur.close(); conn.close()
    
    if res:
        title, data = res[0], json.loads(res[1]) if isinstance(res[1], str) else res[1]
        bot.send_message(chat_id, f"🏁 **{title}** boshlandi!")
        for idx, i in enumerate(data, 1):
            try:
                bot.send_poll(chat_id, f"[{idx}/{len(data)}] {i['q']}", i['o'], 
                              type='quiz', correct_option_id=i['c'], is_anonymous=False, 
                              open_period=interval)
                time.sleep(interval + 2)
            except: break
        bot.send_message(chat_id, "✅ Test yakunlandi!")

@bot.callback_query_handler(func=lambda call: True)
def calls(call):
    d = call.data.split('_')
    if d[0] == 't':
        bot.delete_message(call.message.chat.id, call.message.message_id)
        threading.Thread(target=run_quiz, args=(call.message.chat.id, d[2], int(d[1]))).start()
    elif d[0] == 'run':
        show_timer(call.message.chat.id, d[1])

# --- BOTNI ISHGA TUSHIRISH ---
if __name__ == '__main__':
    auto_fix_db() # Bazani o'zi to'g'irlaydi
    print("Bot yoqildi...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
