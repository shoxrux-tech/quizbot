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

# DATABASE_URL bo'sh bo'lsa xato bermasligi uchun tekshiruv
if not TOKEN or not DATABASE_URL:
    print("❌ XATO: TOKEN yoki DATABASE_URL topilmadi!")
    exit(1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://")

bot = telebot.TeleBot(TOKEN)
user_session = {}
active_quizzes = {} # Natijalarni hisoblash uchun

def get_db():
    return psycopg2.connect(DATABASE_URL)

# --- 🛠 BAZANI AVTO-SOZLASH (Xatolarni to'g'irlash uchun) ---
def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                title TEXT,
                quiz_data JSONB,
                time_limit INTEGER DEFAULT 15
            );
        """)
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
        print("✅ Baza va funksiyalar tayyor!")
    except Exception as e:
        print(f"❌ Baza sozlashda xato: {e}")

# --- START VA ASOSIY MENYU ---
@bot.message_handler(commands=['start'])
def start(msg):
    args = msg.text.split()
    # Guruhda yoki lichkada testni boshlash (Link orqali)
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        threading.Thread(target=start_quiz_engine, args=(msg.chat.id, quiz_id)).start()
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Yangi test yaratish", "📂 Mening testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot professional tizimi ishga tushdi!**", reply_markup=kb, parse_mode="Markdown")

# --- 📚 TEST YARATISH (Vaqt tanlash bilan) ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi test yaratish")
def create_quiz(msg):
    if msg.from_user.id != ADMIN_ID:
        return bot.send_message(msg.chat.id, "⛔️ Kechirasiz, faqat admin test yarata oladi.")
    
    user_session[msg.from_user.id] = {"step": "name", "questions": []}
    bot.send_message(msg.chat.id, "📖 **Fan yoki mavzu nomini kiriting:**", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.from_user.id in user_session)
def quiz_steps(msg):
    uid = msg.from_user.id
    s = user_session[uid]

    if s["step"] == "name":
        s["name"] = msg.text
        s["step"] = "time"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("10", "15", "30", "60", "120")
        bot.send_message(msg.chat.id, "⏱ **Har bir savol uchun vaqt tanlang (soniya):**", reply_markup=kb)

    elif s["step"] == "time":
        s["time"] = int(msg.text) if msg.text.isdigit() else 15
        s["step"] = "questions"
        bot.send_message(msg.chat.id, "✅ Savollarni yuboring. Namuna:\n\nSavol matni\nJavob 1\nJavob 2+\nJavob 3\n\n(To'g'ri javob yoniga + qo'ying). Tugagach **🏁 Saqlash** ni bosing.", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

    elif s["step"] == "questions":
        if "Saqlash" in msg.text:
            if not s["questions"]: return bot.send_message(msg.chat.id, "❌ Savol kiritmadingiz!")
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s) RETURNING id",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            q_id = cur.fetchone()[0]
            conn.commit(); cur.close(); conn.close()
            bot.send_message(msg.chat.id, f"🎉 **Test tayyor!**\nID: `{q_id}`\nLink: `t.me/{bot.get_me().username}?start=run_{q_id}`", parse_mode="Markdown")
            del user_session[uid]
            return

        lines = msg.text.strip().split('\n')
        if len(lines) >= 3:
            s["questions"].append({"q": lines[0], "o": lines[1:]})
            bot.send_message(msg.chat.id, f"📥 {len(s['questions'])} ta savol kiritildi.")

# --- 📊 NATIJALARNI HISOBLASH VA TESTNI O'TKAZISH ---
def start_quiz_engine(chat_id, quiz_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row: return

    title, questions, t_limit = row[0], json.loads(row[1]), row[2]
    quiz_key = f"{chat_id}_{time.time()}"
    active_quizzes[quiz_key] = {"scores": {}, "total": len(questions)}

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlandi!**\nSoniya: {t_limit}", parse_mode="Markdown")
    
    for i, q in enumerate(questions):
        options = [o.replace("+", "").strip() for o in q["o"]]
        correct_id = next((idx for idx, o in enumerate(q["o"]) if "+" in o), 0)
        
        poll = bot.send_poll(
            chat_id, f"{i+1}/{len(questions)}: {q['q']}", options,
            type="quiz", correct_option_id=correct_id, is_anonymous=False, 
            open_period=t_limit
        )
        time.sleep(t_limit + 1) # Navbatdagi savolgacha kutish

    finalize_results(chat_id, title, quiz_key)

def finalize_results(chat_id, title, quiz_key):
    # Bu yerda bot poll natijalarini Telegram orqali yig'adi (is_anonymous=False bo'lishi shart)
    bot.send_message(chat_id, f"🏁 **“{title}” testi yakunlandi!**\nNatijalarni ko'rish uchun poll ustiga bosing (Telegram statistikasi).")

if __name__ == "__main__":
    init_db()
    print("Bot muvaffaqiyatli ishga tushdi...")
    bot.infinity_polling()
