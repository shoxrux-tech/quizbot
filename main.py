import os
import telebot
import psycopg2
import json
import time
import threading
from telebot import types

# --- SOZLAMALAR ---
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5842665369"))
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

bot = telebot.TeleBot(TOKEN)
user_session = {}
active_quizzes = {}

def get_db():
    return psycopg2.connect(DATABASE_URL)

# --- 🛠 AVTOMATIK BAZANI SOZLASh (Siz qidirgan qism) ---
def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        # Jadval bo'lmasa yaratish va ustunni tekshirib qo'shish
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                title TEXT,
                quiz_data JSONB,
                time_limit INTEGER DEFAULT 15
            );
        """)
        # Agar jadval eski bo'lsa, ustunni qo'shib qo'yish
        cur.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name='quizzes' AND column_name='time_limit') THEN
                    ALTER TABLE quizzes ADD COLUMN time_limit INTEGER DEFAULT 15;
                END IF;
            END $$;
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Baza avtomatik sozlandi!")
    except Exception as e:
        print(f"❌ Baza sozlashda xato: {e}")

# --- ASOSIY FUNKSIYALAR ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        threading.Thread(target=start_quiz_engine, args=(msg.chat.id, args[1].replace("run_", ""))).start()
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Yangi test yaratish", "📂 Mening testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot tayyor!**", reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📚 Yangi test yaratish")
def create_quiz(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "⛔️ Faqat admin ruxsatiga ega.")
    user_session[msg.from_user.id] = {"step": "name", "questions": []}
    bot.send_message(msg.chat.id, "📖 **Fan nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.from_user.id in user_session)
def quiz_steps(msg):
    uid = msg.from_user.id
    s = user_session[uid]

    if s["step"] == "name":
        s["name"] = msg.text
        s["step"] = "time"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add("15", "30", "60")
        bot.send_message(msg.chat.id, "⏱ **Soniya tanlang:**", reply_markup=kb)

    elif s["step"] == "time":
        s["time"] = int(msg.text) if msg.text.isdigit() else 15
        s["step"] = "questions"
        bot.send_message(msg.chat.id, "✅ Savollarni yuboring. Tugagach **🏁 Saqlash** ni bosing.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

    elif s["step"] == "questions":
        if "Saqlash" in msg.text:
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s) RETURNING id",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            q_id = cur.fetchone()[0]
            conn.commit(); cur.close(); conn.close()
            bot.send_message(msg.chat.id, f"🎉 **Saqlandi!** ID: {q_id}\nLink: `t.me/{bot.get_me().username}?start=run_{q_id}`", parse_mode="Markdown")
            del user_session[uid]
            return
        # Oddiy savol qabul qilish
        lines = msg.text.strip().split('\n')
        if len(lines) >= 3:
            s["questions"].append({"q": lines[0], "o": lines[1:]})
            bot.send_message(msg.chat.id, f"📥 Olindi. Jami: {len(s['questions'])}")

def start_quiz_engine(chat_id, quiz_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row: return
    title, questions, t_limit = row[0], json.loads(row[1]), row[2]
    bot.send_message(chat_id, f"🏁 **{title}** boshlandi!")
    for i, q in enumerate(questions):
        options = [o.replace("+", "").strip() for o in q["o"]]
        c_id = next((idx for idx, o in enumerate(q["o"]) if "+" in o), 0)
        bot.send_poll(chat_id, f"{i+1}: {q['q']}", options, type="quiz", correct_option_id=c_id, is_anonymous=False, open_period=t_limit)
        time.sleep(t_limit + 1)

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_quizzes(msg):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, title FROM quizzes WHERE user_id=%s", (msg.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    if not rows: return bot.send_message(msg.chat.id, "📭 Bo'sh.")
    for r in rows:
        bot.send_message(msg.chat.id, f"🎲 {r[1]}\nID: {r[0]}")

if __name__ == "__main__":
    init_db() # 🚀 Botni yoqishdan oldin bazani o'zi to'g'irlaydi
    bot.infinity_polling()
