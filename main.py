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
# Render bazangiz manzili yangilandi
DATABASE_URL = 'postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a/quizdb_wgm2'

bot = telebot.TeleBot(TOKEN)
app = Flask('')

# Foydalanuvchi sessiyalari va test natijalari
user_session = {}
quiz_results = {} # {chat_id: {poll_id: correct_option, 'scores': {user_id: {'name': name, 'count': 0}}}}

@app.route('/')
def home(): return "Bot barcha funksiyalari (Leaderboard bilan) faol!"

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS quizzes (id SERIAL PRIMARY KEY, user_id BIGINT, title TEXT, quiz_data TEXT)')
    conn.commit()
    cur.close()
    conn.close()

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

# --- NATIJALARNI HISOBLASH ---
@bot.poll_answer_handler()
def handle_poll_answer(pollAnswer):
    for chat_id in list(quiz_results.keys()):
        if pollAnswer.poll_id in quiz_results[chat_id]:
            correct_id = quiz_results[chat_id][pollAnswer.poll_id]
            # Agar javob to'g'ri bo'lsa ball qo'shish
            if pollAnswer.option_ids[0] == correct_id:
                uid = pollAnswer.user.id
                uname = pollAnswer.user.first_name
                if uid not in quiz_results[chat_id]['scores']:
                    quiz_results[chat_id]['scores'][uid] = {'name': uname, 'count': 0}
                quiz_results[chat_id]['scores'][uid]['count'] += 1

# --- MENYULAR ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    markup.row("📊 Statistika", "❓ Yo'riqnoma")
    return markup

# --- TEST YUBORISH LOGIKASI ---
def run_quiz_logic(chat_id, q_id, interval):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    
    if res:
        title, data = res
        qs = json.loads(data)
        
        # Test natijalarini tozalash va tayyorlash
        quiz_results[chat_id] = {'scores': {}}
        
        bot.send_message(chat_id, f"🏁 **{title}** testi boshlandi! Savollar soni: {len(qs)}")
        
        for idx, i in enumerate(qs, 1):
            try:
                poll = bot.send_poll(
                    chat_id, 
                    f"[{idx}/{len(qs)}] {i['q']}", 
                    i['o'], 
                    type='quiz', 
                    correct_option_id=i['c'], 
                    is_anonymous=False
                )
                # Har bir poll ID sini to'g'ri javob bilan saqlab qo'yamiz
                quiz_results[chat_id][poll.poll.id] = i['c']
                time.sleep(interval)
            except: break
        
        # --- NATIJALARNI CHIQARISH (Leaderboard) ---
        scores = quiz_results[chat_id]['scores']
        result_msg = f"🏁 **“{title}” testi yakunlandi!**\n\n"
        
        if scores:
            # Ballar bo'yicha saralash
            sorted_players = sorted(scores.values(), key=lambda x: x['count'], reverse=True)
            result_msg += f"📊 **Natijalar:**\n\n"
            for index, player in enumerate(sorted_players, 1):
                medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"{index}."
                result_msg += f"{medal} {player['name']} – **{player['count']} ta** to'g'ri javob\n"
        else:
            result_msg += "😕 Afsuski, hech kim testda qatnashmadi."
            
        bot.send_message(chat_id, result_msg, reply_markup=main_menu())
        
        # Xotirani tozalash
        if chat_id in quiz_results:
            del quiz_results[chat_id]

# --- HANDLERLAR ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    parts = message.text.split()
    if len(parts) > 1 and parts[1].startswith('run_'):
        try:
            q_id = int(parts[1].split('_')[1])
            threading.Thread(target=run_quiz_logic, args=(message.chat.id, q_id, 15)).start()
            return
        except:
            bot.reply_to(message, "⚠️ Testni yuklashda xatolik.")
            return
            
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, "🎯 Quiz Botga xush kelibsiz!", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
def show_stat(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM quizzes')
    total = cur.fetchone()[0]
    cur.close()
    conn.close()
    bot.send_message(message.chat.id, f"📈 **Bot statistikasi:**\n\n📝 Jami yaratilgan testlar: {total}")

@bot.message_handler(func=lambda m: m.text == "❓ Yo'riqnoma")
def help_guide(message):
    bot.send_message(message.chat.id, "📖 Savollarni quyidagicha yuboring:\n\nSavol matni\nVariant 1\nVariant 2+\nVariant 3\n\n(To'g'ri javob oxiriga + qo'ying)")

@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def start_new(message):
    user_session[message.from_user.id] = {'subject': '', 'questions': []}
    bot.send_message(message.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, get_subject_name)

def get_subject_name(message):
    uid = message.from_user.id
    if uid in user_session:
        user_session[uid]['subject'] = message.text
        bot.send_message(message.chat.id, f"✅ Fan: **{message.text}**\nSavollarni yuboring.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash", "❌ Bekor qilish"))

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_tests(message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, title, quiz_data FROM quizzes WHERE user_id = %s', (message.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        bot.send_message(message.chat.id, "📭 Sizda hali testlar yo'q.")
        return
        
    for r in rows:
        q_id, title, data = r
        q_count = len(json.loads(data))
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("🚀 Bu testni boshlash", callback_data=f"run_15_{q_id}"))
        m.add(types.InlineKeyboardButton("👥 Guruhda testni boshlash", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}"))
        m.add(types.InlineKeyboardButton("🔗 Testni ulashish", switch_inline_query=f"quiz_{q_id}"))
        m.add(types.InlineKeyboardButton("📝 Tahrirlash", callback_data=f"edit_{q_id}"),
              types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}"))
        
        caption = f"🎲 “{title}” testi\n\n✒️ {q_count} ta savol  ·  ⏱ 15 soniya"
        bot.send_message(message.chat.id, caption, reply_markup=m)

@bot.inline_handler(lambda query: query.query.startswith("quiz_"))
def inline_share(inline_query):
    try:
        q_id = int(inline_query.query.split("_")[1])
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT title, quiz_data FROM quizzes WHERE id = %s', (q_id,))
        res = cur.fetchone()
        cur.close()
        conn.close()
        
        if res:
            title, data = res
            q_count = len(json.loads(data))
            r = types.InlineQueryResultArticle(
                id=str(q_id),
                title=f"🎲 {title}",
                description=f"{q_count} ta savollik testni ulashish",
                input_message_content=types.InputTextMessageContent(
                    message_text=f"🎲 **“{title}” testi**\n\n✒️ {q_count} ta savol mavjud.\n\nTestni boshlash uchun pastdagi tugmani bosing 👇"
                ),
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🚀 Testni boshlash", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}")
                )
            )
            bot.answer_inline_query(inline_query.id, [r])
    except: pass

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    p = call.data.split('_')
    if p[0] == 'run':
        bot.answer_callback_query(call.id, "Test boshlanmoqda...")
        threading.Thread(target=run_quiz_logic, args=(call.message.chat.id, int(p[2]), int(p[1]))).start()
    elif p[0] == 'del':
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM quizzes WHERE id = %s', (p[1],))
        conn.commit()
        cur.close()
        conn.close()
        bot.delete_message(call.message.chat.id, call.message.message_id)
    elif p[0] == 'edit':
        user_session[call.from_user.id] = {'edit_id': int(p[1]), 'subject': '', 'questions': []}
        bot.send_message(call.message.chat.id, "📝 Yangi fan nomini yozing:")
        bot.register_next_step_handler(call.message, get_subject_name)

@bot.message_handler(func=lambda m: True)
def collect(message):
    uid = message.from_user.id
    if uid in user_session:
        if message.text == "🏁 Saqlash":
            s = user_session[uid]
            if not s['questions']: return
            conn = get_db_connection()
            cur = conn.cursor()
            if 'edit_id' in s:
                cur.execute('UPDATE quizzes SET title = %s, quiz_data = %s WHERE id = %s', (s['subject'], json.dumps(s['questions']), s['edit_id']))
            else:
                cur.execute('INSERT INTO quizzes (user_id, title, quiz_data) VALUES (%s, %s, %s)', (uid, s['subject'], json.dumps(s['questions'])))
            conn.commit()
            cur.close()
            conn.close()
            bot.send_message(message.chat.id, "🎉 Test saqlandi!", reply_markup=main_menu())
            del user_session[uid]
            return
        
        new_qs = parse_multiline_questions(message.text)
        if new_qs:
            user_session[uid]['questions'].extend(new_qs)
            bot.send_message(message.chat.id, f"📥 {len(new_qs)} ta savol olindi.")

if __name__ == '__main__':
    init_db()
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    bot.polling(none_stop=True)
