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
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a.ohio-postgres.render.com/quizdb_wgm2'

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

# --- 1. START VA INLINE ---
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    if uid in user_session: del user_session[uid]
    
    if len(message.text.split()) > 1:
        param = message.text.split()[1]
        if param.startswith("run_"):
            return bot.send_message(message.chat.id, "🎬 Testni boshlash uchun dasturchi mantiqni ulashi kutilmoqda...")

    bot.send_message(message.chat.id, "🎯 Quiz Bot faol!", reply_markup=main_menu())

@bot.inline_handler(lambda query: query.query.startswith("share_"))
def inline_handler(query):
    try:
        q_id = query.query.split("_")[1]
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
        row = cur.fetchone(); cur.close(); conn.close()
        if row:
            title = row[0]
            result = types.InlineQueryResultArticle(
                id=q_id, title=f"🎲 {title}",
                input_message_content=types.InputTextMessageContent(f"🎲 **“{title}” testi**\n\nBoshlash uchun bosing 👇", parse_mode="Markdown"),
                reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚀 Boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}"))
            )
            bot.answer_inline_query(query.id, [result], cache_time=1)
    except: pass

# --- 2. MENING TESTLARIM ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT id, title, quiz_data FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    if not rows:
        return bot.send_message(message.chat.id, "📭 Testlar yo'q.")
    for r in rows:
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("🚀 Shaxsiy", url=f"https://t.me/{bot.get_me().username}?start=run_{r[0]}"))
        markup.row(types.InlineKeyboardButton("🔗 Ulashish", switch_inline_query=f"share_{r[0]}"))
        markup.row(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{r[0]}"))
        bot.send_message(message.chat.id, f"🎲 **{r[1]}**\n({len(json.loads(r[2]))} ta savol)", reply_markup=markup, parse_mode="Markdown")

# --- 3. TEST YARATISH (ENG MUHIM QISM) ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'step': 'name', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.reply_to(message, "⛔️ Faqat admin yaratishi mumkin!")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid = message.from_user.id
    
    if message.text == "📊 Statistika":
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM quizzes'); count = cur.fetchone()[0]
        cur.close(); conn.close()
        return bot.send_message(message.chat.id, f"🚀 Jami testlar: {count}")

    if uid in user_session:
        step = user_session[uid].get('step')
        
        # Fan nomini olish
        if step == 'name':
            user_session[uid]['name'] = message.text
            user_session[uid]['step'] = 'questions'
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish")
            bot.send_message(message.chat.id, f"✅ Fan: {message.text}\nEndi savollarni yuboring. To'g'ri javob oxiriga + qo'ying.", reply_markup=markup)
            return

        # Saqlash
        if message.text == "🏁 Saqlash":
            if not user_session[uid]['questions']:
                return bot.send_message(message.chat.id, "⚠️ Savol yubormadingiz!")
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', 
                        (uid, user_session[uid]['name'], json.dumps(user_session[uid]['questions'])))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(message.chat.id, "🎉 Test saqlandi!", reply_markup=main_menu())
            del user_session[uid]
            return

        # Bekor qilish
        if message.text == "❌ Bekor qilish":
            del user_session[uid]
            bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=main_menu())
            return

        # Savollarni qabul qilish (Parser)
        if step == 'questions':
            raw_text = message.text.strip()
            # Savollarni bloklarga bo'lish
            blocks = re.split(r'\n\s*\n', raw_text)
            for block in blocks:
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if len(lines) >= 3: # Savol + kamida 2ta javob
                    user_session[uid]['questions'].append({'q': lines[0], 'o': lines[1:], 'c': 0})
            
            bot.send_message(message.chat.id, f"📥 {len(user_session[uid]['questions'])} ta savol tayyor.\nYana yuboring yoki 🏁 Saqlashni bosing.")

# --- 4. CALLBACKS ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def del_callback(call):
    q_id = call.data.split("_")[1]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('DELETE FROM quizzes WHERE id = %s AND user_id = %s', (q_id, call.from_user.id))
    conn.commit(); cur.close(); conn.close()
    bot.delete_message(call.message.chat.id, call.message.message_id)

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    Thread(target=run_flask).start()
    bot.polling(none_stop=True)
