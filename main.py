import os
import telebot
import logging

# 1. Настраиваем логирование, чтобы видеть подробности в панели Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Получаем токен из переменных окружения
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Пример простого обработчика команды /start
@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "Привет! Бот успешно запущен и готов к работе.")

# 3. Основной блок запуска
if __name__ == "__main__":
    try:
        logger.info("Удаление старых соединений (webhook)...")
        # Этот шаг критически важен для исправления ошибки 409
        bot.remove_webhook()
        
        logger.info("Запуск бота в режиме infinity_polling...")
        # skip_updates=True проигнорирует сообщения, которые прислали, пока бот был выключен
        bot.infinity_polling(skip_updates=True)
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске: {e}")
