import os
import logging
import asyncio
import replicate
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
    
    # Отримуємо посилання на файл від Telegram
    file = await context.bot.get_file(photo_file.file_id)
    photo_url = file.file_path

    user_data_store[user_id] = {'photo_url': photo_url}
    
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

# --- Обробка вибору стилю та запуск Replicate ---
async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    style_choice = query.data

    if user_id not in user_data_store or 'photo_url' not in user_data_store[user_id]:
        await query.edit_message_text("❌ Будь ласка, спочатку надішли своє селфі за допомогою команди /start.")
        return

    styles = {
        "style_beach": {
            "title": "🌴 Тропічний пляж",
            "prompt": "luxurious aesthetic photoshoot of a beautiful glamorous woman on a tropical beach at sunset, turquoise ocean, professional fashion photography, 8k"
        },
        "style_mountain": {
            "title": "🏔 Гірське шале",
            "prompt": "luxury mountain retreat photoshoot, elegant woman in a cozy winter chalet, snowy peaks background, high-end fashion magazine style, 8k"
        },
        "style_glamour": {
            "title": "✨ Вечірній шик",
            "prompt": "high-end glamour photoshoot in a luxury penthouse, elegant evening gown, cinematic lighting, professional studio portraits, 8k"
        }
    }

    selected_style = styles.get(style_choice)

    await query.edit_message_text(
        f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n"
        f"⏳ Штучний інтелект створює твою розкішну фотосесію...",
        parse_mode='Markdown'
    )

    try:
        print(f"🚀 [Replicate] Запуск генерації для стилю: {selected_style['title']}")
        
        # Запускаємо генерацію через модель Stable Diffusion XL на Replicate
        output = replicate.run(
            "stability-ai/sdxl:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
            input={
                "prompt": selected_style["prompt"],
                "negative_prompt": "ugly, blurry, low quality, distorted face",
                "width": 768,
                "height": 1024,
                "num_outputs": 1
            }
        )

        print(f"✅ [Replicate] Успішно отримано результат: {output}")

        if output and len(output) > 0:
            image_url = output[0]
            await context.bot.send_photo(
                chat_id=user_id,
                photo=image_url,
                caption=f"✨ Твоя фотосесія у стилі **{selected_style['title']}** готова!",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(chat_id=user_id, text="❌ Порожній результат від ШІ.")

    except Exception as e:
        print(f"❌ [Replicate Error]: {e}")
        logging.error(f"Replicate Error: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"⚠️ Помилка ШІ: {str(e)}")

def main():
    keep_alive()

    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
        print("❌ Помилка: Змінна TELEGRAM_TOKEN не знайдена!")
        exit(1)

    # Примусово створюємо цикл подій для Python 3.14+
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_closed():
            raise RuntimeError()
    except Exception:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app_bot.add_handler(CallbackQueryHandler(handle_style_selection))

    print("🚀 Бот для ШІ-фотосесій з підтримкою Replicate запущений...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
