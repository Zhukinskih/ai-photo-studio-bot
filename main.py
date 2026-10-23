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
        "• Завантаж **3-4 різні фото** у форматі **по груди** (середній план).\n"
        "• Одне — дивлячись прямо в камеру, інші — під невеликим кутом.\n"
        "• Чітке освітлення, без темних кімнат чи розмиття.\n\n"
        "👇 **Просто надішли ці фото сюди пачкою або файлами**, і ми почнемо!"
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

# --- Встановлення кнопки Menu / Start у Telegram ---
async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Запустити бота та почати фотосесію")
    ])

# --- Обробка завантажених фото або файлів-картинок ---
async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data_store:
        user_data_store[user_id] = {'photos': []}

    photo_url = None

    if update.message.photo:
        photo_file = update.message.photo[-1]
        file = await context.bot.get_file(photo_file.file_id)
        photo_url = file.file_path
    elif update.message.document:
        doc = update.message.document
        if doc.mime_type and doc.mime_type.startswith('image/'):
            file = await context.bot.get_file(doc.file_id)
            photo_url = file.file_path
        else:
            await update.message.reply_text("⚠️ Будь ласка, завантажуйте зображення у форматі фото або файлів-картинок (jpg, png).")
            return
    else:
        return

    if photo_url:
        user_data_store[user_id]['photos'].append(photo_url)
    
    sources_count = len(user_data_store[user_id]['photos'])

    if sources_count >= 3:
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
            f"🎉 Отримано фото: **{sources_count}**. Успішно збережено!\n\n"
            "Тепер обери стиль для твоєї фотосесії:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"✅ Фото прийнято (загалом: {sources_count}/3). Додай ще кілька, щоб зібрати мінімум 3 референси.",
            parse_mode='Markdown'
        )

# --- Функція для виведення меню стилів ---
async def show_styles_menu(chat_id, context):
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
    await context.bot.send_message(
        chat_id=chat_id, 
        text="🎨 Обери стиль для твоєї фотосесії:", 
        reply_markup=reply_markup, 
        parse_mode='Markdown'
    )

# --- Обробка вибору стилю та асинхронна генерація через Flux-2-Pro ---
async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    # Перевірка на кнопки посткабінету
    if data == "action_change_style":
        if user_id not in user_data_store or len(user_data_store[user_id].get('photos', [])) < 3:
            await context.bot.send_message(chat_id=user_id, text="❌ Спочатку завантаж фото через /start.")
            return
        await show_styles_menu(user_id, context)
        return

    if data == "action_new_photos":
        user_data_store[user_id] = {'photos': []}
        await context.bot.send_message(
            chat_id=user_id,
            text="🔄 Сеанс скинуто.\n\n📸 Надішли **3-4 нові фото (по груди)** пачкою або файлами, щоб почати спочатку.",
            parse_mode='Markdown'
        )
        return

    style_choice = data

    if user_id not in user_data_store or len(user_data_store[user_id].get('photos', [])) < 3:
        await context.bot.send_message(chat_id=user_id, text="❌ Будь ласка, спочатку завантаж щонайменше 3 фото за допомогою команди /start.")
        return

    styles = {
        "style_mountain": {
            "title": "🏔 Панорама Альп (Quiet Luxury)",
            "prompt": "High-end editorial waist-up medium portrait of the man from the input images standing on a modern glass balcony of an architectural alpine chalet, breathtaking majestic snowy mountain peaks panorama bathed in soft golden hour sunset light strictly on the background, natural neutral front daylight illuminating the subject's face with accurate skin tones, wearing a premium cashmere crewneck sweater, shot on Hasselblad 100MP, 35mm lens, natural unpolished skin texture, visible micro-pores, 8k, photorealistic"
        },
        "style_beach": {
            "title": "🛥 Яхта в океані (Superyacht)",
            "prompt": "High-end luxury travel magazine waist-up medium portrait of the man from the input images relaxing on the deck of a modern superyacht, crystal clear turquoise open ocean panorama with a soft warm sunset glowing far on the horizon background, natural bright daytime light on the subject's face, accurate natural skin tones, wearing a stylish unbuttoned white linen shirt, shot on Leica S3, 50mm lens, zero plastic look, 8k resolution"
        },
        "style_glamour": {
            "title": "✨ Пентхаус Манхеттен",
            "prompt": "Cinematic high-end corporate waist-up medium portrait of the man from the input images standing by floor-to-ceiling windows of a luxury Manhattan skyscraper penthouse, dramatic warm sunset city skyline bokeh strictly on the background, soft neutral indoor lighting on the subject's face, natural realistic skin tones, wearing a sharp tailored dark charcoal suit, shot on Sony Alpha 1, 85mm lens, f/1.4, magazine cover aesthetic"
        },
        "style_cafe": {
            "title": "☕️ Вуличне кафе (Париж)",
            "prompt": "Candid documentary style waist-up medium portrait of the man from the input images sitting at an outdoor terrace of a chic Parisian cafe, holding a coffee cup, soft overcast neutral daylight on the face, warm golden hour sunset glow reflecting softly on European street buildings in the deep background, wearing a stylish minimalist black hoodie, shot on Fujifilm X-T5, 35mm lens, natural skin texture"
        },
        "style_linkedin": {
            "title": "💼 Executive Портрет",
            "prompt": "Professional executive corporate waist-up headshot of the man from the input images inside a modern high-end architectural office, warm sunset city lights blurred far on the background through panoramic windows, soft natural neutral window light on the face for clean skin tones, confident calm expression, wearing a tailored navy blazer and crisp white shirt, shot on Sony A7R V, 85mm lens, razor-sharp focus on eyes, 8k"
        },
        "style_retro": {
            "title": "🎞 Retro Film 90s",
            "prompt": "Authentic 90s vintage film photography waist-up medium portrait snapshot of the man from the input images outdoors in city, warm sunset glow in the background sky, natural balanced lighting on the face, shot on Contax T2, Kodak Portra 400 film grain, casual unposed moment, genuine facial expressions, nostalgic timeless look"
        }
    }

    selected_style = styles.get(style_choice)
    user_photos = user_data_store[user_id]['photos']

    # Повідомлення про початок генерації надсилаємо окремо
    await context.bot.send_message(
        chat_id=user_id,
        text=f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n⏳ Створюємо шедевр через Flux.2 Pro (це займе близько 20-30 секунд)...",
        parse_mode='Markdown'
    )

    try:
        print(f"🚀 [Flux-2-Pro] Початок генерації для стилю: {selected_style['title']}")
        
        output = await asyncio.to_thread(
            replicate.run,
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
            post_action_keyboard = [
                [
                    InlineKeyboardButton("🎨 Обрати інший стиль", callback_data="action_change_style"),
                    InlineKeyboardButton("🔄 Завантажити нові фото", callback_data="action_new_photos")
                ]
            ]
            post_reply_markup = InlineKeyboardMarkup(post_action_keyboard)

            await context.bot.send_photo(
                chat_id=user_id,
                photo=str(final_image_url),
                caption=f"🔥 Твоя приголомшлива фотосесія у стилі **{selected_style['title']}** готова! Готуй лайки в соцмережах 😉",
                reply_markup=post_reply_markup,
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
    app_bot.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_photos))
    app_bot.add_handler(CallbackQueryHandler(handle_style_selection))

    print("🚀 Стабільний бот з робочими кнопками запущено успішно...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
