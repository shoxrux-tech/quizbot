import telebot
import psycopg2
import json
import re
import time
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
quiz_active_sessions = {} # {chat_id: {users: {user_id: score}, start_time: t}}

@app.route('/')
def home(): return "Bot faol!"

def get_db_connection():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except: return None

# --- 1. ASOSIY START VA BOSHLASH MANTIQLARI ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    # Guruhda yoki shaxsiydagi "Testni boshlash" tugmasi bosilganda
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        return run_quiz_engine(message.chat.id, quiz_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    bot.send_message(message.chat.id, "🎯 Quiz Bot faol! Test yaratish uchun tugmani bosing.", reply_markup=markup)

# --- 2. TESTNI VAQT VA NATIJALAR BILAN YURITISH ---
def run_quiz_engine(chat_id, quiz_id):
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data, time_limit FROM quizzes WHERE id = %s', (quiz_id,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if row:
        title, questions, t_limit = row[0], json.loads(row[1]), row[2] or 15
        quiz_active_sessions[chat_id] = {"users": {}, "start_time": time.time()}
        
        bot.send_message(chat_id, f"🏁 **“{title}”** testi boshlanmoqda!\n\nSavollar: {len(questions)} ta\n⏱ Vaqt: {t_limit} soniya", parse_mode="Markdown")
        time.sleep(3)

        for i, q in enumerate(questions):
            options = []
            correct_id = 0
            for idx, opt in enumerate(q['o']):
                clean_opt = opt.replace('+', '').strip()
                options.append(clean_opt)
                if '+' in opt: correct_id = idx
            
            # Telegram Quiz Poll (So'rovnoma) yuborish
            bot.send_poll(
                chat_id=chat_id,
                question=f"❓ {i+1}/{len(questions)}: {q['q']}",
                options=options,
                type='quiz',
                correct_option_id=correct_id,
                is_anonymous=False,
                open_period=t_limit
            )
            # Savol vaqti tugashini kutish (Variantlar bloklanadi)
            time.sleep(t_limit + 1)
        
        # Test yakunida natijalarni rasmdagidek chiqarish
        finalize_quiz_results(chat_id, title)
    else:
        bot.send_message(chat_id, "❌ Test topilmadi.")

def finalize_quiz_results(chat_id, title):
    if chat_id not in quiz_active_sessions: return
    
    data = quiz_active_sessions[chat_id]
    sorted_res = sorted(data["users"].items(), key=lambda x: x[1]['score'], reverse=True)
    
    res_text = f"🏁 **“{title}” testi yakunlandi!**\n\n📊 **Natijalar:**\n"
    icons = ["🥇", "🥈", "🥉", "👤", "👤"]
    
    if not sorted_res:
        res_text += "\nHech kim qatnashmadi. 🤷‍♂️"
    else:
        for i, (u_id, u_info) in enumerate(sorted_res[:5]):
            icon = icons[i] if i < 5 else "👤"
            dur = int(time.time() - data["start_time"])
            m, s = divmod(dur, 60)
            time_str = f"({m} daqiqa {s} soniya)" if m > 0 else f"({s} soniya)"
            res_text += f"\n{icon} {u_info['name']} — **{u_info['score']} ta** {time_str}"

    res_text += "\n\n🏆 G'oliblarni tabriklaymiz!"
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    del quiz_active_sessions[chat_id]

# --- 3. JAVOBLARNI TUTIB OLISH ---
@bot.poll_answer_handler()
def poll_answer_handler(answer):
    for c_id in quiz_active_sessions:
        if answer.user.id not in quiz_active_sessions[c_id]["users"]:
            quiz_active_sessions[c_id]["users"][answer.user.id] = {"name": answer.user.first_name, "score": 0}
        
        # To'g'ri javobni hisoblash
        quiz_active_sessions[c_id]["users"][answer.user.id]["score"] += 1

# --- 4. TEST YARATISH VA VAQTNI TANLASH ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz_init(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'step': 'name', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.reply_to(message, "⛔️ Faqat admin yaratishi mumkin!")

@bot.message_handler(func=lambda m: True)
def quiz_creation_steps(message):
    uid = message.from_user.id
    if uid not in user_session: return

    step = user_session[uid]['step']

    if step == 'name':
        user_session[uid]['name'] = message.text
        user_session[uid]['step'] = 'time'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("15", "30", "60", "120")
        bot.send_message(message.chat.id, "⏱ **Har bir savol uchun vaqtni tanlang (soniya):**", reply_markup=markup)
    
    elif step == 'time':
        user_session[uid]['time'] = int(message.text) if message.text.isdigit() else 15
        user_session[uid]['step'] = 'questions'
        bot.send_message(message.chat.id, "✅ Vaqt saqlandi. Endi savollarni yuboring (+ bilan).", reply_markup=types.ReplyKeyboardRemove())

    elif step == 'questions':
        if "🏁 Saqlash" in message.text:
            s = user_session[uid]
            conn = get_db_connection(); cur = conn.cursor()
            cur.execute('INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s)', 
                        (uid, s['name'], json.dumps(s['questions']), s['time']))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(message.chat.id, "🎉 Test saqlandi!", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📂 Mening testlarim"))
            del user_session[uid]
            return

        blocks = re.split(r'\n\s*\n', message.text.strip())
        for b in blocks:
            lines = [l.strip() for l in b.split('\n') if l.strip()]
            if len(lines) >= 3:
                user_session[uid]['questions'].append({'q': lines[0], 'o': lines[1:]})
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash")
        bot.send_message(message.chat.id, f"📥 {len(user_session[uid]['questions'])} ta savol tayyor.", reply_markup=markup)

# --- 5. MENING TESTLARIM VA ULASHISH ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_quizzes(message):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    if not rows: return bot.send_message(message.chat.id, "📭 Testlar yo'q.")

    for r in rows:
        markup = types.InlineKeyboardMarkup()
        bot_u = bot.get_me().username
        markup.row(types.InlineKeyboardButton("🚀 Shaxsiydada boshlash", url=f"https://t.me/{bot_u}?start=run_{r[0]}"))
        markup.row(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot_u}?startgroup=run_{r[0]}"))
        markup.row(types.InlineKeyboardButton("🔗 Testni ulashish (Inline)", switch_inline_query=f"share_{r[0]}"))
        markup.row(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{r[0]}"))
        bot.send_message(message.chat.id, f"🎲 **{r[1]}**", reply_markup=markup)

@bot.inline_handler(lambda query: query.query.startswith("share_"))
def inline_handler(query):
    q_id = query.query.split("_")[1]
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT title FROM quizzes WHERE id = %s', (q_id,))
    title = cur.fetchone()[0]; cur.close(); conn.close()
    
    res = types.InlineQueryResultArticle(
        id=q_id, title=f"🎲 {title}",
        input_message_content=types.InputTextMessageContent(f"🏁 **“{title}” testi tayyor!**\nBoshlash uchun pastdagi tugmani bosing 👇"),
        reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚀 Testni boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}"))
    )
    bot.answer_inline_query(query.id, [res])

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
