import os
import telebot
import psycopg2
from telebot import types

# --- SOZLAMALAR ---
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
CHANNEL_ID = "@A_ToolsX" # Kanalingiz userneymini shu yerga yozing

bot = telebot.TeleBot(TOKEN)

# --- OBUNANI TEKSHIRISH FUNKSIYASI ---
def check_sub(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except:
        return True # Xatolik bo'lsa o'tkazib yuboradi

# --- ASOSIY MENYU ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("📚 Mening testlarim"), types.KeyboardButton("📊 Statistika"))
    markup.add(types.KeyboardButton("🆕 Yangi fan testi yaratish"))
    return markup

# --- START KOMANDASI ---
@bot.message_handler(commands=['start'])
def start(message):
    if not check_sub(message.from_user.id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("A'zo bo'lish", url=f"https://t.me/{CHANNEL_ID[1:]}"))
        bot.send_message(message.chat.id, f"🚀 Botdan foydalanish uchun kanalimizga a'zo bo'ling: {CHANNEL_ID}", reply_markup=markup)
        return

    bot.send_message(message.chat.id, "👋 Xush kelibsiz!", reply_markup=main_menu())

# --- TESTLAR RO'YXATI VA ULASHISH TUGMASI ---
@bot.message_handler(func=lambda m: m.text == "📚 Mening testlarim")
def my_tests(message):
    user_id = message.from_user.id
    
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor()
        
        # Admin hamma testni, foydalanuvchi faqat o'zinikini ko'radi
        if user_id == ADMIN_ID:
            cur.execute("SELECT id, title FROM quiz_titles")
        else:
            cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (user_id,))
        
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        bot.send_message(message.chat.id, f"Baza xatosi: {e}")
        return

    if not rows:
        bot.send_message(message.chat.id, "Testlar topilmadi.")
        return

    bot_user = bot.get_me().username
    for q_id, title in rows:
        # ULASHISH TUGMASI MANA SHU YERDA
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_user}?start=run_{q_id}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}"),
            types.InlineKeyboardButton("📤 Ulashish", url=share_url)
        )
        if user_id == ADMIN_ID:
            markup.add(types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{q_id}"))
            
        bot.send_message(message.chat.id, f"📋 Test: <b>{title}</b>", parse_mode="HTML", reply_markup=markup)

# --- BOTNI ISHGA TUSHIRISH ---
if __name__ == "__main__":
    bot.remove_webhook()
    bot.infinity_polling(skip_updates=True)
