import os
import telebot
import logging

# Настройка логирования, чтобы видеть ошибки в панели Render
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Твои обработчики команд (например, /start)
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я снова в строю.")

# Блок запуска
if __name__ == "__main__":
    logging.info("Удаление старых соединений...")
    # Это критически важно для исправления ошибки 409
    bot.remove_webhook()
    
    logging.info("Бот запущен...")
    # skip_updates=True заставит бота игнорировать сообщения, 
    # присланные, пока он был выключен (чтобы не спамить в ответ)
    bot.infinity_polling(skip_updates=True)
