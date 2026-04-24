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
ADMIN_ID = 5842665369  
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
app = Flask('')

user_session = {}
quiz_results = {} 

@app.route('/')
def home(): return "Bot 24/7 faol holatda!"

# --- BAZA BILAN XATOSIZ ISHLASH ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except Exception as e:
        print(f"Baza xatosi: {e}")
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
        # Profilni yangilash
        try: bot.set_my_description(f"📊 {count} ta foydalanuvchi botdan foydalanmoqda")
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

# --- MENYULAR ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    return markup

# --- TEST LOGIKASI VA LEADERBOARD ---
@bot.poll_answer_handler()
def handle_poll_answer(pollAnswer):
    for chat_id in list(quiz_results.keys()):
        if pollAnswer.poll_id in quiz_results[chat_id]:
            correct_id = quiz_results[chat_id][pollAnswer.poll_id]
            if pollAnswer.option_ids[0] == correct_id:
                uid, uname = pollAnswer.user.id, pollAnswer.user.first_name
                if uid not in quiz_results[chat_id]['scores']:
                    quiz_results[chat_id]['scores'][uid] = {'name': uname, 'count': 0, 'start': time.time()}
                quiz_results[chat_id]['scores'][uid]['count'] += 1
                quiz_results[chat_id]['scores'][uid]['last'] = time.time()

def run_quiz_logic(chat_id, q_id, interval):
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
    res = cur.fetchone()
    cur.close(); conn.close()
    
    if res:
        title, data = res
        qs = json.loads(data)
        quiz_results[chat_id] = {'scores': {}}
        bot.send_message(chat_id, f"🏁 **“{title}”** testi boshlandi!\nSavollar soni: {len(qs)}")
        
        for idx, i in enumerate(qs, 1):
            try:
                poll = bot.send_poll(chat_id, f"[{idx}/{len(qs)}] {i['q']}", i['o'], 
                                    type='quiz', correct_option_id=i['c'], is_anonymous=False)
                quiz_results[chat_id][poll.poll.id] = i['c']
                time.sleep(interval)
                bot.stop_poll(chat_id, poll.message_id)
            except: break
        
        scores = quiz_results[chat_id]['scores']
        result_msg = f"🏁 **“{title}” testi yakunlandi!**\n\n"
        if scores:
            sorted_players = sorted(scores.values(), key=lambda x: x['count'], reverse=True)
            for idx, p in enumerate(sorted_players, 1):
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
                dur = int(p.get('last', 0) - p.get('start', 0))
                result_msg += f"{medal} {p['name']} – **{p['count']} ta** ({dur} s)\n"
        else: result_msg += "😕 Ishtirokchilar yo'q."
        bot.send_message(chat_id, result_msg, reply_markup=main_menu())
        quiz_results.pop(chat_id, None)

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
    if uid == ADMIN_ID:
        user_session[uid] = {'subject': '', 'questions': []}
        bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, get_subject_name)
    else:
        bot.reply_to(message, "⛔️ Test tuzish uchun adminga murojaat qiling!")
        bot.send_message(ADMIN_ID, f"🔔 So'rov: {message.from_user.first_name} test tuzmoqchi.")

def get_subject_name(message):
    uid = message.from_user.id
    if uid == ADMIN_ID and uid in user_session:
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
                cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', (uid, s['subject'], json.dumps(s['questions'])))
                conn.commit(); cur.close(); conn.close()
                bot.send_message(message.chat.id, "🎉 Test saqlandi!", reply_markup=main_menu())
                del user_session[uid]
        elif message.text == "❌ Bekor qilish":
            del user_session[uid]
            bot.send_message(message.chat.id, "O'chirildi.", reply_markup=main_menu())
        else:
            new_qs = parse_multiline_questions(message.text)
            if new_qs:
                user_session[uid]['questions'].extend(new_qs)
                bot.send_message(message.chat.id, f"📥 {len(new_qs)} ta savol olindi.")

@bot.inline_handler(lambda query: query.query.startswith("quiz_"))
def inline_share(inline_query):
    try:
        q_id = int(inline_query.query.split("_")[1])
        conn = get_db_connection()
        if conn:
            cur = conn.cursor(); cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
            res = cur.fetchone(); cur.close(); conn.close()
            if res:
                r = types.InlineQueryResultArticle(
                    id=str(q_id), title=f"🎲 {res[0]}", description=f"{len(json.loads(res[1]))} ta savol",
                    input_message_content=types.InputTextMessageContent(f"🎲 **“{res[0]}” testi**\n\nBoshlash uchun bosing 👇"),
                    reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚀 Boshlash", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}"))
                )
                bot.answer_inline_query(inline_query.id, [r], cache_time=1)
    except: pass

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor(); cur.execute('SELECT id, title, quiz_data FROM quizzes WHERE user_id = %s', (message.from_user.id,))
        rows = cur.fetchall(); cur.close(); conn.close()
        if not rows: bot.send_message(message.chat.id, "📭 Testlar yo'q."); return
        for r in rows:
            m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👥 Ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{r[0]}"))
            bot.send_message(message.chat.id, f"🎲 “{r[1]}” ({len(json.loads(r[2]))} ta savol)", reply_markup=m)

@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def stats(message):
    conn = get_db_connection()
    if conn:
        cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM users'); u = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM quizzes'); q = cur.fetchone()[0]
        cur.close(); conn.close()
        bot.send_message(message.chat.id, f"👥 Azolar: {u}\n🎲 Testlar: {q}")

if __name__ == '__main__':
    init_db()
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    while True:
        try: bot.polling(none_stop=True, timeout=60)
        except: time.sleep(5)
