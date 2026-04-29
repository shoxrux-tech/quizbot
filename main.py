import os
import logging
import psycopg2 # PostgreSQL uchun kutubxona
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# --- SOZLAMALAR ---
# Token va Baza manzilini Render'ning Environment Variables bo'limidan oladi
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', 12345678)) # O'z ID'ingizni yozing

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- BAZA BILAN ISHLASH (PostgreSQL) ---
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS quizes (
        id SERIAL PRIMARY KEY,
        question TEXT,
        options TEXT,
        correct_id INTEGER,
        owner_id BIGINT
    )""")
    conn.commit()
    cur.close()
    conn.close()

# Bot ishga tushganda bazani tayyorlash
init_db()

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

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Salom! Men o'chmas xotirali Quiz botman. \nAdmin test tashlashi mumkin.")

@dp.message_handler(commands=['quizzes'])
async def show_quizzes(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, question FROM quizes")
    all_quiz = cur.fetchall()
    cur.close()
    conn.close()

    if not all_quiz:
        await message.answer("Hozircha testlar yo'q.")
        return
    
    keyboard = types.InlineKeyboardMarkup()
    for q in all_quiz:
        keyboard.add(types.InlineKeyboardButton(text=q[1], callback_data=f"quiz_{q[0]}"))
    await message.answer("Mavjud testlar:", reply_markup=keyboard)

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID)
async def admin_parse(message: types.Message):
    if '+' not in message.text: return

    questions = parse_text_to_quiz(message.text)
    conn = get_db_connection()
    cur = conn.cursor()
    for q, opt, corr in questions:
        cur.execute("INSERT INTO quizes (question, options, correct_id, owner_id) VALUES (%s, %s, %s, %s)",
                    (q, opt, corr, message.from_user.id))
    conn.commit()
    cur.close()
    conn.close()
    await message.answer(f"✅ {len(questions)} ta savol bazaga saqlandi va o'chib ketmaydi!")

@dp.callback_query_handler(lambda c: c.data.startswith('quiz_'))
async def process_quiz(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[1]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT question, options, correct_id FROM quizes WHERE id=%s", (quiz_id,))
    q_data = cur.fetchone()
    cur.close()
    conn.close()
    
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
            explanation="To'g'ri javob belgilandi!",
            open_period=30
        )
    await callback_query.answer()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
