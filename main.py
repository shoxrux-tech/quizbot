import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
import sqlite3

# --- SOZLAMALAR ---
API_TOKEN = '8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs'
ADMIN_ID = 5842665369  # O'z ID'ingiz

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- BAZA BILAN ISHLASH ---
db = sqlite3.connect("quiz.db")
sql = db.cursor()
sql.execute("""CREATE TABLE IF NOT EXISTS quizes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT,
    options TEXT,
    correct_id INTEGER,
    owner_id INTEGER
)""")
db.commit()

# --- PARSING FUNKSIYASI ---
def parse_text_to_quiz(text):
    blocks = text.strip().split('\n\n')
    parsed_questions = []
    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 2: continue
        
        question = lines[0]
        options = []
        correct_id = 0
        for i, opt in enumerate(lines[1:]):
            if opt.endswith('+'):
                correct_id = i
                options.append(opt[:-1].strip())
            else:
                options.append(opt.strip())
        parsed_questions.append((question, "|".join(options), correct_id))
    return parsed_questions

# --- BUYRUQLAR ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer(f"Salom! Men professional Quiz botman.\n"
                         f"Admin testlarni matn ko'rinishida yuborishi mumkin.\n"
                         f"Foydalanuvchilar esa /quizzes orqali testlarni ko'ra oladi.")

@dp.message_handler(commands=['quizzes'])
async def show_quizzes(message: types.Message):
    sql.execute("SELECT id, question FROM quizes")
    all_quiz = sql.fetchall()
    if not all_quiz:
        await message.answer("Hozircha testlar yo'q.")
        return
    
    keyboard = types.InlineKeyboardMarkup()
    for q in all_quiz:
        keyboard.add(types.InlineKeyboardButton(text=q[1], callback_data=f"start_quiz_{q[0]}"))
    await message.answer("Mavjud testlar ro'yxati:", reply_markup=keyboard)

# --- ADMIN UCHUN AVTOMATIK TEST YARATISH ---
@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID)
async def admin_parse(message: types.Message):
    if '+' not in message.text:
        return # Oddiy xabarlarga javob bermaydi

    questions = parse_text_to_quiz(message.text)
    for q, opt, corr in questions:
        sql.execute("INSERT INTO quizes (question, options, correct_id, owner_id) VALUES (?, ?, ?, ?)",
                    (q, opt, corr, message.from_user.id))
    db.commit()
    await message.answer(f"✅ {len(questions)} ta savol bazaga saqlandi!")

# --- TESTNI BOSHLASH (CALLBACK) ---
@dp.callback_query_handler(lambda c: c.data.startswith('start_quiz_'))
async def process_quiz(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[2]
    sql.execute("SELECT question, options, correct_id FROM quizes WHERE id=?", (quiz_id,))
    q_data = sql.fetchone()
    
    if q_data:
        question, options_raw, correct_id = q_data
        options = options_raw.split('|')
        
        await bot.send_poll(
            chat_id=callback_query.message.chat.id,
            question=question,
            options=options,
            type='quiz',
            correct_option_id=correct_id,
            is_anonymous=False,
            explanation="Bu @QuizBot kabi professional test!", # Tushuntirish qismi
            open_period=30 # 30 soniya vaqt (QuizBot funksiyasi)
        )
    await callback_query.answer()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
