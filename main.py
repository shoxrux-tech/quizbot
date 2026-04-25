import os
import telebot
import psycopg2
import json
import time
from telebot import types

# --- SOZLAMALAR ---
TOKEN = os.getenv("TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "5842665369")
DATABASE_URL = os.getenv("DATABASE_URL")
# ADMIN_ID ni raqamga o'tkazishda xatolikni oldini olish
try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 5842665369

# DATABASE_URL ni Render uchun to'g'irlash
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

# Token borligini tekshirish
if not TOKEN:
    print("⚠️ DIQQAT: TOKEN topilmadi! Render Environment Variables-ni tekshiring.")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Vaqtinchalik ma'lumotlar
user_session = {}
active_quizzes = {}

def get_db():
    return psycopg2.connect(DATABASE_URL)

# --- BOT FUNKSIYALARI ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        return start_quiz_engine(msg.chat.id, args[1].replace("run_", ""))
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Yangi fan testi yaratish", "📂 Mening testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot ishga tushdi!**", reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📚 Yangi fan testi yaratish")
def create_quiz(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "⛔️ Faqat admin test yarata oladi!")

    user_session[msg.from_user.id] = {"step": "name", "questions": []}
    bot.send_message(msg.chat.id, "📖 Fan nomini kiriting:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.from_user.id in user_session)
def quiz_steps(msg):
    uid = msg.from_user.id
    s = user_session[uid]

    if s["step"] == "name":
        s["name"] = msg.text
        s["step"] = "time"
        bot.send_message(msg.chat.id, "⏱ Savol vaqti (sekund):")

    elif s["step"] == "time":
        s["time"] = int(msg.text) if msg.text.isdigit() else 15
        s["step"] = "questions"
        bot.send_message(msg.chat.id, "✅ Savollarni yuboring. Tugagach **🏁 Saqlash** ni bosing.")

    elif s["step"] == "questions":
        if "Saqlash" in msg.text:
            if not s["questions"]: return
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s)",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            conn.commit(); cur.close(); conn.close()
            bot.send_message(msg.chat.id, "🎉 Test saqlandi!", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("📂 Mening testlarim"))
            del user_session[uid]
            return

        blocks = msg.text.strip().split("\n\n")
        for b in blocks:
            lines = [l.strip() for l in b.split('\n') if l.strip()]
            if len(lines) >= 3:
                s["questions"].append({"q": lines[0], "o": lines[1:]})
        
        bot.send_message(msg.chat.id, f"📥 {len(s['questions'])} ta savol olindi.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

def start_quiz_engine(chat_id, quiz_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row: return

    title, questions, t_limit = row[0], json.loads(row[1]), row[2]
    active_quizzes[chat_id] = {"scores": {}}

    bot.send_message(chat_id, f"🏁 **{title}** testi boshlandi!")
    
    for i, q in enumerate(questions):
        options = [o.replace("+", "").strip() for o in q["o"]]
        correct_id = next(idx for idx, o in enumerate(q["o"]) if "+" in o)
        bot.send_poll(chat_id, f"{i+1}: {q['q']}", options, type="quiz", correct_option_id=correct_id, is_anonymous=False, open_period=t_limit)
        time.sleep(t_limit + 1)
    
    bot.send_message(chat_id, "🏁 Test yakunlandi!")

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_quizzes(msg):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, title FROM quizzes WHERE user_id=%s", (msg.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    for r in rows:
        link = f"https://t.me/{bot.get_me().username}?start=run_{r[0]}"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🚀 Boshlash", url=link))
        bot.send_message(msg.chat.id, f"🎲 {r[1]}", reply_markup=markup)

# --- POLLING ISHGA TUSHIRISH ---
if __name__ == "__main__":
    print("🚀 Bot Polling rejimida ishga tushmoqda...")
    bot.remove_webhook() # Webhookni tozalash
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
