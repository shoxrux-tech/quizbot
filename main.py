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

# Render bazasi uchun formatni to'g'rilash
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

bot = telebot.TeleBot(TOKEN)
user_session = {}

def get_db():
    return psycopg2.connect(DATABASE_URL)

# --- 🛠 BAZANI AVTOMATIK SOZLASh FUNKSIYASI ---
def auto_setup_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        # 1. Agar jadval bo'lmasa, yaratadi
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                title TEXT,
                quiz_data JSONB,
                time_limit INTEGER DEFAULT 15
            );
        """)
        # 2. Agar jadval bo'lsa-yu, lekin 'time_limit' ustuni bo'lmasa, uni qo'shadi
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
        print("✅ Ma'lumotlar bazasi muvaffaqiyatli tekshirildi va sozlandi!")
    except Exception as e:
        print(f"❌ Bazani sozlashda xato: {e}")

# --- BOT BUYRUQLARI ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        threading.Thread(target=start_quiz_engine, args=(msg.chat.id, args[1].replace("run_", ""))).start()
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Yangi test yaratish", "📂 Mening testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot tizimiga xush kelibsiz!**", reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📚 Yangi test yaratish")
def create_quiz(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "⛔️ Bu tugma faqat admin uchun.")
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
        bot.send_message(msg.chat.id, "⏱ **Har bir savol uchun vaqt (soniya) tanlang:**", reply_markup=kb)

    elif s["step"] == "time":
        s["time"] = int(msg.text) if msg.text.isdigit() else 15
        s["step"] = "questions"
        bot.send_message(msg.chat.id, "✅ Savollarni yuboring.\n\nNamuna:\nSavol?\nJavob 1\nJavob 2+\nJavob 3\n\nTugagach **🏁 Saqlash** ni bosing.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

    elif s["step"] == "questions":
        if "Saqlash" in msg.text:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s) RETURNING id",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            q_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
            bot.send_message(msg.chat.id, f"🎉 **Saqlandi!**\nLink: `t.me/{bot.get_me().username}?start=run_{q_id}`", parse_mode="Markdown")
            del user_session[uid]
            return
        
        lines = msg.text.strip().split('\n')
        if len(lines) >= 3:
            s["questions"].append({"q": lines[0], "o": lines[1:]})
            bot.send_message(msg.chat.id, f"📥 Savol olindi. Jami: {len(s['questions'])}")

def start_quiz_engine(chat_id, quiz_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if not row: return
    title, questions, t_limit = row[0], json.loads(row[1]), row[2]
    
    bot.send_message(chat_id, f"🏁 **{title}** testi boshlanmoqda...")
    for i, q in enumerate(questions):
        options = [o.replace("+", "").strip() for o in q["o"]]
        c_id = next((idx for idx, o in enumerate(q["o"]) if "+" in o), 0)
        bot.send_poll(chat_id, f"{i+1}: {q['q']}", options, type="quiz", correct_option_id=c_id, is_anonymous=False, open_period=t_limit)
        time.sleep(t_limit + 1)

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_quizzes(msg):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM quizzes WHERE user_id=%s", (msg.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    if not rows:
        return bot.send_message(msg.chat.id, "📭 Sizda hali testlar yo'q.")
    for r in rows:
        bot.send_message(msg.chat.id, f"🎲 {r[1]}\nID: `{r[0]}`\nLink: `t.me/{bot.get_me().username}?start=run_{r[0]}`", parse_mode="Markdown")

if __name__ == "__main__":
    auto_setup_db() # 🚀 Bot yoqilishi bilan bazani o'zi tekshirib to'g'irlaydi
    print("Bot ishga tushdi...")
    bot.infinity_polling()
