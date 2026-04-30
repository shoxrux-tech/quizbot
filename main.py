import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask
from threading import Thread

# Render uchun kichik server (Health Check uchun)
app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# --- BOT SOZLAMALARI ---
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# --- ASOSIY MENYU ---
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("📚 Mening testlarim"), KeyboardButton("📊 Statistika"))
    keyboard.add(KeyboardButton("🆕 Yangi fan testi yaratish"))
    return keyboard

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    # Ulashish orqali kirilganda
    args = message.get_args()
    if args and args.startswith('run_'):
        quiz_id = args.split('_')[1]
        await message.answer("🚀 Test yuklanmoqda...")
        return # Bu yerda start_quiz funksiyasini chaqirish mumkin

    await message.answer("👋 Bot yangilandi! Bo'limni tanlang:", reply_markup=main_menu())

@dp.message_handler(lambda m: m.text == "📚 Mening testlarim")
async def my_quizzes(message: types.Message):
    user_id = message.from_user.id
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    
    # ADMIN hamma testni ko'radi, oddiy foydalanuvchi faqat o'zinikini
    if user_id == ADMIN_ID:
        cur.execute("SELECT id, title FROM quiz_titles")
    else:
        cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (user_id,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await message.answer("Hozircha hech qanday test topilmadi.")
        return

    bot_info = await bot.get_me()
    for q_id, title in rows:
        # ULASHISH TUGMASI MANA SHU YERDA:
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=run_{q_id}"
        
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            InlineKeyboardButton("📤 Chatga/Guruhga ulashish", url=share_url)
        )
        if user_id == ADMIN_ID:
            kb.add(InlineKeyboardButton("🗑 O'chirish (Admin)", callback_data=f"del_{q_id}"))
        
        await message.answer(f"📁 <b>{title}</b>", reply_markup=kb)

if __name__ == '__main__':
    # Flaskni alohida oqimda yurgizamiz
    Thread(target=run_flask).start()
    # Botni ishga tushiramiz
    executor.start_polling(dp, skip_updates=True)
