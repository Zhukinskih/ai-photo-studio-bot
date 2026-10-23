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

# --- Команда /start з рекомендаціями ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {'photos': []}
    
    welcome_text = (
        "✨ **Вітаю в AI Photo Studio Pro!** ✨\n\n"
        "Створимо твою розкішну професійну фотосесію рівня глянцевих журналів за допомогою передової моделі Flux.2 Pro.\n\n"
        "📸 **Як підготувати фото для ідеального результату:**\n"
        "• Завантаж **3-4 різні фото** (оптимально у форматі **по груди**).\n"
        "• Одне — дивлячись прямо в камеру, інші — під невеликим кутом.\n"
        "• Чітке освітлення, без темних кімнат чи розмиття.\n\n"
        "👇 **Просто надішли ці фото сюди одразу пачкою (альбомом)**, і ми почнемо!"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# --- Встановлення кнопки Menu / Start у Telegram ---
async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Запустити бота та почати фотосесію")
    ])

# --- Обробка завантажених фото (альбоми або по одному) ---
async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        user_data_store[user_id] = {'photos': []}

    photo_file = update.message.photo[-1]
    file = await context.bot.get_file(photo_file.file_id)
    photo_url = file.file_path

    user_data_store[user_id]['photos'].append(photo_url)
    total_photos = len(user_data_store[user_id]['photos'])

    # Коли є мінімум 3 фото, показуємо сітку з 6 стилів (2 на 3)
    if total_photos >= 3:
        keyboard = [
            [
                InlineKeyboardButton("🏔 Панорама Альп", callback_data="style_mountain"),
                InlineKeyboardButton("🛥 Яхта в океані", callback_data="style_beach")
            ],
            [
                InlineKeyboardButton("✨ Пентхаус Манхеттен", callback_data="style_glamour"),
                InlineKeyboardButton("☕️ Вуличне кафе (Париж)", callback_data="style_cafe")
            ],
            [
                InlineKeyboardButton("💼 Executive Портрет", callback_data="style_linkedin"),
                InlineKeyboardButton("🎞 Retro Film 90s", callback_data="style_retro")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🎉 Отримано фото: **{total_photos}**. Успішно збережено!\n\n"
            "Тепер обери стиль для твоєї фотосесії:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"✅ Фото прийнято (загалом: {total_photos}/3). Додай ще кілька, щоб зібрати мінімум 3 референси.",
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

    # 6 трендових промптів без «пластику» з панорамними локаціями
    styles = {
        "style_mountain": {
            "title": "🏔 Панорама Альп (Quiet Luxury)",
            "prompt": "Stunning high-end editorial lifestyle photography ofന്ത് the man from the input images standing on a modern glass balcony of an architectural alpine chalet, breathtaking majestic snowy mountain peaks panorama in the background, golden hour sunset light, wearing a premium cashmere crewneck sweater, shot on Hasselblad 100MP, 35mm lens, natural unpolished skin texture, visible micro-pores, authentic documentary look, 8k, photorealistic"
        },
        "style_beach": {
            "title": "🛥 Яхта в океані (Superyacht)",
            "prompt": "High-end luxury travel magazine photography of the man from the input images relaxing on the deck of a modern superyacht, crystal clear turquoise open ocean panorama stretching to the horizon, bright sunny day, soft sea breeze blowing messy hair, wearing a stylish unbuttoned white linen shirt, shot on Leica S3, 50mm lens, natural skin texture, zero plastic look, 8k resolution"
        },
        "style_glamour": {
            "title": "✨ Пентхаус Манхеттен",
            "prompt": "Cinematic high-end corporate portrait of the man from the input images standing by floor-to-ceiling windows of a luxury Manhattan skyscraper penthouse, dramatic night city skyline bokeh background, moody atmospheric rim lighting, wearing a sharp tailored dark charcoal suit, shot on Sony Alpha 1, 85mm lens, f/1.4, sharp focus, natural skin pores, magazine cover aesthetic"
        },
        "style_cafe": {
            "title": "☕️ Вуличне кафе (Париж)",
            "prompt": "Candid documentary style street photography of the man from the input images sitting at an outdoor terrace of a chic Parisian cafe, holding a coffee cup, soft overcast daylight, blurred romantic European street background, wearing a stylish minimalist black hoodie, shot on Fujifilm X-T5, 35mm lens, natural skin texture, authentic lifestyle editorial"
        },
        "style_linkedin": {
            "title": "💼 Executive Портрет",
            "prompt": "Professional executive corporate headshot of the man from the input images inside a modern high-end architectural office, soft natural window light, confident calm expression, wearing a tailored navy blazer and crisp white shirt, shot on Sony A7R V, 85mm lens, razor-sharp focus on eyes, natural skin texture, Forbes magazine cover style, 8k"
        },
        "style_retro": {
            "title": "🎞 Retro Film 90s",
            "prompt": "Authentic 90s vintage film photography snapshot of the man from the input images outdoors in city, shot on Contax T2, Kodak Portra 400 film grain, natural imperfect lighting, casual unposed candid moment, genuine facial expressions, zero AI smoothness, nostalgic timeless look"
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

    print("🚀 Повноцінний бот на базі Flux.2 Pro запущено успішно...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
