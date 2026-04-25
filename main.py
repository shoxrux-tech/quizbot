import telebot
import psycopg2
import json
import re
import time
from telebot import types
from flask import Flask
from threading import Thread

# --- KONFIGURATSIYA ---
TOKEN = '8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs'
ADMIN_ID = 5842665369 
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# Foydalanuvchi seanslari va natijalarni saqlash
user_session = {}
active_quizzes = {} # {chat_id: {scores: {}, start_time: t, total: n}}

@app.route('/')
def home(): return "Bot ishlamoqda!"

def get_db_conn():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=5)
    except: return None

# --- ASOSIY BUYRUQLAR ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    # Agar guruhga yoki shaxsiyga testni boshlash havolasi bilan kirilsa
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        return start_quiz_engine(message.chat.id, quiz_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    bot.send_message(message.chat.id, "🎯 **Quiz Botga xush kelibsiz!**\n\nTest yaratish yoki mavjudlarini ko'rish uchun menyudan foydalaning.", 
                     reply_markup=markup, parse_mode="Markdown")

# --- TESTNI BOSHQARISH MANTIQI (ENGINE) ---
def start_quiz_engine(chat_id, quiz_id):
    conn = get_db_conn(); cur = conn.cursor()
    cur.execute('SELECT title, quiz_data, time_limit FROM quizzes WHERE id = %s', (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    if not row:
        return bot.send_message(chat_id, "❌ Test topilmadi.")

    title, questions_json, t_limit = row[0], json.loads(row[1]), row[2] or 15
    active_quizzes[chat_id] = {"scores": {}, "start_time": time.time(), "total": len(questions_json)}

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**\n\n📊 Savollar: {len(questions_json)} ta\n⏱ Vaqt: {t_limit} soniya\n\nTayyor turing, 3 soniyadan so'ng boshlanadi...", parse_mode="Markdown")
    time.sleep(3)

    for i, q in enumerate(questions_json):
        options = []
        correct_id = 0
        for idx, opt in enumerate(q['o']):
            clean_opt = opt.replace('+', '').strip()
            options.append(clean_opt)
            if '+' in opt: correct_id = idx
        
        # Telegram so'rovnomasini yuborish
        poll = bot.send_poll(
            chat_id=chat_id,
            question=f"❓ {i+1}/{len(questions_json)}: {q['q']}",
            options=options,
            type='quiz',
            correct_option_id=correct_id,
            is_anonymous=False,
            open_period=t_limit # Vaqt tugashi bilan variantlar bloklanadi
        )
        # Savol vaqti + 1 soniya kutish
        time.sleep(t_limit + 1)

    # Test tugagach natijalarni chiqarish
    show_results(chat_id, title)

def show_results(chat_id, title):
    if chat_id not in active_quizzes: return
    data = active_quizzes[chat_id]
    sorted_res = sorted(data["scores"].items(), key=lambda x: x[1]['score'], reverse=True)

    text = f"🏁 **“{title}” testi yakunlandi!**\n\n*{data['total']} ta savolga javob berildi*\n\n📊 **Natijalar:**\n"
    icons = ["🥇", "🥈", "🥉", "👤", "👤"]
    
    if not sorted_res:
        text += "\nHech kim qatnashmadi. 🤷‍♂️"
    else:
        for i, (u_id, info) in enumerate(sorted_res[:5]):
            icon = icons[i] if i < 5 else "👤"
            dur = int(time.time() - data["start_time"])
            m, s = divmod(dur, 60)
            time_str = f"({m} daqiqa {s} soniya)" if m > 0 else f"({s} soniya)"
            text += f"\n{icon} {info['name']} — **{info['score']} ta** {time_str}"

    text += "\n\n🏆 G'oliblarni tabriklaymiz!"
    bot.send_message(chat_id, text, parse_mode="Markdown")
    del active_quizzes[chat_id]

# --- JAVOBLARNI TUTIB OLISH ---
@bot.poll_answer_handler()
def handle_poll_answer(answer):
    # Chat ID ni poll orqali aniqlash
    for c_id in active_quizzes:
        # Foydalanuvchi ballini oshirish (faqat to'g'ri topsa Telegram poll_answer yuboradi)
        if answer.user.id not in active_quizzes[c_id]["scores"]:
            active_quizzes[c_id]["scores"][answer.user.id] = {"name": answer.user.first_name, "score": 0}
        active_quizzes[c_id]["scores"][answer.user.id]["score"] += 1

# --- TEST YARATISH VA VAQTNI TANLASH ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(message):
    user_session[message.from_user.id] = {'step': 'name', 'questions': []}
    bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_steps(message):
    uid = message.from_user.id
    if uid not in user_session: return

    step = user_session[uid]['step']

    if step == 'name':
        user_session[uid]['name'] = message.text
        user_session[uid]['step'] = 'time'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("10", "15", "20", "30", "60")
        bot.send_message(message.chat.id, "⏱ **Har bir savol uchun vaqtni tanlang (soniya):**", reply_markup=markup)
    
    elif step == 'time':
        user_session[uid]['time'] = int(message.text) if message.text.isdigit() else 15
        user_session[uid]['step'] = 'questions'
        bot.send_message(message.chat.id, "✅ Vaqt saqlandi. Endi savollarni namunadagidek yuboring (+ bilan).", reply_markup=types.ReplyKeyboardRemove())

    elif step == 'questions':
        if "Saqlash" in message.text:
            s = user_session[uid]
            conn = get_db_conn(); cur = conn.cursor()
            cur.execute('INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s)', 
                        (uid, s['name'], json.dumps(s['questions']), s['time']))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(message.chat.id, "🎉 Test saqlandi!", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📂 Mening testlarim"))
            del user_session[uid]; return

        blocks = re.split(r'\n\s*\n', message.text.strip())
        for b in blocks:
            lines = [l.strip() for l in b.split('\n') if l.strip()]
            if len(lines) >= 3:
                user_session[uid]['questions'].append({'q': lines[0], 'o': lines[1:]})
        
        bot.send_message(message.chat.id, f"📥 {len(user_session[uid]['questions'])} ta savol tayyor. Saqlash uchun pastdagi tugmani bosing.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

# --- TESTLAR RO'YXATI VA ULASHISH ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_conn(); cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    if not rows: return bot.send_message(message.chat.id, "📭 Sizda hali testlar yo'q.")

    for r in rows:
        markup = types.InlineKeyboardMarkup()
        bot_user = bot.get_me().username
        markup.row(types.InlineKeyboardButton("🚀 Shaxsiydada boshlash", url=f"https://t.me/{bot_user}?start=run_{r[0]}"))
        markup.row(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot_user}?startgroup=run_{r[0]}"))
        markup.row(types.InlineKeyboardButton("🔗 Testni ulashish (Inline)", switch_inline_query=f"share_{r[0]}"))
        bot.send_message(message.chat.id, f"🎲 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")

@bot.inline_handler(lambda query: query.query.startswith("share_"))
def inline_share(query):
    q_id = query.query.split("_")[1]
    conn = get_db_conn(); cur = conn.cursor()
    cur.execute('SELECT title FROM quizzes WHERE id = %s', (q_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    
    if row:
        res = types.InlineQueryResultArticle(
            id=q_id, title=f"🎲 {row[0]}",
            input_message_content=types.InputTextMessageContent(f"🏁 **“{row[0]}” testi tayyor!**\n\nBoshlash uchun pastdagi tugmani bosing 👇"),
            reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚀 Testni boshlash", url=f"https://t.me/{bot.get_me().username}?start=run_{q_id}"))
        )
        bot.answer_inline_query(query.id, [res])

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
