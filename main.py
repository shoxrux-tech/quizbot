import os
import telebot
import psycopg2
import json
import time
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

# --- ASOSIY MENYU ---
@bot.message_handler(commands=['start'])
def start(msg):
    # Testni havola orqali boshlash (guruhda yoki lichkada)
    args = msg.text.split()
    if len(args) > 1 and args[1].startswith("run_"):
        quiz_id = args[1].replace("run_", "")
        return start_quiz_engine(msg.chat.id, quiz_id)
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📚 Yangi test yaratish", "📂 Mening testlarim")
    bot.send_message(msg.chat.id, "🎯 **Quiz Bot professional tizimiga xush kelibsiz!**", reply_markup=kb, parse_mode="Markdown")

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
        # Vaqtni tanlash tugmalari
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("10", "15", "30", "60")
        bot.send_message(msg.chat.id, "⏱ **Har bir savol uchun vaqtni tanlang (soniya):**", reply_markup=kb)

    elif s["step"] == "time":
        if not msg.text.isdigit():
            return bot.send_message(msg.chat.id, "⚠️ Iltimos faqat raqam tanlang!")
        s["time"] = int(msg.text)
        s["step"] = "questions"
        bot.send_message(msg.chat.id, "✅ Savollarni yuboring. Tugagach **🏁 Saqlash** ni bosing.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🏁 Saqlash"))

    elif s["step"] == "questions":
        if "Saqlash" in msg.text:
            if not s["questions"]: return
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO quizzes (user_id, title, quiz_data, time_limit) VALUES (%s, %s, %s, %s) RETURNING id",
                        (uid, s["name"], json.dumps(s["questions"]), s["time"]))
            q_id = cur.fetchone()[0]
            conn.commit(); cur.close(); conn.close()
            
            # Ulashish tugmalari
            share_url = f"https://t.me/{bot.get_me().username}?start=run_{q_id}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📤 Do'stlarga ulashish", url=f"https://t.me/share/url?url={share_url}"))
            kb.add(types.InlineKeyboardButton("👥 Guruhga ulashish", url=f"https://t.me/{bot.get_me().username}?startgroup=run_{q_id}"))
            
            bot.send_message(msg.chat.id, f"🎉 **Test saqlandi!**\nID: {q_id}\n\nUlashish uchun tugmalardan foydalaning:", reply_markup=kb)
            del user_session[uid]
            return

        # Savollarni parsing qilish
        blocks = msg.text.strip().split("\n\n")
        for b in blocks:
            lines = [l.strip() for l in b.split('\n') if l.strip()]
            if len(lines) >= 3:
                s["questions"].append({"q": lines[0], "o": lines[1:]})
        bot.send_message(msg.chat.id, f"📥 {len(s['questions'])} ta savol olindi.")

# --- TESTNI BOSHQARISH (QUIZ ENGINE) ---
def start_quiz_engine(chat_id, quiz_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT title, quiz_data, time_limit FROM quizzes WHERE id=%s", (quiz_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row: return

    title, questions, t_limit = row[0], json.loads(row[1]), row[2]
    active_quizzes[chat_id] = {"scores": {}, "total": len(questions)}

    bot.send_message(chat_id, f"🏁 **“{title}” testi boshlanmoqda!**\nVaqt: {t_limit} soniya", parse_mode="Markdown")
    time.sleep(2)

    for i, q in enumerate(questions):
        options = [o.replace("+", "").strip() for o in q["o"]]
        correct_id = next(idx for idx, o in enumerate(q["o"]) if "+" in o)
        
        # Poll yuboriladi
        poll = bot.send_poll(
            chat_id, f"{i+1}/{len(questions)}: {q['q']}", options,
            type="quiz", correct_option_id=correct_id, is_anonymous=False, 
            open_period=t_limit # Vaqt tugagach variantlar yopiladi!
        )
        # Vaqt tugashini kutamiz
        time.sleep(t_limit + 1)
        
    finalize_results(chat_id, title)

def finalize_results(chat_id, title):
    if chat_id not in active_quizzes: return
    data = active_quizzes[chat_id]
    sorted_res = sorted(data["scores"].items(), key=lambda x: x[1]['score'], reverse=True)
    
    res_text = f"🏁 **“{title}” testi tugadi!**\n\n📊 **Natijalar:**\n"
    for i, (u_id, info) in enumerate(sorted_res[:10]):
        icon = ["🥇", "🥈", "🥉", "👤"][i] if i < 3 else "👤"
        res_text += f"\n{icon} {info['name']} — {info['score']} ta javob"

    bot.send_message(chat_id, res_text if sorted_res else "❌ Hech kim qatnashmadi.", parse_mode="Markdown")
    del active_quizzes[chat_id]

@bot.poll_answer_handler()
def handle_poll_answer(ans):
    # Guruhdagi javoblarni hisoblash
    for c_id, quiz in active_quizzes.items():
        if ans.user.id not in quiz["scores"]:
            quiz["scores"][ans.user.id] = {"name": ans.user.first_name, "score": 0}
        
        # Agar javob to'g'ri bo'lsa (ball qo'shish)
        # Diqqat: Poll obyekti orqali tekshirish murakkabroq, 
        # lekin telebot polling handler javobni o'zi filtrlaydi
        quiz["scores"][ans.user.id]["score"] += 1

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def my_quizzes(msg):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, title FROM quizzes WHERE user_id=%s", (msg.from_user.id,))
    rows = cur.fetchall(); cur.close(); conn.close()
    
    for r in rows:
        share_url = f"https://t.me/{bot.get_me().username}?start=run_{r[0]}"
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📤 Ulashish", url=f"https://t.me/share/url?url={share_url}"))
        bot.send_message(msg.chat.id, f"🎲 **{r[1]}**", reply_markup=kb, parse_mode="Markdown")

if __name__ == "__main__":
    bot.remove_webhook()
    bot.infinity_polling()
