import os
import logging
import asyncio
import replicate
from flask import Flask
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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
        "Я допоможу тобі створити круту фотосесію із точним перенесенням твого обличчя.\n\n"
        "📸 **Будь ласка, надішли 1 чітке селфі**, де добре видно твоє обличчя."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# --- Встановлення кнопки Menu / Start у Telegram ---
async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Запустити бота та створити фотосесію")
    ])

# --- Обробка завантаженого фото ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_file = update.message.photo[-1]
    
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
        "📸 **Селфі успішно збережено!** Тепер оберемо стиль для твоєї фотосесії:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- Обробка вибору стилю та запуск генерації + Face Swap ---
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
            "prompt": "RAW photo, a handsome man on a tropical beach at sunset, turquoise ocean, natural skin texture, professional DSLR photography, 35mm lens, 8k, photorealistic"
        },
        "style_mountain": {
            "title": "🏔 Гірське шале",
            "prompt": "RAW photo, a handsome man in a cozy winter chalet, snowy peaks background, natural skin texture, professional photography, DSLR, 8k, photorealistic"
        },
        "style_glamour": {
            "title": "✨ Вечірній шик",
            "prompt": "RAW photo, a handsome man in a luxury penthouse, elegant evening wear, cinematic lighting, natural skin texture, professional portrait photography, 8k, photorealistic"
        }
    }

    selected_style = styles.get(style_choice)
    user_photo_url = user_data_store[user_id]['photo_url']

    await query.edit_message_text(
        f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n"
        f"⏳ Крок 1/2: Генеруємо базове фото за допомогою SDXL...",
        parse_mode='Markdown'
    )

    try:
        # Крок 1: Генеруємо якісний фон через SDXL
        print(f"🚀 [Gen] Генеруємо базове зображення через SDXL для стилю: {selected_style['title']}")
        base_output = replicate.run(
            "stability-ai/sdxl:7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc",
            input={
                "width": 768,
                "height": 960,
                "prompt": selected_style["prompt"],
                "refine": "expert_ensemble_refiner",
                "apply_watermark": False,
                "num_inference_steps": 25
            }
        )

        base_image_item = base_output[0] if isinstance(base_output, list) else base_output
        base_image_url = base_image_item.url if hasattr(base_image_item, 'url') else str(base_image_item)
        print(f"✅ [Gen] Базове фото створено: {base_image_url}")

        await context.bot.send_message(
            chat_id=user_id,
            text=f"⏳ Крок 2/2: Пауза кілька секунд (обхід лімітів API) і переносимо обличчя..."
        )

        # Невелика пауза (7 секунд), щоб охолодити ліміти API безкоштовного акаунта
        await asyncio.sleep(7)

        # Крок 2: Точна заміна обличчя
        print(f"🚀 [FaceSwap] Запуск заміни обличчя...")
        swap_output = replicate.run(
            "cdingram/face-swap:d1d6ea8c8be89d664a07a457526f7128109dee7030fdac424788d762c71ed111",
            input={
                "swap_image": user_photo_url,      
                "input_image": base_image_url      
            }
        )

        print(f"✅ [FaceSwap] Успішно! Результат: {swap_output}")

        if swap_output:
            final_image_url = swap_output.url if hasattr(swap_output, 'url') else (swap_output[0] if isinstance(swap_output, list) else str(swap_output))
            
            await context.bot.send_photo(
                chat_id=user_id,
                photo=str(final_image_url),
                caption=f"✨ Твоя реалістична фотосесія у стилі **{selected_style['title']}** готова!",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(chat_id=user_id, text="❌ Порожній результат від моделі заміни обличчя.")

    except Exception as e:
        print(f"❌ [Error]: {e}")
        logging.error(f"Error: {e}")
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"⚠️ Помилка обробки: {str(e)}"
        )

def main():
    keep_alive()

    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
        print("❌ Помилка: Змінна TELEGRAM_TOKEN не знайдена!")
        exit(1)

    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop.is_closed():
            raise RuntimeError()
    except Exception:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app_bot = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app_bot.add_handler(CallbackQueryHandler(handle_style_selection))

    print("🚀 Бот з SDXL та Face Swap запущений...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
