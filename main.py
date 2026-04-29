import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# --- SOZLAMALAR ---
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# --- ASOSIY MENYU TUGMALARI ---
def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🆕 Yangi fan testi yaratish"))
    keyboard.row(KeyboardButton("📚 Mening testlarim"), KeyboardButton("📊 Statistika"))
    keyboard.add(KeyboardButton("👤 Admin"))
    return keyboard

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    # Deep linking orqali kelganda testni boshlash
    args = message.get_args()
    if args and args.startswith('run_'):
        quiz_id = args.split('_')[1]
        await start_quiz_session(message.chat.id, quiz_id)
        return

    await message.answer("👋 Bot Render'da tayyor va barcha funksiyalar yoniq!", reply_markup=main_menu())

# --- MENING TESTLARIM (SIZ XOHLAGAN TUGMALAR) ---
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

    bot_info = await bot.get_me()
    for q_id, title in rows:
        # Ulashish havolasi: bu link bosilganda guruhda botga start berish chiqadi
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=run_{q_id}"
        
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}")
        )
        kb.add(InlineKeyboardButton("📤 Guruhga/Chatga ulashish", url=share_url))
        
        await message.answer(f"📁 <b>**{title}**</b>", reply_markup=kb)

# --- TEST JARAYONI (VAQT TUGAGACH YOPILADI) ---
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
        
        poll_msg = await bot.send_poll(
            chat_id=chat_id,
            question=f"[{i}/{total}] {q}",
            options=options,
            type='quiz',
            correct_option_id=corr_id,
            is_anonymous=False,
            open_period=timer # Vaqt tugagach Telegram avtomatik savolni yopadi
        )
        
        await asyncio.sleep(timer + 1) # Keyingi savolga o'tishdan oldin kutish

    await bot.send_message(chat_id, "✅ Test yakunlandi!")

# --- CALLBACKLAR ---
@dp.callback_query_handler(lambda c: c.data.startswith('run_'))
async def run_callback(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[1]
    await start_quiz_session(callback_query.message.chat.id, quiz_id)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('del_'))
async def del_callback(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[1]
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    cur.execute("DELETE FROM quiz_titles WHERE id=%s", (quiz_id,))
    conn.commit()
    cur.close()
    conn.close()
    await callback_query.message.delete()
    await callback_query.answer("Test o'chirildi")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
