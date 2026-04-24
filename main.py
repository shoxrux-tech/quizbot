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
def home(): return "Bot 24/7 faol!" # Cron-job uchun kerak

# --- BAZA BILAN ISHLASH ---
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
                else: opts.append(opt)
            parsed_questions.append({'q': q_text, 'o': opts, 'c': corr})
    return parsed_questions

# --- ASOSIY MENYU ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    return markup

# --- HANDLERLAR ---
@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.from_user.id)
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('run_'):
        q_id = int(args[1].split('_')[1])
        threading.Thread(target=run_quiz_logic, args=(message.chat.id, q_id, 15)).start()
        return
    bot.send_message(message.chat.id, "🎯 Quiz Bot faol!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_new(message):
    uid = message.from_user.id
    if uid == ADMIN_ID: # ADMIN LOCK
        user_session[uid] = {'subject': '', 'questions': []}
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
            bot.send_message(message.chat.id, "O'chirildi.", reply_markup=main_menu())
        else:
            new_qs = parse_multiline_questions(message.text) #
            if new_qs:
                user_session[uid]['questions'].extend(new_qs)
                bot.send_message(message.chat.id, f"📥 {len(new_qs)} ta savol olindi.")

# --- INLINE MODE ---
@bot.inline_handler(lambda query: query.query.startswith("quiz_"))
def inline_share(inline_query):
    try:
        q_id = int(inline_query.query.split("_")[1])
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(); cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
            res = cur.fetchone(); cur.close(); conn.close()
            if res:
                qs_count = len(json.loads(res[1]))
                r = types.InlineQueryResultArticle(
                    id=str(q_id), title=f"🎲 {res[0]}", description=f"{qs_count} ta savol",
                    input_message_content=types.InputTextMessageContent(f"🎲 **“{res[0]}” testi**\n\nBoshlash uchun bosing 👇"),
                    reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚀 Boshlash", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}"))
                )
                bot.answer_inline_query(inline_query.id, [r], cache_time=1)
    except: pass

# --- TO'XTOVSIZ ISHLASHNI TA'MINLASH ---
if __name__ == '__main__':
    init_db()
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    while True: # Eng muhim qism: Loop to'xtab qolsa qayta ulaydi
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Ulanish uzildi: {e}")
            time.sleep(5)
