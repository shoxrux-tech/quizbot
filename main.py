import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Render sozlamalari
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
# ADMIN_ID ni Render Environment Variables bo'limiga raqamli ID sifatida yozing
ADMIN_ID = int(os.getenv('ADMIN_ID', 0)) 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# --- ASOSIY MENYU ---
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("📚 Mening testlarim"), KeyboardButton("📊 Statistika"))
    keyboard.add(KeyboardButton("🆕 Yangi fan testi yaratish"))
    keyboard.add(KeyboardButton("👤 Admin"))
    return keyboard

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    if args and args.startswith('run_'):
        quiz_id = args.split('_')[1]
        await start_quiz_session(message.chat.id, quiz_id)
        return
    await message.answer("👋 Bot tayyor! Bo'limni tanlang:", reply_markup=main_menu())

# --- TESTLAR (ULASHISH VA ADMIN HUQUQLARI) ---
@dp.message_handler(lambda m: m.text == "📚 Mening testlarim")
async def my_quizzes(message: types.Message):
    user_id = message.from_user.id
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    
    # Faqat ADMIN barcha testlarni ko'ra oladi
    if user_id == ADMIN_ID:
        cur.execute("SELECT id, title FROM quiz_titles")
    else:
        cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (user_id,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await message.answer("Hozircha testlar yo'q.")
        return

    bot_info = await bot.get_me()
    for q_id, title in rows:
        # Chat va guruhga ulashish tugmasi uchun havola
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=run_{q_id}"
        
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            InlineKeyboardButton("📤 Chatga/Guruhga ulashish", url=share_url)
        )
        
        # Faqat admin testlarni o'chira oladi
        if user_id == ADMIN_ID:
            kb.add(InlineKeyboardButton("🗑 O'chirish (Admin)", callback_data=f"del_{q_id}"))
        
        await message.answer(f"📁 <b>**{title}**</b>", reply_markup=kb)

# --- TEST VAQTINI NAZORAT QILISH ---
async def start_quiz_session(chat_id, quiz_id):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    cur.execute("SELECT timer_seconds, title FROM quiz_titles WHERE id=%s", (quiz_id,))
    res = cur.fetchone()
    timer = res[0]
    
    cur.execute("SELECT question, options, correct_id FROM questions WHERE quiz_id=%s ORDER BY id", (quiz_id,))
    questions = cur.fetchall()
    cur.close()
    conn.close()

    total = len(questions)
    for i, (q, opts_raw, corr_id) in enumerate(questions, 1):
        options = opts_raw.split('|')
        
        # open_period savolni belgilangan vaqtdan keyin yopadi
        poll = await bot.send_poll(
            chat_id=chat_id,
            question=f"[{i}/{total}] {q}",
            options=options,
            type='quiz',
            correct_option_id=corr_id,
            is_anonymous=False,
            open_period=timer 
        )
        await asyncio.sleep(timer) # Keyingi savolgacha kutish

    await bot.send_message(chat_id, "✅ Test yakunlandi! Vaqt tugadi.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
