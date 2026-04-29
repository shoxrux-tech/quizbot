import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- SOZLAMALAR ---
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# --- TESTNI BOSHLASH VA TAYMER ---
async def start_quiz_session(chat_id, quiz_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT timer_seconds, title FROM quiz_titles WHERE id=%s", (quiz_id,))
    res = cur.fetchone()
    timer = res[0]
    title = res[1]
    
    cur.execute("SELECT question, options, correct_id FROM questions WHERE quiz_id=%s ORDER BY id", (quiz_id,))
    questions = cur.fetchall()
    cur.close()
    conn.close()

    total = len(questions)
    await bot.send_message(chat_id, f"🚀 <b>{title}</b> testi boshlandi!\nHar bir savolga {timer} soniya beriladi.")

    for i, (q, opts_raw, corr_id) in enumerate(questions, 1):
        options = opts_raw.split('|')
        
        # [i/total] formatida savolni yuboramiz
        poll_msg = await bot.send_poll(
            chat_id=chat_id,
            question=f"[{i}/{total}] {q}",
            options=options,
            type='quiz',
            correct_option_id=corr_id,
            is_anonymous=False,
            open_period=timer, # VAQT TUGAGACH JAVOB BERIB BO'LMAYDI
            is_closed=False
        )
        
        # Vaqt tugashini kutamiz (+1 soniya zaxira bilan)
        await asyncio.sleep(timer + 1)
        
        # Savolni majburiy yopish (agar o'zi yopilmagan bo'lsa)
        try:
            await bot.stop_poll(chat_id, poll_msg.message_id)
        except:
            pass 

    await bot.send_message(chat_id, f"🏁 <b>{title}</b> testi yakunlandi!")

# --- MENING TESTLARIM (ULASHISH TUGMASI BILAN) ---
@dp.message_handler(lambda m: m.text == "📚 Mening testlarim")
async def my_quizzes(message: types.Message):
    conn = get_db_connection()
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
        kb = InlineKeyboardMarkup(row_width=1)
        
        # Haqiqiy ulashish tugmasi (Inline link)
        share_link = f"https://t.me/{bot_info.username}?start=run_{q_id}"
        
        kb.add(
            InlineKeyboardButton("▶️ Testni hozir boshlash", callback_data=f"run_{q_id}"),
            InlineKeyboardButton("📤 Guruhga/Chatga ulashish", url=f"https://t.me/share/url?url={share_link}"),
            InlineKeyboardButton("🗑 Testni o'chirish", callback_data=f"del_{q_id}")
        )
        await message.answer(f"📋 <b>{title}</b>", reply_markup=kb)

# --- START KOMANDASI (ULASHISH ORQALI KELGANDA) ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    args = message.get_args()
    if args and args.startswith('run_'):
        quiz_id = args.split('_')[1]
        await start_quiz_session(message.chat.id, quiz_id)
        return
        
    await message.answer("Xush kelibsiz! Test yaratish uchun 'Admin' tugmasidan foydalaning.", 
                         reply_markup=main_menu_keyboard()) # menyuni o'zingizniki bilan almashtiring

@dp.callback_query_handler(lambda c: c.data.startswith('run_'))
async def run_callback(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[1]
    await start_quiz_session(callback_query.message.chat.id, quiz_id)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('del_'))
async def del_callback(callback_query: types.CallbackQuery):
    # O'chirish kodi (avvalgidek)
    pass

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
