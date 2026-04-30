import os
import telebot
import psycopg2
import logging
from telebot import types

# 1. Loggingni sozlash (xatolarni ko'rish uchun)
logging.basicConfig(level=logging.INFO)

# 2. Render Environment Variables'dan ma'lumotlarni olish
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
# Admin ID'ni xavfsiz olish
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
except:
    ADMIN_ID = 0

# Botni yaratish
bot = telebot.TeleBot(TOKEN)

# 3. Asosiy menyu (Klaviatura)
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("📚 Mening testlarim"), types.KeyboardButton("📊 Statistika"))
    markup.add(types.KeyboardButton("🆕 Yangi fan testi yaratish"))
    return markup

# 4. Start komandasi va Ulashish (Deep Link)
@bot.message_handler(commands=['start'])
def start_handler(message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith('run_'):
        quiz_id = args[1].replace('run_', '')
        bot.send_message(message.chat.id, f"🚀 Test (ID: {quiz_id}) yuklanmoqda...")
        return

    bot.send_message(message.chat.id, "👋 Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu())

# 5. Mening testlarim bo'limi (Admin + Ulashish tugmasi)
@bot.message_handler(func=lambda m: m.text == "📚 Mening testlarim")
def my_quizzes(message):
    user_id = message.from_user.id
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor()
        
        # Admin bo'lsa hamma testni, bo'lmasa faqat o'zinikini ko'radi
        if user_id == ADMIN_ID:
            cur.execute("SELECT id, title FROM quiz_titles")
        else:
            cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (user_id,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bazada xato: {e}")
        return

    if not rows:
        bot.send_message(message.chat.id, "Sizda hali testlar yo'q.")
        return

    bot_username = bot.get_me().username
    for q_id, title in rows:
        # Ulashish havolasi
        share_link = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=run_{q_id}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            types.InlineKeyboardButton("📤 Ulashish", url=share_link)
        )
        # Admin uchun o'chirish tugmasi
        if user_id == ADMIN_ID:
            markup.add(types.InlineKeyboardButton("🗑 O'chirish (Admin)", callback_data=f"del_{q_id}"))
            
        bot.send_message(message.chat.id, f"📁 <b>{title}</b>", parse_mode="HTML", reply_markup=markup)

# 6. Botni xatolarsiz ishga tushirish
if __name__ == "__main__":
    logging.info("Bot Render'da ishga tushmoqda...")
    # Eng muhim joyi: eski ulanishlarni uzish!
    bot.remove_webhook()
    # Faqat bitta pollingni qoldiramiz
    bot.infinity_polling(skip_updates=True)
