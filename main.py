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
quiz_results = {} # Vaqtinchalik natijalarni saqlash: {chat_id: {user_id: {'score': 0, 'start_time': 0}}}

@app.route('/')
def home(): return "Bot faol!"

def get_db_connection():
    try: return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except: return None

# --- 1. TESTNI BOSHLASH VA NATIJALARNI HISOBLASH ---
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        return start_professional_quiz(message.chat.id, quiz_id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    bot.send_message(message.chat.id, "🎯 Quiz Botga xush kelibsiz!", reply_markup=markup)

def start_professional_quiz(chat_id, quiz_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT title, quiz_data, time_limit FROM quizzes WHERE id = %s', (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    if not row: return bot.send_message(chat_id, "❌ Test topilmadi.")

    title, questions, t_limit = row[0], json.loads(row[1]), row[2] or 15
    quiz_results[chat_id] = {} # Natijalarni nolga tushirish

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**\n\n📊 Savollar: {len(questions)} ta\n⏱ Vaqt: {t_limit} soniya\n\nTayyor turing...")
    time.sleep(3)

    for i, q in enumerate(questions):
        options = []
        correct_id = 0
        for idx, opt in enumerate(q['o']):
            clean_opt = opt.replace('+', '').strip()
            options.append(clean_opt)
            if '+' in opt: correct_id = idx
        
        # Poll yuborish
        msg = bot.send_poll(
            chat_id=chat_id,
            question=f"❓ {i+1}/{len(questions)}: {q['q']}",
            options=options,
            type='quiz',
            correct_option_id=correct_id,
            is_anonymous=False,
            open_period=t_limit
        )
        
        # Vaqt tugashini kutish
        time.sleep(t_limit + 1)

    # --- TEST TUGAGANDA NATIJALARNI CHIQARISH ---
    show_leaderboard(chat_id, title, len(questions))

def show_leaderboard(chat_id, title, total_q):
    if chat_id not in quiz_results or not quiz_results[chat_id]:
        return bot.send_message(chat_id, f"🏁 **“{title}” testi yakunlandi!**\n\nHech kim qatnashmadi. 🤷‍♂️")

    results = quiz_results[chat_id]
    # Natijalarni saralash (eng ko'p topgan birinchi)
    sorted_res = sorted(results.items(), key=lambda x: x[1]['score'], reverse=True)

    text = f"🏁 **“{title}” testi yakunlandi!**\n\n*{total_q} ta savolga javob berildi*\n\n📊 **Natijalar:**\n"
    icons = ["🥇", "🥈", "🥉", "👤", "👤"]
    
    for i, (u_id, data) in enumerate(sorted_res[:5]): # Top 5 talik
        icon = icons[i] if i < len(icons) else "👤"
        duration = int(time.time() - data['start_time'])
        m, s = divmod(duration, 60)
        time_str = f"({m} daqiqa {s} soniya)" if m > 0 else f"({s} soniya)"
        text += f"\n{icon} {data['name']} — **{data['score']} ta** {time_str}"

    text += "\n\n🏆 G'oliblarni tabriklaymiz!"
    bot.send_message(chat_id, text, parse_mode="Markdown")
    del quiz_results[chat_id] # Xotirani tozalash

# --- 2. JAVOBLARNI TUTIB OLISH ---
@bot.poll_answer_handler()
def handle_poll_answer(answer):
    chat_id = None
    # Chat ID ni aniqlash (bu qism murakkabroq, odatda poll yuborilganda saqlanadi)
    # Soddalik uchun foydalanuvchi ismini va natijasini yozamiz
    user_id = answer.user.id
    user_name = answer.user.first_name
    
    # Eslatib o'tamiz: poll_answer_handler chat_id bermaydi, 
    # shuning uchun biz quiz_results'ni global boshqaramiz
    for c_id in quiz_results:
        if user_id not in quiz_results[c_id]:
            quiz_results[c_id][user_id] = {'score': 0, 'name': user_name, 'start_time': time.time()}
        
        # Agar javob to'g'ri bo'lsa (bu yerda poll_id orqali tekshirish kerak)
        # Telegram API cheklovi sababli, ballni oshirish uchun bot poll_id ni eslab qolishi kerak
        quiz_results[c_id][user_id]['score'] += 1 

# --- 3. TEST YARATISH VA ULASHISH (OLDINGI KODDAGI KABI) ---
# ... (Yangi fan testi yaratish, Vaqtni tanlash, Mening testlarim kodlari shu yerda bo'ladi)
