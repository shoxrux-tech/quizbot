import os
import telebot
import psycopg2
from telebot import types

# 1. Настройка данных
# Берем токен и данные базы из настроек Render
TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
# Твой ID (укажи его в Environment Variables на Render)
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

bot = telebot.TeleBot(TOKEN)

# 2. Главное меню
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("📚 Mening testlarim")
    btn2 = types.KeyboardButton("📊 Statistika")
    btn3 = types.KeyboardButton("🆕 Yangi fan testi yaratish")
    markup.add(btn1, btn2)
    markup.add(btn3)
    return markup

# 3. Обработка команды /start
@bot.message_handler(commands=['start'])
def start(message):
    # Проверка: если человек пришел по ссылке (start=run_123)
    if len(message.text.split()) > 1:
        payload = message.text.split()[1]
        if payload.startswith('run_'):
            quiz_id = payload.split('_')[1]
            bot.send_message(message.chat.id, f"🚀 Test yuklanmoqda (ID: {quiz_id})...")
            return

    bot.send_message(
        message.chat.id, 
        "👋 Salom! Test botiga xush kelibsiz.", 
        reply_markup=main_menu()
    )

# 4. Список тестов (Кнопки поделиться и Админка)
@bot.message_handler(func=lambda message: message.text == "📚 Mening testlarim")
def show_quizzes(message):
    user_id = message.from_user.id
    
    # Подключаемся к базе данных
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    
    # Если ты админ — видишь всё. Если нет — только свои тесты.
    if user_id == ADMIN_ID:
        cur.execute("SELECT id, title FROM quiz_titles")
    else:
        cur.execute("SELECT id, title FROM quiz_titles WHERE owner_id=%s", (user_id,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "Hozircha testlar yo'q.")
        return

    bot_username = bot.get_me().username
    for q_id, title in rows:
        # Ссылка для кнопки "Поделиться"
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=run_{q_id}"
        
        markup = types.InlineKeyboardMarkup()
        btn_start = types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{q_id}")
        btn_share = types.InlineKeyboardButton("📤 Ulashish", url=share_url)
        markup.add(btn_start, btn_share)
        
        # Если админ — добавляем кнопку удаления
        if user_id == ADMIN_ID:
            btn_del = types.InlineKeyboardButton("🗑 O'chirish (Admin)", callback_data=f"del_{q_id}")
            markup.add(btn_del)
            
        bot.send_message(message.chat.id, f"📋 Test: *{title}*", parse_mode="Markdown", reply_markup=markup)

# 5. Запуск бота
if __name__ == "__main__":
    print("Бот запускается...")
    # Удаляем вебхуки, чтобы не было конфликта 409
    bot.remove_webhook()
    # Запускаем бесконечный опрос
    bot.infinity_polling(skip_updates=True)
