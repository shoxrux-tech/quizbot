import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# --- SOZLAMALAR ---
API_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- BAZA BILAN ISHLASH ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS quiz_titles (
        id SERIAL PRIMARY KEY,
        title TEXT,
        owner_id BIGINT,
        timer_seconds INTEGER DEFAULT 30
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS questions (
        id SERIAL PRIMARY KEY,
        quiz_id INTEGER REFERENCES quiz_titles(id) ON DELETE CASCADE,
        question TEXT,
        options TEXT,
        correct_id INTEGER
    )""")
    conn.commit()
    cur.close()
    conn.close()

init_db()

class QuizCreate(StatesGroup):
    waiting_for_title = State()
    waiting_for_timer = State()
    waiting_for_questions = State()

# --- ASOSIY MENYU ---
def main_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("🆕 Yangi test yaratish", "📚 Mening testlarim")
    return keyboard

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer(f"Salom {message.from_user.full_name}!", reply_markup=main_menu())

# --- TEST YARATISH VA O'CHIRISH ---
@dp.message_handler(lambda m: m.text == "🆕 Yangi test yaratish" and m.from_user.id == ADMIN_ID)
async def start_quiz_creation(message: types.Message):
    await QuizCreate.waiting_for_title.set()
    await message.answer("Test nomini kiriting:", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(state=QuizCreate.waiting_for_title)
async def set_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await QuizCreate.waiting_for_timer.set()
    await message.answer("Har bir savol uchun vaqtni kiriting (soniyalarda, masalan: 30):")

@dp.message_handler(state=QuizCreate.waiting_for_timer)
async def set_timer(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting!")
        return
    await state.update_data(timer=int(message.text), questions=[])
    await QuizCreate.waiting_for_questions.set()
    await message.answer("Endi savollarni tashlang va tugatgach <b>/done</b> bosing.")

@dp.message_handler(state=QuizCreate.waiting_for_questions)
async def process_questions(message: types.Message, state: FSMContext):
    if message.text == "/done":
        data = await state.get_data()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO quiz_titles (title, owner_id, timer_seconds) VALUES (%s, %s, %s) RETURNING id", 
                    (data['title'], message.from_user.id, data['timer']))
        quiz_id = cur.fetchone()[0]
        for q, opt, corr in data['questions']:
            cur.execute("INSERT INTO questions (quiz_id, question, options, correct_id) VALUES (%s, %s, %s, %s)",
                        (quiz_id, q, "|".join(opt), corr))
        conn.commit()
        cur.close()
        conn.close()
        await state.finish()
        await message.answer(f"✅ '{data['title']}' saqlandi!", reply_markup=main_menu())
        return

    # Savollarni parsing qilish (avvalgi mantiq)
    blocks = message.text.strip().split('\n\n')
    new_qs = []
    for block in blocks:
        lines = block.split('\n')
        if len(lines) < 2: continue
        opts, corr_id = [], 0
        for i, o in enumerate(lines[1:]):
            if o.endswith('+'):
                corr_id = i
                opts.append(o[:-1].strip())
            else: opts.append(o.strip())
        new_qs.append((lines[0], opts, corr_id))
    
    data = await state.get_data()
    data['questions'].extend(new_qs)
    await state.update_data(questions=data['questions'])
    await message.answer(f"📥 {len(new_qs)} ta savol olindi. Davom eting yoki /done.")

# --- TESTLARNI BOSHQARISH ---
@dp.message_handler(lambda m: m.text == "📚 Mening testlarim")
async def my_quizzes(message: types.Message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (message.from_user.id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await message.answer("Testlar topilmadi.")
        return

    for q_id, title in rows:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("▶️ Testni boshlash", callback_data=f"run_{q_id}"),
            types.InlineKeyboardButton("🗑 Testni o'chirish", callback_data=f"del_{q_id}"),
            types.InlineKeyboardButton("📤 Ulashish", url=f"https://t.me/share/url?url=https://t.me/{(await bot.get_me()).username}?start=quiz_{q_id}")
        )
        await message.answer(f"📋 <b>{title}</b>", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('del_'))
async def delete_quiz(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[1]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM quiz_titles WHERE id=%s", (quiz_id,))
    conn.commit()
    cur.close()
    conn.close()
    await callback_query.message.delete()
    await callback_query.answer("Test o'chirildi!")

# --- AVTOMATIK TEST O'TKAZISH LOGIKASI ---
@dp.callback_query_handler(lambda c: c.data.startswith('run_'))
async def run_quiz_handler(callback_query: types.CallbackQuery):
    quiz_id = callback_query.data.split('_')[1]
    await callback_query.answer("Test boshlanmoqda...")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT timer_seconds FROM quiz_titles WHERE id=%s", (quiz_id,))
    timer = cur.fetchone()[0]
    cur.execute("SELECT question, options, correct_id FROM questions WHERE quiz_id=%s", (quiz_id,))
    questions = cur.fetchall()
    cur.close()
    conn.close()

    for q, opts_raw, corr_id in questions:
        poll = await bot.send_poll(
            chat_id=callback_query.message.chat.id,
            question=q,
            options=opts_raw.split('|'),
            type='quiz',
            correct_option_id=corr_id,
            is_anonymous=False,
            open_period=timer # Vaqt tugagach yopiladi
        )
        await asyncio.sleep(timer + 2) # Vaqt tugashini kutadi + 2 soniya pauza

    await bot.send_message(callback_query.message.chat.id, "🏁 Test yakunlandi!")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
