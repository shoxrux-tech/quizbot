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

@app.route('/')
def home(): return "Bot faol!"

def get_db_connection():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except: return None

# --- 1. START VA TESTNI BOSHLASH MANTIQI ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    
    # Agar start bilan birga test ID kelsa (Guruhda yoki Shaxsiydagi tugma bosilganda)
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        return send_quiz_to_chat(message.chat.id, quiz_id)

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    bot.send_message(message.chat.id, "🎯 Quiz Bot faol! Guruhga qo'shish uchun 'Mening testlarim' bo'limiga o'ting.", reply_markup=markup)

# --- 2. TESTNI CHATGA (GURUHGA) YUBORISH FUNKSIYASI ---
def send_quiz_to_chat(chat_id, quiz_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (quiz_id,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if row:
        title, questions_json = row[0], row[1]
        questions = json.loads(questions_json)
        
        bot.send_message(chat_id, f"🚀 **“{title}” testi boshlanmoqda...**\nJami: {len(questions)} ta savol.", parse_mode="Markdown")
        
        # Har bir savolni Telegram Poll (so'rovnoma) ko'rinishida yuborish
        for q in questions:
            # To'g'ri javob indeksini aniqlash (+ belgisi orqali)
            options = []
            correct_id = 0
            for i, opt in enumerate(q['o']):
                clean_opt = opt.replace('+', '').strip()
                options.append(clean_opt)
                if '+' in opt:
                    correct_id = i
            
            # Guruhda so'rovnoma yuborish
            bot.send_poll(
                chat_id=chat_id,
                question=q['q'],
                options=options,
                type='quiz',
                correct_option_id=correct_id,
                is_anonymous=False # Kim qanday javob berganini ko'rish uchun
            )
    else:
        bot.send_message(chat_id, "❌ Test topilmadi!")

# --- 3. TESTLARNI BOSHLASH TUGMALARI ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT id, title, quiz_data FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    if not rows:
        return bot.send_message(message.chat.id, "📭 Testlar yo'q.")
        
    for r in rows:
        markup = types.InlineKeyboardMarkup()
        # Bu tugma guruhni tanlash va botni u yerga yuborish imkonini beradi
        start_url = f"https://t.me/{bot.get_me().username}?startgroup=run_{r[0]}"
        markup.row(types.InlineKeyboardButton("🚀 Guruhda boshlash", url=start_url))
        markup.row(types.InlineKeyboardButton("🔗 Ulashish", switch_inline_query=f"share_{r[0]}"))
        markup.row(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{r[0]}"))
        bot.send_message(message.chat.id, f"🎲 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")

# --- TEST YARATISH VA BOSHQA FUNKSIYALAR (OLDINGIDEK) ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, get_quiz_name)
    else:
        bot.reply_to(message, "⛔️ Faqat admin yaratishi mumkin!")

def get_quiz_name(message):
    quiz_name = message.text
    bot.send_message(message.chat.id, f"✅ Fan: {quiz_name}\n\nEndi savollarni yuboring. To'g'ri javob oxiriga + qo'ying.")
    bot.register_next_step_handler(message, lambda msg: save_questions(msg, quiz_name))

def save_questions(message, name):
    # Savollarni parser qilish
    questions = []
    blocks = re.split(r'\n\s*\n', message.text.strip())
    for block in blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) >= 3:
            questions.append({'q': lines[0], 'o': lines[1:]})
    
    if questions:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', 
                    (message.from_user.id, name, json.dumps(questions)))
        conn.commit(); cur.close(); conn.close()
        bot.send_message(message.chat.id, f"🎉 {len(questions)} ta savol saqlandi!", reply_markup=main_menu_markup())
    else:
        bot.send_message(message.chat.id, "❌ Xato! Savollar formatini tekshiring.", reply_markup=main_menu_markup())

def main_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def del_callback(call):
    q_id = call.data.split("_")[1]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('DELETE FROM quizzes WHERE id = %s', (q_id,))
    conn.commit(); cur.close(); conn.close()
    bot.answer_callback_query(call.id, "O'chirildi")
    bot.delete_message(call.message.chat.id, call.message.message_id)

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
