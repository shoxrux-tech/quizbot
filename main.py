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
# O'zingizning Telegram ID raqamingizni Render'da ADMIN_ID deb kiriting
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
    # Agar foydalanuvchi ulashilgan havola orqali kelsa
    if args and args.startswith('run_'):
        quiz_id = args.split('_')[1]
        await start_quiz_session(message.chat.id, quiz_id)
        return
    await message.answer("👋 Salom! Testlar botiga xush kelibsiz.", reply_markup=main_menu())

# --- TESTLARNI CHIQARISH (ADMIN VA FOYDALANUVCHI UCHUN) ---
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
        await message.answer("Hozircha testlar yo'q.")
        return

    bot_user = await bot.get_me()
    for q_id, title in rows:
        # Ulashish havolasi: bu tugma bosilganda chatlar ro'yxati chiqadi
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_user.username}?start=run_{q_id}"
        
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            InlineKeyboardButton("📤 Guruhga/Chatga ulashish", url=share_url)
        )
        
        # O'chirish tugmasi faqat test egasi yoki admin uchun
        kb.add(InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}"))
        
        await message.answer(f"📁 <b>**{title}**</b>", reply_markup=kb)

# --- TESTNI O'TKAZISH VA VAQTNI CHEKLASH ---
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
        
        # open_period savolni vaqt tugashi bilan avtomat yopadi
        poll = await bot.send_poll(
            chat_id=chat_id,
            question=f"[{i}/{total}] {q}",
            options=options,
            type='quiz',
            correct_option_id=corr_id,
            is_anonymous=False,
            open_period=timer 
        )
        # Savol tugashini kutamiz
        await asyncio.sleep(timer)

    await bot.send_message(chat_id, "✅ Test yakunlandi! Hech kim qayta javob bera olmaydi.")

# --- CALLBACKLAR ---
@dp.callback_query_handler(lambda c: c.data.startswith('run_'))
async def run_callback(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[1]
    await start_quiz_session(callback_query.message.chat.id, quiz_id)
    await callback_query.answer()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
