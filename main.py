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
    # Скидаємо/ініціалізуємо список фото для нового сеансу
    user_data_store[user_id] = {'photos': []}
    
    welcome_text = (
        "✨ **Вітаю в AI Photo Studio Pro!** ✨\n\n"
        "Створимо твою професійну фотосесію за допомогою передової моделі Flux.2 Pro.\n\n"
        "📸 **Будь ласка, надішли 3 різні чіткі селфі** (по черзі), щоб нейромережа ідеально запам'ятала твої риси обличчя під різними кутами.\n\n"
        "Завантажено фото: **0 / 3**"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# --- Встановлення кнопки Menu / Start у Telegram ---
async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Запустити бота та почати фотосесію")
    ])

# --- Обробка завантажених фото (збираємо до 3 штук) ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        user_data_store[user_id] = {'photos': []}

    photo_file = update.message.photo[-1]
    file = await context.bot.get_file(photo_file.file_id)
    photo_url = file.file_path

    # Додаємо фото у список референсів користувача
    user_data_store[user_id]['photos'].append(photo_url)
    current_count = len(user_data_store[user_id]['photos'])

    if current_count < 3:
        await update.message.reply_text(
            f"✅ Фото #{current_count} прийнято!\n"
            f"Будь ласка, надішли ще **{3 - current_count}** фото.",
            parse_mode='Markdown'
        )
    else:
        # Коли зібрано всі 3 фото, показуємо меню вибору стилів
        keyboard = [
            [InlineKeyboardButton("🌴 Тропічний пляж (Editorial)", callback_data="style_beach")],
            [InlineKeyboardButton("🏔 Гірське шале (Lifestyle)", callback_data="style_mountain")],
            [InlineKeyboardButton("✨ Вечірній шик (Dark Moody)", callback_data="style_glamour")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🎉 **Усі 3 референси успішно збережено!**\n\n"
            "Тепер обери стиль для твоєї професійної фотосесії:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

# --- Обробка вибору стилю та генерація через Flux-2-Pro ---
async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    style_choice = query.data

    if user_id not in user_data_store or len(user_data_store[user_id].get('photos', [])) < 3:
        await query.edit_message_text("❌ Будь ласка, спочатку надішли 3 селфі за допомогою команди /start.")
        return

    # Оновлені професійні промпти з акцентом на природність, пори та плівкову текстуру (без "пластику")
    styles = {
        "style_beach": {
            "title": "🌴 Тропічний пляж",
            "prompt": "Raw unfiltered candid editorial photography of the man from the input images on a tropical beach at sunset, authentic skin imperfections, visible pores, natural skin texture, slight sweat, unstyled messy hair blowing in the wind, shot on 35mm film, Kodak Portra 400, Fujifilm color science, authentic documentary style, zero AI smoothness"
        },
        "style_mountain": {
            "title": "🏔 Гірське шале",
            "prompt": "Raw unfiltered candid lifestyle photography of the man from the input images inside an alpine wooden chalet, natural unpolished skin texture, visible pores, subtle stubble, authentic facial asymmetry, casual pose, shot on Leica M10, 50mm lens, natural window daylight, documentary photography, no plastic skin"
        },
        "style_glamour": {
            "title": "✨ Вечірній шик",
            "prompt": "Raw unfiltered corporate portrait of the man from the input images in a luxury penthouse, wearing a charcoal grey suit, authentic skin texture with natural pores and tiny imperfections, realistic micro-details, shot on Sony Alpha 1, natural indoor ambient light, professional editorial journalism style, zero CGI look"
        }
    }

    selected_style = styles.get(style_choice)
    user_photos = user_data_store[user_id]['photos']

    await query.edit_message_text(
        f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n"
        f"⏳ Запускаємо генерацію через Flux.2 Pro з урахуванням твоїх референсів (це займе близько 20-30 секунд)...",
        parse_mode='Markdown'
    )

    try:
        print(f"🚀 [Flux-2-Pro] Генеруємо фото для стилю: {selected_style['title']} з {len(user_photos)} референсами")
        
        # Виклик моделі flux-2-pro з передачею списку референсних фото
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
                caption=f"✨ Твоя професійна фотосесія у стилі **{selected_style['title']}** готова!",
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
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app_bot.add_handler(CallbackQueryHandler(handle_style_selection))

    print("🚀 Бот на базі Flux.2 Pro та мульти-референсів запущений...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
