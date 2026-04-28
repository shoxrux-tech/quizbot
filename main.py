import os
import telebot
import psycopg2
import json
import time
import threading
from telebot import types

# --- SOZLAMALAR ---
TOKEN = "8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs"
DATABASE_URL = os.getenv("postgresql://quizdb_user:g9nB6DRVNQgHtWg2LI56KaWQcRo8CPCf@dpg-d7ks1157vvec739ms05g-a.ohio-postgres.render.com/quizdb_wgm2")
bot = telebot.TeleBot(TOKEN)

def get_db():
    return psycopg2.connect(DATABASE_URL)

# --- ASOSIY MENYU ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📚 Yangi test yaratish", "📂 Mening testlarim")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    # Foydalanuvchi link orqali kelganini tekshirish
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('run_'):
        q_id = args[1].split('_')[1]
        markup = types.InlineKeyboardMarkup()
        markup.row(types.InlineKeyboardButton("15 sek", callback_data=f"t_15_{q_id}"),
                   types.InlineKeyboardButton("30 sek", callback_data=f"t_30_{q_id}"))
        return bot.send_message(message.chat.id, "⏱ Vaqtni tanlang:", reply_markup=markup)
    
    bot.send_message(message.chat.id, "🎯 Bot ishga tushdi!", reply_markup=main_menu())

# --- MENYULARGA JAVOB BERISH ---
@bot.message_handler(func=lambda m: m.text == "📚 Yangi test yaratish")
def create_quiz_start(message):
    bot.send_message(message.chat.id, "📖 Yangi test uchun fan nomini kiriting:")
    # Bu yerda register_next_step_handler qo'shiladi

@bot.message_handler(func=lambda m: m.text == "📂 Mening testlarim")
def show_my_tests(message):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id, title FROM quizzes WHERE user_id = %s', (message.from_user.id,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        
        if not rows:
            return bot.send_message(message.chat.id, "Sizda testlar yo'q.")
            
        for r in rows:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{r[0]}"))
            markup.add(types.InlineKeyboardButton("📤 Ulashish", switch_inline_query=f"share_{r[0]}"))
            bot.send_message(message.chat.id, f"📂 **{r[1]}**", reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"Xato: {e}")

# --- BOTNI TO'XTAB QOLMAYDIGAN QILIB YOQISH ---
if __name__ == '__main__':
    print("Bot menyulari yuklanmoqda...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
