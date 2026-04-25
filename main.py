import telebot
import psycopg2
import json
import re
import time
from telebot import types
from flask import Flask
from threading import Thread

# --- SOZLAMALAR (Buni o'zingizniki bilan tekshiring) ---
TOKEN = '8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs'
ADMIN_ID = 5842665369 
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a.ohio-postgres.render.com/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# Vaqtinchalik ma'lumotlar ombori
user_session = {}
active_quizzes = {} # {chat_id: {scores: {}, start_time: t, total: n}}

@app.route('/')
def home(): return "Bot 100% Faol!"

def get_db_conn():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=5)
    except: return None

# --- 1. START VA TESTNI ISHGA TUSHIRISH ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    # Testni boshlash tugmasi bosilganda (start=run_ID)
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        return start_quiz_logic(message.chat.id, quiz_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    bot.send_message(message.chat.id, "🎯 **Quiz Bot professional tizimiga xush kelibsiz!**", 
                     reply_markup=markup, parse_mode="Markdown")

# --- 2. TESTNI O'TKAZISH MANTIQI (ENGINE) ---
def start_quiz_logic(chat_id, quiz_id):
    conn = get_db_conn(); cur = conn.cursor()
    cur.execute('SELECT title, quiz_data, time_limit FROM quizzes WHERE id = %s', (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    if not row:
        return bot.send_message(chat_id, "❌ Test topilmadi.")

    title, questions, t_limit = row[0], json.loads(row[1]), row[2] or 15
    active_quizzes[chat_id] = {"scores": {}, "start_time": time.time(), "total": len(questions)}

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**\n\n⏱ Har bir savolga: {t_limit} soniya\n❓ Jami savollar: {len(questions)} ta", parse_mode="Markdown")
    time.sleep(3)

    for i, q in enumerate(questions):
        options = []
        correct_id = 0
        for idx, opt in enumerate(q['o']):
            clean_opt = opt.replace('+', '').strip()
            options.append(clean_opt)
            if '+' in opt: correct_id = idx
        
        # Telegram Quiz Poll yuborish
        bot.send_poll(
            chat_id=chat_id,
            question=f"{i+1}/{len(questions)}: {q['q']}",
            options=options,
            type='quiz',
            correct_option_id=correct_id,
            is_anonymous=False,
            open_period=t_limit # Vaqt tugagach variantlar avtomatik yopiladi
        )
        time.sleep(t_limit + 1) # Keyingi savolgacha kutish

    # Yakuniy natijalar jadvali
    finalize_quiz(chat_id, title)

def finalize_quiz(chat_id, title):
    if chat_id not in active_quizzes: return
    data = active_quizzes[chat_id]
    sorted_res = sorted(data["scores"].items(), key=lambda x: x[1]['score'], reverse=True)

    res_text = f"🏁 **“{title}” testi yakunlandi!**\n\n📊 **Natijalar:**\n"
    icons = ["🥇", "🥈", "🥉", "👤", "👤"]
    
    if not sorted_res:
        res_text += "\nHech kim qatnashmadi. 🤷‍♂️"
    else:
        for i, (u_id, info) in enumerate(sorted_res[:5]):
            icon = icons[i] if i < 5 else "👤"
            dur = int(time.time() - data["start_time"])
            m, s = divmod(dur, 60)
            text_time = f"({m}m {s}s)" if m > 0 else f"({s}s)"
            res_text += f"\n{icon} {info['name']} — **{info['score']} ta** {text_time}"

    res_text += "\n\n🏆 G'oliblarni tabriklaymiz!"
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    del active_quizzes[chat_id]

@bot.poll_answer_handler()
def poll_handler(answer):
    for c_id in active_quizzes:
        if answer.user.id not in active_quizzes[c_id]["scores"]:
            active_quizzes[c_id]["scores"][answer.user.id] = {"name": answer.user.first_name, "score": 0}
        active_quizzes[c_id]["scores"][answer.user.id]["score"] += 1

# --- 3. FAQAT ADMIN TEST YARATA OLISHI ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz_start(message):
    if message.from_user.id == ADMIN_ID:
        user_session[message.from_user.id] = {'step': 'name', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
    else:
        bot.send_message(message.chat.id, "⛔️ **Kechirasiz, faqat admin test yarata oladi!**")

@bot.message_handler(func=lambda m: True)
def quiz_steps(message):
    uid = message.from_user.id
    if uid not in user_session or uid != ADMIN_ID: return

    step = user_session[uid]['step']

    if step == 'name':
        user_session[uid]['name'] = message.text
        user_session[uid]['step'] = 'time'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("15", "30", "60")
        bot.send_message(message.chat.id, "⏱ **Vaqtni tanlang (soniya):**", reply_markup=markup)
    
    elif step == 'time':
        user_session[uid]['time'] = int(message.text) if message.text.isdigit() else 15
        user_session[uid]['step'] = 'questions'
        bot.send_message(message.chat.id, "✅ Tayyor. Endi savollarni yuboring (+ bilan).", reply_markup=types.ReplyKeyboardRemove())

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
        
        bot.send_message(message.chat.id, f"📥 {len(user_session[uid]['questions'])} ta savol olindi.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

# --- 4. TESTLAR RO'YXATI VA ULASHISH ---
@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_quizzes(message):
    if message.from_user.id != ADMIN_ID: return
    conn = get_db_conn(); cur = conn.cursor()
    cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    for r in rows:
        markup = types.InlineKeyboardMarkup()
        bot_u = bot.get_me().username
        markup.row(types.InlineKeyboardButton("🚀 Testni boshlash", url=f"https://t.me/{bot_u}?start=run_{r[0]}"))
        markup.row(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot_u}?startgroup=run_{r[0]}"))
        bot.send_message(message.chat.id, f"🎲 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")

if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
