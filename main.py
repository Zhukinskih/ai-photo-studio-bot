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
        "Я допоможу тобі перетворити твоє селфі на розкішну фотосесію зі збереженням твого обличчя.\n\n"
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

# --- Обробка вибору стилю та запуск PhotoMaker ---
async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    style_choice = query.data

    if user_id not in user_data_store or 'photo_url' not in user_data_store[user_id]:
        await query.edit_message_text("❌ Будь ласка, спочатку надішли своє селфі за допомогою команди /start.")
        return

    # Оновлені промпти з акцентом на абсолютну фотореалістичність та природну текстуру шкіри
    styles = {
        "style_beach": {
            "title": "🌴 Тропічний пляж",
            "prompt": "RAW photo, a handsome man img on a tropical beach at sunset, turquoise ocean, natural skin texture, pores, professional DSLR photography, 35mm lens, shot on Canon, 8k resolution, photorealistic"
        },
        "style_mountain": {
            "title": "🏔 Гірське шале",
            "prompt": "RAW photo, a handsome man img in a cozy winter chalet, snowy peaks background, natural skin texture, realistic lighting, professional photography, DSLR, 8k, highly detailed, photorealistic"
        },
        "style_glamour": {
            "title": "✨ Вечірній шик",
            "prompt": "RAW photo, a handsome man img in a luxury penthouse, elegant evening wear, cinematic lighting, natural skin texture, professional portrait photography, 8k, photorealistic"
        }
    }

    selected_style = styles.get(style_choice)
    user_photo_url = user_data_store[user_id]['photo_url']

    await query.edit_message_text(
        f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n"
        f"⏳ ШІ створює фотореалістичну фотосесію (це займе ~30-40 секунд)...",
        parse_mode='Markdown'
    )

    try:
        print(f"🚀 [PhotoMaker] Запуск для стилю: {selected_style['title']} з фото: {user_photo_url}")
        
        output = replicate.run(
            "tencentarc/photomaker:ddfc2b08d209f9fa8c1eca692712918bd449f695dabb4a958da31802a9570fe4",
            input={
                "input_image": user_photo_url,
                "prompt": selected_style["prompt"],
                "negative_prompt": "cartoon, illustration, painting, drawing, art, 3d render, anime, blurry, low quality, distorted face, deformed, bad anatomy, plastic skin",
                "num_steps": 50,
                "num_outputs": 1
            }
        )

        print(f"✅ [Replicate] Успішно отримано результат: {output}")

        if output:
            image_item = output[0]
            image_url = image_item.url if hasattr(image_item, 'url') else str(image_item)
            
            await context.bot.send_photo(
                chat_id=user_id,
                photo=image_url,
                caption=f"✨ Твоя реалістична фотосесія у стилі **{selected_style['title']}** готова!",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(chat_id=user_id, text="❌ Порожній результат від ШІ.")

    except Exception as e:
        print(f"❌ [Replicate Error]: {e}")
        logging.error(f"Replicate Error: {e}")
        await context.bot.send_message(
            chat_id=user_id, 
            text=f"⚠️ Помилка обробки обличчя: {str(e)}"
        )

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

    app_bot = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app_bot.add_handler(CommandHandler("start", start_command))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app_bot.add_handler(CallbackQueryHandler(handle_style_selection))

    print("🚀 Бот для ШІ-фотосесій з PhotoMaker запущений...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
