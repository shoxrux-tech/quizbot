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

# --- 1. START BUYRUG'I ---
@bot.message_handler(commands=['start'])
def start(message):
    user_session.pop(message.from_user.id, None) # Sessiyani tozalash
    bot.send_message(message.chat.id, "🎯 Quiz Bot faol!", reply_markup=main_menu())

# --- 2. INLINE HANDLER (ULASHISH UCHUN) ---
@bot.inline_handler(lambda query: query.query.startswith("share_"))
def inline_handler(query):
    try:
        q_id = query.query.split("_")[1]
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
        row = cur.fetchone(); cur.close(); conn.close()
        if row:
            title, q_count = row[0], len(json.loads(row[1]))
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

# --- 3. MENING TESTLARIM (CHATLAR RO'YXATI CHIQADIGAN QILINDI) ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT id, title, quiz_data FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    if not rows:
        bot.send_message(message.chat.id, "📭 Sizda hali testlar yo'q.")
        return
        
    for r in rows:
        q_id, title = r[0], r[1]
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("🚀 Shaxsiyda boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}"))
        markup.row(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}"))
        # switch_inline_query (bo'sh qiymat bilan) hamma chatlarni chiqaradi
        markup.row(types.InlineKeyboardButton("🔗 Testni ulashish (Chatni tanlash)", switch_inline_query=f"share_{q_id}"))
        markup.row(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}"))
        bot.send_message(message.chat.id, f"🎲 **“{title}”**", reply_markup=markup, parse_mode="Markdown")

# --- 4. TEST YARATISH (SAVOL QABUL QILISHI ANIQ QILINDI) ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'step': 'get_name', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.reply_to(message, "⛔️ Faqat admin yaratishi mumkin!")

@bot.message_handler(func=lambda m: True)
def handle_all_logic(message):
    uid = message.from_user.id
    
    # 1. Statistika
    if message.text == "📊 Statistika":
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM quizzes'); count = cur.fetchone()[0]
        cur.close(); conn.close()
        return bot.send_message(message.chat.id, f"🚀 Jami testlar: {count}")

    # 2. Test yaratish jarayoni
    if uid in user_session:
        state = user_session[uid]
        
        if state['step'] == 'get_name':
            user_session[uid]['name'] = message.text
            user_session[uid]['step'] = 'get_questions'
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish")
            bot.send_message(message.chat.id, f"✅ Fan: {message.text}\nEndi savollarni yuboring. To'g'ri javob oxiriga + qo'ying.", reply_markup=markup)
            return

        if message.text == "🏁 Saqlash":
            if not user_session[uid]['questions']:
                return bot.send_message(message.chat.id, "⚠️ Hech bo'lmasa 1 ta savol yuboring!")
            
            # Bazaga yozish
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', 
                        (uid, state['name'], json.dumps(state['questions'])))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(message.chat.id, "🎉 Test saqlandi!", reply_markup=main_menu())
            del user_session[uid]
            return

        if message.text == "❌ Bekor qilish":
            del user_session[uid]
            bot.send_message(message.chat.id, "Bekor qilindi.", reply_markup=main_menu())
            return

        # Savollarni yig'ish (Parser)
        blocks = re.split(r'\n\s*\n', message.text.strip())
        added_count = 0
        for block in blocks:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) >= 3:
                user_session[uid]['questions'].append({'q': lines[0], 'o': lines[1:], 'c': 0})
                added_count += 1
        
        if added_count > 0:
            bot.send_message(message.chat.id, f"📥 {added_count} ta savol olindi. Jami: {len(user_session[uid]['questions'])} ta.\nYana yuboring yoki 🏁 Saqlashni bosing.")

# --- 5. O'CHIRISH CALLBACK ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def del_call(call):
    q_id = call.data.split("_")[1]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('DELETE FROM quizzes WHERE id = %s AND user_id = %s', (q_id, call.from_user.id))
    conn.commit(); cur.close(); conn.close()
    bot.delete_message(call.message.chat.id, call.message.message_id)

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
