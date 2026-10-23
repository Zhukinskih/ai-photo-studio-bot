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

    # Визначаємо, чи це звичайне фото, чи документ-картинка з ПК
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

# --- Функція для виведення меню стилів (використовується повторно) ---
async def show_styles_menu(update_or_query, context, user_id):
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
    text = "🎨 Обери стиль для наступної фотосесії:"

    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup, parse_mode='Markdown')

# --- Обробка вибору стилю та генерація через Flux-2-Pro ---
async def handle_style_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # Перевірка на кнопки посткабінету (зміна стилю або нові фото)
    if data == "action_change_style":
        await query
