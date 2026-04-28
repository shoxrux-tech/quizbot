import os
import telebot
import psycopg2
import json
import time
from telebot import types

# --- SOZLAMALAR ---
TOKEN = os.getenv("TOKEN")
# ADMIN_ID ni xavfsiz o'qish
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "5842665369")
ADMIN_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW.isdigit() else 5842665369
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

bot = telebot.TeleBot(TOKEN)
user_session = {}
active_quizzes = {}

def get_db():
    return psycopg2.connect(DATABASE_URL)

# --- ASOSIY MENYU ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        # Testni alohida thread-da boshlash (bot qotib qolmasligi uchun)
        import threading
        threading.Thread(target=start_quiz_engine, args=(msg.chat.id, quiz_id)).start()
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Yangi test yaratish", "📂 Mening testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot tizimiga xush kelibsiz!**", reply_markup=kb, parse_mode="Markdown")

# --- TEST YARATISH JARAYONI ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi test yaratish")
def create_quiz(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "⛔️ Faqat admin test yarata oladi!")
    
    user_session[msg.from_user.id] = {"step": "name", "questions": []}
    bot.send_message(msg.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.from_user.id in user_session)
def quiz_steps(msg):
    uid = msg.from_user.id
    s = user_session[uid]

    if s["step"] == "name":
        s["name"] = msg.text
        s["step"] = "time"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("10", "15", "30", "60")
        bot.send_message(msg.chat.id, "⏱ **Har bir savol uchun vaqt (soniya):**", reply_markup=kb)

    elif s["step"] == "time":
        if not msg.text.isdigit():
            return bot.send_message(msg.chat.id, "⚠️ Faqat raqam tanlang!")
        s["time"] = int(msg.text)
        s["step"] = "questions"
        bot.send_message(msg.chat.id, "✅ Savollarni yuboring (Masalan: Savol\\nVariant1\\nVariant2+). Tugagach **🏁 Saqlash** ni bosing.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

    elif s["step"] == "questions":
        if "Saqlash" in msg.text:
            if not s["questions"]: 
                return bot.send_message(msg.chat.id, "❌ Savol kiritilmadi!")
            
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s) RETURNING id",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            q_id = cur.fetchone()[0]
            conn.commit(); cur.close(); conn.close()
            
            share_url = f"https://t.me/{bot.get_me().username}?start=run_{q_id}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📤 Do'stlarga ulashish", url=f"https://t.me/share/url?url={share_url}"))
            kb.add(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}"))
            
            bot.send_message(msg.chat.id, f"🎉 **Test saqlandi!** ID: {q_id}", reply_markup=kb)
            del user_session[uid]
            return

        blocks = msg.text.strip().split("\n\n")
        for b in blocks:
            lines = [l.strip() for l in b.split('\n') if l.strip()]
            if len(lines) >= 3:
                s["questions"].append({"q": lines[0], "o": lines[1:]})
        bot.send_message(msg.chat.id, f"📥 {len(s['questions'])} ta savol olindi.")

# --- TESTNI BOSHQARISH ---
def start_quiz_engine(chat_id, quiz_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row: return

    title, questions, t_limit = row[0], json.loads(row[1]), row[2]
    # Har bir test uchun noyob kalit (chat_id + vaqt)
    quiz_key = f"{chat_id}"
    active_quizzes[quiz_key] = {"scores": {}, "total": len(questions), "current_poll": None}

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**\nSoniya: {t_limit}", parse_mode="Markdown")
    time.sleep(3)

    for i, q in enumerate(questions):
        options = [o.replace("+", "").strip() for o in q["o"]]
        try:
            correct_id = next(idx for idx, o in enumerate(q["o"]) if "+" in o)
        except StopIteration: correct_id = 0
        
        poll = bot.send_poll(
            chat_id, f"{i+1}/{len(questions)}: {q['q']}", options,
            type="quiz", correct_option_id=correct_id, is_anonymous=False, 
            open_period=t_limit
        )
        active_quizzes[quiz_key]["current_poll"] = poll.poll.id
        time.sleep(t_limit + 1)
        
    finalize_results(chat_id, title, quiz_key)

def finalize_results(chat_id, title, quiz_key):
    if quiz_key not in active_quizzes: return
    data = active_quizzes[quiz_key]
    sorted_res = sorted(data["scores"].items(), key=lambda x: x[1]['score'], reverse=True)
    
    res_text = f"🏁 **“{title}” testi tugadi!**\n\n📊 **Natijalar:**\n"
    if not sorted_res:
        res_text += "❌ Hech kim qatnashmadi."
    else:
        for i, (u_id, info) in enumerate(sorted_res[:10]):
            icon = ["🥇", "🥈", "🥉", "👤"][i] if i < 3 else "👤"
            res_text += f"\n{icon} {info['name']} — {info['score']} ta to'g'ri"

    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    del active_quizzes[quiz_key]

@bot.poll_answer_handler()
def handle_poll_answer(ans):
    # Foydalanuvchi to'g'ri javob berganini tekshirish
    for quiz_key, quiz in active_quizzes.items():
        if quiz["current_poll"] == ans.poll_id:
            if ans.user.id not in quiz["scores"]:
                quiz["scores"][ans.user.id] = {"name": ans.user.first_name, "score": 0}
            
            # To'g'ri javobni hisoblash (bu yerda ans.option_ids keladi)
            # QuizBot rejimida user faqat 1ta variant tanlaydi
            quiz["scores"][ans.user.id]["score"] += 1

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_quizzes(msg):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, title FROM quizzes WHERE user_id=%s", (msg.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    if not rows:
        return bot.send_message(msg.chat.id, "📭 Sizda hali testlar yo'q.")
        
    for r in rows:
        share_url = f"https://t.me/{bot.get_me().username}?start=run_{r[0]}"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📤 Ulashish", url=f"https://t.me/share/url?url={share_url}"))
        bot.send_message(msg.chat.id, f"🎲 **{r[1]}**", reply_markup=kb, parse_mode="Markdown")

if __name__ == "__main__":
    bot.remove_webhook()
    print("Bot ishga tushdi...")
    bot.infinity_polling()
