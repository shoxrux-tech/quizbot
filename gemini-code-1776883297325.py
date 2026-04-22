import telebot
import sqlite3
import json
import re
from telebot import types
from flask import Flask
from threading import Thread

# DIQQAT: BotFather-dan yangi token olib shu yerga qo'ying!
TOKEN = '8533049259:AAGlLQaMGq9RTvcui9iyHwz9yi9ydzNjpLs' 
bot = telebot.TeleBot(TOKEN)

# Render-da botni o'chib qolishdan asrash uchun kichik server
app = Flask('')
@app.route('/')
def home(): return "Bot ishlayapti!"
def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

def init_db():
    conn = sqlite3.connect('quiz_bot.db')
    conn.execute('CREATE TABLE IF NOT EXISTS quizzes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, quiz_data TEXT)')
    conn.commit()
    conn.close()

# --- SIZNING TUGMALARINGIZ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("📚 Yangi fan testi yaratish")
    m.row("📂 Mening testlarim", "📊 Statistika")
    m.row("👨‍💻 Admin")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    bot.send_message(message.chat.id, "👋 Xush kelibsiz!", reply_markup=main_menu())

# (Boshqa barcha funksiyalar: collect, save va h.k.larni shu yerga qo'shing)

if __name__ == "__main__":
    init_db()
    keep_alive() # Render uchun veb-serverni yoqish
    bot.polling(none_stop=True)