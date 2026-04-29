import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# --- SOZLAMALAR ---
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# --- MENYU ---
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📚 Mening testlarim"))
    keyboard.add(KeyboardButton("🆕 Yangi fan testi yaratish"))
    return keyboard

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    if args and args.startswith('run_'):
        quiz_id = args.split('_')[1]
        # Testni boshlash funksiyasi shu yerda chaqiriladi
        return
    await message.answer("Sizning professional Quiz botingiz tayyor!", reply_markup=main_menu())

# --- MANA SHU YERDA TUGMALAR CHIQADI ---
@dp.message_handler(lambda m: m.text == "📚 Mening testlarim")
async def my_quizzes(message: types.Message):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (message.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await message.answer("Sizda hali testlar yo'q.")
        return

    bot_user = await bot.get_me()
    for q_id, title in rows:
        # Maxsus ulashish linki
        share_link = f"https://t.me/share/url?url=https://t.me/{bot_user.username}?start=run_{q_id}"
        
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            InlineKeyboardButton("📤 Guruhga/Chatga ulashish", url=share_link), # BU TUGMA CHATLAR RO'YXATINI OCHADI
            InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}")
        )
        await message.answer(f"📁 <b>**{title}**</b>", reply_markup=kb)

# --- QOLGAN FUNKSIYALAR (RUN, DELETE) ---
# ... (avvalgi kodlardagi kabi)

if __name__ == '__main__':
    # Render'da "Build Success" bo'lishi uchun Flask shart emas, lekin portni band qilish kerak bo'lsa qo'shiladi.
    executor.start_polling(dp, skip_updates=True)
