import os
import csv
import aiohttp
import asyncio
import zipfile
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from aiohttp import web

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка базы BIN-кодов из ZIP-архива
bin_db = {}

def load_db():
    try:
        # Проверяем, нужно ли распаковать архив
        if not os.path.exists("full_bins.csv"):
            logger.info("Распаковываю архив full_bins.zip...")
            with zipfile.ZipFile("full_bins.zip", 'r') as zip_ref:
                zip_ref.extractall()
                logger.info("Архив успешно распакован")
        
        # Загружаем данные из CSV
        with open("full_bins.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bin_db[row["BIN"]] = {
                    "Brand": row.get("Brand", "Unknown"),
                    "Issuer": row.get("Issuer", "Unknown"),
                    "CountryName": row.get("CountryName", "Unknown"),
                }
        logger.info(f"Загружено {len(bin_db)} BIN-кодов")
        
    except Exception as e:
        logger.error(f"Ошибка загрузки базы: {str(e)}")
        raise  # Прерываем работу при ошибке

# Определение платёжной системы
def get_card_scheme(bin_code: str) -> str:
    if not bin_code.isdigit() or len(bin_code) < 6:
        return "Unknown"

    first_digit = int(bin_code[0])
    first_two = int(bin_code[:2])
    first_four = int(bin_code[:4])

    if first_digit == 4:
        return "Visa"
    elif 51 <= first_two <= 55 or 2221 <= first_four <= 2720:
        return "MasterCard"
    elif 2200 <= first_four <= 2204:
        return "МИР"
    else:
        return "Unknown"

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 Привет! Пришли мне первые 6 цифр номера карты (BIN), "
        "и я определю банк, страну и платёжную систему.\n"
        "Пример: <code>424242</code> → тестовый Visa",
        parse_mode="HTML"
    )

async def check_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    bin_code = text[:6] if text.isdigit() else ""

    if not bin_code or len(bin_code) < 6:
        await update.message.reply_text(
            "❌ Нужно 6 цифр. Пример: <code>424242</code>",
            parse_mode="HTML"
        )
        return

    brand = get_card_scheme(bin_code)
    issuer = "Unknown"
    country = "Unknown"

    # Сначала проверяем локальную базу
    if bin_code in bin_db:
        data = bin_db[bin_code]
        issuer = data.get("Issuer", issuer)
        country = data.get("CountryName", country)
    else:
        # Если нет в базе - запрашиваем через API
        try:
            url = f"https://lookup.binlist.net/{bin_code}"
            headers = {"Accept-Version": "3"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        issuer = data.get("bank", {}).get("name", issuer)
                        country = data.get("country", {}).get("name", country)
        except Exception as e:
            logger.error(f"Ошибка API: {str(e)}")

    await update.message.reply_text(
        f"💳 <b>Платёжная система</b>: {brand}\n"
        f"🏦 <b>Банк</b>: {issuer}\n"
        f"🌍 <b>Страна</b>: {country}",
        parse_mode="HTML"
    )

# Keep-Alive сервер для Render
async def keep_alive():
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="Bot is alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Keep-alive сервер запущен на порту 8080")

# Запуск бота
async def main():
    # Инициализация базы данных
    try:
        load_db()
    except Exception as e:
        logger.critical(f"Не удалось загрузить базу: {str(e)}")
        return

    # Проверка токена
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("Токен бота не найден! Добавьте TELEGRAM_TOKEN в переменные окружения.")
        return

    # Создаем и настраиваем приложение
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_card))

    # Запускаем keep-alive
    asyncio.create_task(keep_alive())

    # Запускаем бота
    logger.info("Бот запускается...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
