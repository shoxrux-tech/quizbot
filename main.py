import os
import telebot
import psycopg2
import logging
from telebot import types

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- SOZLAMALAR ---
# Render Environment Variables'dan ma'lumotlarni olamiz
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
# Admin ID'ni raqam formatiga o'tkazamiz
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
except (TypeError, ValueError):
    ADMIN_ID = 0

bot = telebot.TeleBot(TOKEN)

# --- ASOSIY MENYU ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📚 Mening testlarim"), types.KeyboardButton("📊 Statistika"))
    markup.add(types.KeyboardButton("🆕 Yangi fan testi yaratish"))
    return markup

# --- START KOMANDASI ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    # Deep linking (ulashish havolasi orqali kirilganda)
    text_parts = message.text.split()
    if len(text_parts) > 1 and text_parts[1].startswith('run_'):
        quiz_id = text_parts[1].replace('run_', '')
        bot.send_message(message.chat.id, f"🚀 Test (ID: {quiz_id}) yuklanmoqda...")
        # Bu yerda testni boshlash funksiyasini chaqirish mumkin
        return

    bot.send_message(
        message.chat.id, 
        "👋 Salom! Test botiga xush kelibsiz. Quyidagilardan birini tanlang:", 
        reply_markup=main_menu()
    )

# --- ADMIN VA ULASHISH FUNKSIYASI ---
@bot.message_handler(func=lambda message: message.text == "📚 Mening testlarim")
def my_quizzes(message):
    user_id = message.from_user.id
    
    try:
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
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Bazaga ulanishda xato: {e}")
        return

    if not rows:
        bot.send_message(message.chat.id, "Hozircha testlar yo'q.")
        return

    bot_info = bot.get_me()
    for q_id, title in rows:
        # ULASHISH TUGMASI (Deep linking orqali)
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_info.username}?start=run_{q_id}"
        
        markup = types.InlineKeyboardMarkup()
        btn_start = types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}")
        btn_share = types.InlineKeyboardButton("📤 Ulashish", url=share_url)
        markup.add(btn_start, btn_share)
        
        # Admin bo'lsangiz o'chirish tugmasi ham chiqadi
        if user_id == ADMIN_ID:
            btn_del = types.InlineKeyboardButton("🗑 O'chirish (Admin)", callback_data=f"del_{q_id}")
            markup.add(btn_del)
            
        bot.send_message(message.chat.id, f"📋 Test nomi: <b>{title}</b>", parse_mode="HTML", reply_markup=markup)

# --- ISHGA TUSHIRISH ---
if __name__ == "__main__":
    logging.info("Bot ishga tushmoqda...")
    # Nizo (Conflict 409) ning oldini olish uchun webhookni tozalaymiz
    bot.remove_webhook()
    # Botni cheksiz so'rov rejimida yoqamiz
    bot.infinity_polling(skip_updates=True)
