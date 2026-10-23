import os
import logging
import asyncio
import io
import replicate
from PIL import Image
import requests
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

# Словник для збереження даних користувача
user_data_store = {}

# --- Команда /start: спочатку запитуємо стать ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {'photos': [], 'gender': None}
    
    keyboard = [
        [
            InlineKeyboardButton("👨 Чоловік", callback_data="gender_male"),
            InlineKeyboardButton("👩 Жінка", callback_data="gender_female")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        "✨ **Вітаю в AI Photo Studio Pro!** ✨\n\n"
        "Створимо твою розкішну професійну фотосесію рівня глянцевих журналів за допомогою передової моделі Flux.2 Pro.\n\n"
        "👤 **Спочатку обери, для кого будемо створювати образ:**"
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

# --- Встановлення кнопки Menu / Start у Telegram ---
async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Запустити бота та обрати стиль")
    ])

# --- Меню стилів ---
async def show_styles_menu(chat_id, context):
    keyboard = [
        [
            InlineKeyboardButton("🏔 Панорама Альп", callback_data="style_mountain"),
            InlineKeyboardButton("🛥 Яхта в океані", callback_data="style_beach")
        ],
        [
            InlineKeyboardButton("🌴 Тропічний Острів", callback_data="style_island"),
            InlineKeyboardButton("🏎️ Суперкар Монако", callback_data="style_supercar")
        ],
        [
            InlineKeyboardButton("✨ Пентхаус Манхеттен", callback_data="style_glamour"),
            InlineKeyboardButton("☕️ Терраса в Італії", callback_data="style_cafe")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id, 
        text="🎨 Чудово! Тепер обери стиль для твоєї фотосесії:", 
        reply_markup=reply_markup, 
        parse_mode='Markdown'
    )

# --- Обробка завантажених фото або файлів-картинок ---
async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data_store or not user_data_store[user_id].get('gender'):
        await update.message.reply_text("⚠️ Будь ласка, спочатку натисни /start та обери стать.")
        return

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
        # Фото достатньо, одразу показуємо меню стилів
        await show_styles_menu(user_id, context)
    else:
        await update.message.reply_text(
            f"✅ Отримано фото: {sources_count}/3. Додай ще кілька, щоб зібрати мінімум 3 референси.",
            parse_mode='Markdown'
        )

# --- Функція для скачування та конвертації у чистий JPEG ---
def convert_to_jpeg(image_url):
    response = requests.get(image_url)
    img = Image.open(io.BytesIO(response.content))
    
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    output_buffer = io.BytesIO()
    img.save(output_buffer, format="JPEG", quality=95)
    output_buffer.seek(0)
    return output_buffer

# --- Обробка натискань на кнопки ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    # Вибір статі
    if data in ["gender_male", "gender_female"]:
        gender = "male" if data == "gender_male" else "female"
        if user_id not in user_data_store:
            user_data_store[user_id] = {'photos': [], 'gender': gender}
        else:
            user_data_store[user_id]['gender'] = gender

        gender_text = "👨 Чоловічий" if gender == "male" else "👩 Жіночий"
        instructions_text = (
            f"✅ Обрано: **{gender_text} образ**.\n\n"
            "📸 **Тепер надішли 3-4 різні фото (по груди / середній план):**\n"
            "• Одне — дивлячись прямо в камеру, інші — під невеликим кутом.\n"
            "• Чітке освітлення, без темних кімнат чи розмиття.\n\n"
            "👇 Чекаю твої фото пачкою або файлами!"
        )
        await query.edit_message_text(instructions_text, parse_mode='Markdown')
        return

    if data == "action_change_style":
        if user_id not in user_data_store or len(user_data_store[user_id].get('photos', [])) < 3:
            await context.bot.send_message(chat_id=user_id, text="❌ Спочатку завантаж щонайменше 3 фото.")
            return
        await show_styles_menu(user_id, context)
        return

    if data == "action_new_photos":
        user_data_store[user_id] = {'photos': [], 'gender': None}
        await context.bot.send_message(
            chat_id=user_id,
            text="🔄 Сеанс скинуто. Введи або натисни /start, щоб почати спочатку.",
            parse_mode='Markdown'
        )
        return

    style_choice = data

    if user_id not in user_data_store or len(user_data_store[user_id].get('photos', [])) < 3:
        await context.bot.send_message(chat_id=user_id, text="❌ Будь ласка, спочатку завантаж щонайменше 3 фото.")
        return

    gender = user_data_store[user_id].get('gender', 'male')

    # Промпти для чоловіків
    male_styles = {
        "style_mountain": {
            "title": "🏔 Панорама Альп (Quiet Luxury)",
            "prompt": "High-end editorial waist-up medium portrait of the man from the input images standing on a modern glass balcony of an architectural alpine chalet, breathtaking majestic snowy mountain peaks panorama bathed in soft golden hour sunset light strictly on the background, natural neutral front daylight illuminating the subject's face with accurate skin tones, wearing a premium cashmere crewneck sweater, shot on Hasselblad 100MP, 35mm lens, natural unpolished skin texture, visible micro-pores, 8k, photorealistic"
        },
        "style_beach": {
            "title": "🛥 Яхта в океані (Superyacht)",
            "prompt": "High-end luxury travel magazine waist-up medium portrait of the man from the input images relaxing on the deck of a modern superyacht, crystal clear turquoise open ocean panorama with a soft warm sunset glowing far on the horizon background, natural bright daytime light on the subject's face, accurate natural skin tones, wearing a stylish unbuttoned white linen shirt, shot on Leica S3, 50mm lens, zero plastic look, 8k resolution"
        },
        "style_island": {
            "title": "🌴 Тропічний Острів (Paradise Beach)",
            "prompt": "High-end travel magazine waist-up portrait of the man from the input images standing relaxed waist-deep in crystal-clear turquoise tropical ocean water near a white sandy shore, warm golden hour sun glowing in the sky, realistic natural body physique with soft natural definition, natural palm trees and soft out-of-focus tropical coast on the background, soft natural bright daylight illuminating the face with accurate natural skin tones, relaxed natural pose looking into the camera, wearing minimalist swimwear, shot on Sony Alpha 1, 35mm lens, natural unpolished skin texture, photorealistic"
        },
        "style_supercar": {
            "title": "🏎️ Суперкар Монако",
            "prompt": "High-end editorial waist-up medium portrait of the man from the input images standing next to a luxury modern supercar in front of a grand illuminated luxury hotel entrance in Monaco, warm sunset dusk lighting, elegant warm architectural lights reflecting on the car's surface in the background, soft neutral daylight illuminating the subject's face for precise skin tone accuracy, wearing a modern dark fitted polo, shot on Hasselblad H6D-100c, 50mm lens, razor-sharp focus, unpolished realistic skin texture, 8k"
        },
        "style_glamour": {
            "title": "✨ Пентхаус Манхеттен",
            "prompt": "Cinematic high-end corporate waist-up medium portrait of the man from the input images standing inside a luxury Manhattan skyscraper penthouse by massive floor-to-ceiling glass windows, iconic recognizable New York City skyline with famous skyscrapers and glowing evening lights clearly visible and detailed on the background, warm golden hour sunset illuminating the urban architecture, soft neutral indoor lighting on the subject's face, natural realistic skin tones, wearing a sharp tailored dark charcoal suit, shot on Sony Alpha 1, 85mm lens, f/4, crisp architectural background details, magazine cover aesthetic"
        },
        "style_cafe": {
            "title": "☕️ Терраса в Італії (Amalfi Coast)",
            "prompt": "Candid travel lifestyle waist-up medium portrait of the man from the input images sitting at an outdoor cafe terrace overlooking the stunning Amalfi coast in Italy, holding an espresso cup, beautiful classic Italian architecture and Mediterranean buildings sharply visible on the background, warm golden hour sunlight, wearing a smart casual linen shirt, shot on Leica M11, 35mm lens, natural realistic skin texture, photorealistic"
        }
    }

    # Промпти для жінок
    female_styles = {
        "style_mountain": {
            "title": "🏔 Панорама Альп (Quiet Luxury)",
            "prompt": "High-end Vogue editorial waist-up portrait of the woman from the input images standing on a glass balcony of a modern luxury alpine chalet, breathtaking snowy mountain peaks sunset panorama on the background, soft front daylight illuminating her face with elegant natural makeup and smooth skin texture, wearing an oversized creamy cashmere knit sweater, shot on Hasselblad 100MP, 50mm lens, soft windy hair, magazine cover aesthetic, 8k"
        },
        "style_beach": {
            "title": "🛥 Яхта в океані (Superyacht)",
            "prompt": "Luxury travel magazine waist-up portrait of the woman from the input images relaxing on the deck of a sleek superyacht, pristine turquoise ocean and golden hour horizon on the background, warm bright sunlight illuminating her face with fresh natural glow, wearing an elegant silk beach cover-up over a stylish swimsuit, wind-kissed hair, shot on Leica S3, 50mm lens, photorealistic, elegant luxury aesthetic"
        },
        "style_island": {
            "title": "🌴 Тропічний Острів (Paradise Beach)",
            "prompt": "High-end fashion waist-up portrait of the woman from the input images standing waist-deep in crystal-clear turquoise ocean water, pristine white sand beach and tropical palm trees blurred on the background, glowing golden sunset light, wearing a chic designer bikini, wet effortless hair, natural glowing skin tone, shot on Sony Alpha 1, 35mm lens, 8k resolution"
        },
        "style_supercar": {
            "title": "🏎️ Суперкар Монако",
            "prompt": "Glamorous Vogue waist-up portrait of the woman from the input images leaning elegantly near a modern luxury supercar outside the famous Hotel de Paris in Monaco, warm sunset dusk ambiance, soft glowing lights reflecting on the car and architecture, wearing an elegant dark evening dress, soft sophisticated makeup, shot on Hasselblad H6D, 85mm portrait lens, razor sharp focus"
        },
        "style_glamour": {
            "title": "✨ Пентхаус Манхеттен",
            "prompt": "Cinematic high-end fashion waist-up portrait of the woman from the input images standing inside a Manhattan penthouse by panoramic floor-to-ceiling windows, breathtaking glowing New York City skyline at sunset on the background, soft warm indoor lighting on face, wearing a chic tailored silk suit or sleek cocktail dress, magazine editorial pose, shot on Sony Alpha 1, 85mm lens, f/2.8"
        },
        "style_cafe": {
            "title": "☕️ Терраса в Італії (Amalfi Coast)",
            "prompt": "Candid elegant waist-up portrait of the woman from the input images sitting at a sunlit outdoor terrace in Amalfi Italy, holding a coffee cup, colorful Mediterranean cliffside architecture sharply visible on the background, soft golden hour sunlight, wearing a light linen sundress and stylish minimalist jewelry, shot on Leica M11, 35mm lens, natural glowing skin texture"
        }
    }

    styles = male_styles if gender == 'male' else female_styles
    selected_style = styles.get(style_choice)
    user_photos = user_data_store[user_id]['photos']

    await context.bot.send_message(
        chat_id=user_id,
        text=f"🎨 Обрано стиль: **{selected_style['title']}**!\n\n⏳ Створюємо шедевр через Flux.2 Pro (це займе близько 20-30 секунд)...",
        parse_mode='Markdown'
    )

    try:
        print(f"🚀 [Flux-2-Pro] Початок генерації для стилю: {selected_style['title']} ({gender})")
        
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
            jpeg_file = await asyncio.to_thread(convert_to_jpeg, final_image_url)

            post_action_keyboard = [
                [
                    InlineKeyboardButton("🎨 Обрати інший стиль", callback_data="action_change_style"),
                    InlineKeyboardButton("🔄 Завантажити нові фото", callback_data="action_new_photos")
                ]
            ]
            post_reply_markup = InlineKeyboardMarkup(post_action_keyboard)

            await context.bot.send_document(
                chat_id=user_id,
                document=jpeg_file,
                filename=f"photo_{style_choice}.jpg",
                caption=f"🔥 Твоя фотосесія у стилі **{selected_style['title']}** готова! (Оригінал .jpg у високій якості)",
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
    app_bot.add_handler(CallbackQueryHandler(handle_callback_query))

    print("🚀 Бот зі зручним логічним порядком (Стать -> Фото -> Стиль) запускно...")
    app_bot.run_polling()

if __name__ == '__main__':
    main()
