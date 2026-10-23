import os
import logging
import asyncio
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Веб-сервер Flask для підтримки 24/7 на Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "AI Photo Studio Bot is alive!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# Словник для тимчасового збереження даних користувача
user_data_store = {}

# --- Команда /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "✨ **Вітаю в AI Photo Studio!** ✨\n\n"
        "Я допоможу тобі створити розкішну тематичну фотосесію за допомогою штучного інтелекту.\n\n"
        "📸 **Будь ласка, надішли 1 чітке селфі**, де добре видно твоє обличчя."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# --- Обробка завантаженого фото ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_file = update.message.photo[-1]
    
    user_data_store[user_id] = {'photo_id': photo_file.file_id}
    
    keyboard = [
        [InlineKeyboardButton("🌴 Тропічний пляж", callback_data="style_beach")],
        [InlineKeyboardButton("🏔 Гірське шале", callback_data="style_mountain")],
        [InlineKeyboardButton("✨ Вечірній шик", callback_data="style_glamour")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📸 **Фото отримано!** Тепер оберемо стиль для твоєї фотосесії:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- Обробка вибору стилю ---
async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    style_choice = query.data

    styles = {
        "style_beach": {
            "title": "🌴 Тропічний пляж",
            "prompt": "luxury aesthetic photoshoot on a tropical beach, turquoise ocean"
        },
        "style_mountain": {
            "title": "🏔 Гірське шале",
            "prompt": "luxury mountain retreat photoshoot, snowy peaks background"
        },
        "style_glamour": {
            "title": "✨ Вечірній шик",
            "prompt": "high-end glamour photoshoot in a penthouse, elegant gown"
        }
    }

    selected_style = styles.get(style_choice)
    
    if user_id in user_data_store:
        user_data_store[user_id]['style'] = selected_style['prompt']
    
    await query.edit_message_text(
        f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n"
        f"⏳ Запускаємо генерацію... (Наступним кроком підключаємо Replicate API)",
        parse_mode='Markdown'
    )

def main():
    keep_alive()

    TOKEN = os.environ.get("TELEGRAM_TOKEN")

    if not TOKEN:
        print("❌ Помилка: Змінна TELEGRAM_TOKEN не знайдена!")
        exit(1)

    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app_bot.add_handler(CallbackQueryHandler(handle_style_selection))

    print("🚀 Бот для ШІ-фотосесій запущений...")
    
    # Сумісний запуск для нових версій Python
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Якщо цикл вже є
        app_bot.run_polling()
    else:
        # Для ізольованих потоків
        app_bot.run_polling()

if __name__ == '__main__':
    main()
