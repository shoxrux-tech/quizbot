import os
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- SOZLAMALAR ---
# Tokenni olish va tekshirish
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID_RAW = os.getenv('ADMIN_ID', '0')

if not API_TOKEN:
    raise ValueError("XATOLIK: BOT_TOKEN topilmadi! Render Environment Variables'ni tekshiring.")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 0

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# --- KLAVIATURA ---
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("📚 Mening testlarim"), KeyboardButton("📊 Statistika"))
    keyboard.add(KeyboardButton("🆕 Yangi fan testi yaratish"))
    return keyboard

# --- START KOMANDASI ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    if args and args.startswith('run_'):
        # Ulashish orqali kirilganda testni boshlash logikasi
        await message.answer("🚀 Test yuklanmoqda...")
        return
    await message.answer("👋 Bot ishga tushdi! Bo'limni tanlang:", reply_markup=main_menu())

# --- ULASHISH TUGMALARI BOR BO'LIM ---
@dp.message_handler(lambda m: m.text == "📚 Mening testlarim")
async def my_quizzes(message: types.Message):
    user_id = message.from_user.id
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor()
        
        if user_id == ADMIN_ID:
            cur.execute("SELECT id, title FROM quiz_titles")
        else:
            cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (user_id,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        await message.answer(f"Bazaga ulanishda xato: {e}")
        return

    if not rows:
        await message.answer("Sizda hali testlar yo'q.")
        return

    bot_info = await bot.get_me()
    for q_id, title in rows:
        # Ulashish havolasi (Deep Linking)
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=run_{q_id}"
        
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            InlineKeyboardButton("📤 Guruhga ulashish", url=share_url)
        )
        if user_id == ADMIN_ID:
            kb.add(InlineKeyboardButton("🗑 O'chirish (Admin)", callback_data=f"del_{q_id}"))
            
        await message.answer(f"📋 Test: <b>{title}</b>", reply_markup=kb)

# --- BOTNI ISHGA TUSHIRISH ---
if __name__ == '__main__':
    # Render kutayotgan portni ochish (agar kerak bo'lsa)
    executor.start_polling(dp, skip_updates=True)
