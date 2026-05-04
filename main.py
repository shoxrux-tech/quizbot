import os
import telebot
from telebot import types

# Bot tokenini sozlash
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(func=lambda m: m.text == "📚 Mening testlarim")
def show_my_quizzes(message):
    # Bu yerda bazadan ma'lumotlarni olasiz (misol uchun mock ma'lumot)
    quizzes = [
        {"id": 123, "title": "Kimyo testi"},
        {"id": 124, "title": "Fizika testi"}
    ]
    
    # Bot username'ini olish (havola yaratish uchun kerak)
    bot_info = bot.get_me()
    bot_username = bot_info.username

    for quiz in quizzes:
        quiz_id = quiz['id']
        title = quiz['title']
        
        # 🔗 Ulashish uchun maxsus havola (Deep Link)
        # Bu havola bosilganda botga /start run_123 buyrug'i boradi
        share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=run_{quiz_id}&text=Do'stim, mana bu testni yechib ko'r: {title}"

        markup = types.InlineKeyboardMarkup()
        
        # 1. Boshlash tugmasi
        btn_start = types.InlineKeyboardButton("🚀 Boshlash", callback_data=f"run_{quiz_id}")
        
        # 2. ULASHISH TUGMASI (Mana shu yerda xato bo'lgan bo'lishi mumkin)
        # Bu tugma foydalanuvchiga chat tanlash imkonini beradi
        btn_share = types.InlineKeyboardButton("📤 Ulashish", url=share_url)
        
        # 3. O'chirish tugmasi
        btn_delete = types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"del_{quiz_id}")

        # Tugmalarni joylashtirish
        markup.add(btn_start, btn_share) # Bir qatorga ikkita tugma
        markup.add(btn_delete)           # Pastki qatorga bitta tugma

        bot.send_message(message.chat.id, f"📂 **{title}**", parse_mode="Markdown", reply_markup=markup)

# Botni ishga tushirish
if __name__ == "__main__":
    bot.infinity_polling()
