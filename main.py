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

# Словник для тимчасового збереження даних користувача та його референсів
user_data_store = {}

# --- Команда /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {'photos': []}
    
    welcome_text = (
        "✨ **Вітаю в AI Photo Studio Pro!** ✨\n\n"
        "Створимо твою розкішну професійну фотосесію рівня глянцевих журналів.\n\n"
        "📸 **Надішли 3-4 своїх чітких фото (селфі) одразу в одному повідомленні (альбомом)**, щоб нейромережа ідеально передала твою зовнішність."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# --- Встановлення кнопки Menu / Start у Telegram ---
async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Запустити бота та почати фотосесію")
    ])

# --- Обробка завантажених фото (підтримка альбомів або кількох фото) ---
async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        user_data_store[user_id] = {'photos': []}

    # Отримуємо найкращу якість завантаженого фото
    photo_file = update.message.photo[-1]
    file = await context.bot.get_file(photo_file.file_id)
    photo_url = file.file_path

    # Додаємо у сховище
    user_data_store[user_id]['photos'].append(photo_url)
    total_photos = len(user_data_store[user_id]['photos'])

    # Якщо користувач закинув кілька фото (наприклад, вже є мінімум 3), показуємо меню вибору стилів
    if total_photos >= 3:
        keyboard = [
            [InlineKeyboardButton("🏔 Панорама гірського шале (Luxury Alps)", callback_data="style_mountain")],
            [InlineKeyboardButton("🛥 Яхта у відкритому океані (Superyacht)", callback_data="style_beach")],
            [InlineKeyboardButton("✨ Новий Манхеттен (Penthouse Skyline)", callback_data="style_glamour")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🎉 Отримано фото: **{total_photos}**. Успішно збережено!\n\n"
            "Тепер обери стиль для ефектної фотосесії:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"✅ Фото прийнято (загалом: {total_photos}/3). Додай ще кілька, щоб досягти мінімуму в 3 фотографії.",
            parse_mode='Markdown'
        )

# --- Обробка вибору стилю та генерація через Flux-2-Pro ---
async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    style_choice = query.data

    if user_id not in user_data_store or len(user_data_store[user_id].get('photos', [])) < 3:
        await query.edit_message_text("❌ Будь ласка, спочатку завантаж щонайменше 3 фото за допомогою команди /start.")
        return

    # Розкішні, панорамні «Вау»-промпти без мультяшності та дивного одягу
    styles = {
        "style_mountain": {
            "title": "🏔 Панорама гірського шале",
            "prompt": "Stunning high-end editorial lifestyle photography of the man from the input images standing on a modern glass balcony of an architectural alpine chalet, breathtaking majestic snowy mountain peaks panorama in the background, golden hour sunset light, wearing a premium cashmere crewneck sweater, shot on Hasselblad 100MP, 35mm lens, f/2.0, natural unpolished skin texture, visible micro-pores, authentic documentary look, 8k, photorealistic"
        },
        "style_beach": {
            "title": "🛥 Яхта у відкритому океані",
            "prompt": "High-end luxury travel magazine photography of the man from the input images relaxing on the deck of a modern superyacht, crystal clear turquoise open ocean panorama stretching to the horizon, bright sunny day, soft sea breeze blowing messy hair, wearing a stylish unbuttoned white linen shirt, shot on Leica S3, 50mm lens, natural skin texture, zero plastic look, 8k resolution"
        },
        "style_glamour": {
            "title": "✨ Новий Манхеттен (Penthouse)",
            "prompt": "Cinematic high-end corporate portrait of the man from the input images standing by floor-to-ceiling windows of a luxury Manhattan skyscraper penthouse, dramatic night city skyline bokeh background, moody atmospheric rim lighting, wearing a sharp tailored dark charcoal suit, shot on Sony Alpha 1, 85mm lens, f/1.4, sharp focus, natural skin pores, magazine cover aesthetic"
        }
    }

    selected_style = styles.get(style_choice)
    user_photos = user_data_store[user_id]['photos']

    await query.edit_message_text(
        f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n"
        f"⏳ Створюємо шедевр через Flux.2 Pro (це займе близько 20-30 секунд)...",
        parse_mode='Markdown'
    )

    try:
        print(f"🚀 [Flux-2-Pro] Генерація для стилю: {selected_style['title']} з {len(user_photos)} референсами")
        
        output = replicate.run(
            "black-forest-labs/flux-2-pro",
            input={
                "prompt": selected_style["prompt"],
                "input_images": user_photos,
                "aspect_ratio": "4:5",
                "resolution": "1 MP"
            }
        )

        final_image_url = output.url if hasattr(output, 'url') else str(output)
        print(f"✅ [Flux-2-Pro] Успішно створено: {final_image_url}")

        if final_image_url:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=str(final_image_url),
                caption=f"🔥 Твоя приголомшлива фотосесія у стилі **{selected_style['title']}** готова! Готуй лайки в соцмережах 😉",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(chat_id=user_id, text="❌ Порожній результат від моделі генерації.")

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
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photos))
    app_bot.add_handler(CallbackQueryHandler(handle_style_selection))

    print("🚀 Бот на базі Flux.2 Pro занесено в оновлену версію...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
