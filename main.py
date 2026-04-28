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

# --- INLINE QUERY (Guruhga ulashish uchun) ---
@bot.inline_handler(lambda query: query.query.startswith("share_"))
def share_quiz(inline_query):
    try:
        q_id = inline_query.query.split("_")[1]
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT title FROM quizzes WHERE id = %s', (q_id,))
        res = cur.fetchone()
        cur.close()
        conn.close()

        if res:
            title = res[0]
            # Guruhga yuboriladigan xabar shakli
            r = types.InlineQueryResultArticle(
                id=q_id,
                title=f"📝 Test: {title}",
                description="Guruhga yuborish uchun ustiga bosing",
                input_message_content=types.InputTextMessageContent(
                    f"📚 **Yangi test: {title}**\n\nTestni ishlash uchun quyidagi tugmani bosing 👇",
                    parse_mode="Markdown"
                ),
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🚀 Testni boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}")
                )
            )
            bot.answer_inline_query(inline_query.id, [r])
    except Exception as e:
        print(f"Inline xato: {e}")

# --- START KOMANDASI ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    # Agar foydalanuvchi guruhdagi link orqali kelsa
    if len(args) > 1 and args[1].startswith('run_'):
        q_id = args[1].split('_')[1]
        show_time_options(message.chat.id, q_id)
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📚 Yangi test yaratish", "📂 Mening testlarim")
    bot.send_message(message.chat.id, "🎯 Quiz Bot professional tizimiga xush kelibsiz!", reply_markup=markup)

def show_time_options(chat_id, q_id):
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("15 sek", callback_data=f"t_15_{q_id}"),
               types.InlineKeyboardButton("30 sek", callback_data=f"t_30_{q_id}"))
    bot.send_message(chat_id, "⏱ Savollar vaqtini tanlang:", reply_markup=markup)

# --- TESTNI BOSHLASH ---
def run_quiz_logic(chat_id, q_id, interval):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()

    if res:
        title, data = res[0], json.loads(res[1]) if isinstance(res[1], str) else res[1]
        bot.send_message(chat_id, f"🏁 **{title}** boshlandi!", parse_mode="Markdown")
        
        for idx, i in enumerate(data, 1):
            try:
                bot.send_poll(
                    chat_id, 
                    f"[{idx}/{len(data)}] {i['q']}", 
                    i['o'], 
                    type='quiz', 
                    correct_option_id=i['c'], 
                    is_anonymous=False,
                    open_period=interval # VAQT TUGAGACH YOPILADI
                )
                time.sleep(interval + 2)
            except: break
        
        # Tugagach ulashish tugmasi
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Do'stlarga yuborish", switch_inline_query=f"share_{q_id}"))
        bot.send_message(chat_id, "✅ Test tugadi. Uni ulashishingiz mumkin:", reply_markup=markup)

# --- CALLBACKLAR ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data.split('_')
    if data[0] == 'run':
        show_time_options(call.message.chat.id, data[1])
    elif data[0] == 't':
        bot.delete_message(call.message.chat.id, call.message.message_id)
        threading.Thread(target=run_quiz_logic, args=(call.message.chat.id, data[2], int(data[1]))).start()

# --- MENING TESTLARIM ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        bot.send_message(message.chat.id, "Sizda testlar yo'q.")
        return

    for r in rows:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{r[0]}"))
        markup.add(types.InlineKeyboardButton("📤 Chat/Guruhga ulashish", switch_inline_query=f"share_{r[0]}"))
        bot.send_message(message.chat.id, f"📂 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")

bot.infinity_polling()
