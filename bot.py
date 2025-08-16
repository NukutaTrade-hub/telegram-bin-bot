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

# Глобальная переменная для базы BIN-кодов
bin_db = {}

def load_db():
    """Загрузка базы BIN-кодов из ZIP-архива"""
    try:
        csv_path = "full_bins.csv"
        if not os.path.exists(csv_path):
            logger.info("Распаковываю архив full_bins.zip...")
            with zipfile.ZipFile("full_bins.zip", 'r') as zip_ref:
                zip_ref.extractall()
                logger.info("Архив успешно распакован")
        
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bin_db[row["BIN"]] = {
                    "Brand": row.get("Brand", "Unknown"),
                    "Issuer": row.get("Issuer", "Unknown"),
                    "CountryName": row.get("CountryName", "Unknown"),
                }
        logger.info(f"Загружено {len(bin_db)} BIN-кодов")
        return True
    except Exception as e:
        logger.error(f"Ошибка загрузки базы: {str(e)}")
        return False

def get_card_scheme(bin_code: str) -> str:
    """Определение платёжной системы по BIN-коду"""
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
    return "Unknown"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "🔍 Привет! Пришли мне первые 6 цифр номера карты (BIN), "
        "и я определю банк, страну и платёжную систему.\n"
        "Пример: <code>424242</code> → тестовый Visa",
        parse_mode="HTML"
    )

async def check_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик проверки BIN-кода"""
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

    if bin_code in bin_db:
        data = bin_db[bin_code]
        issuer = data.get("Issuer", issuer)
        country = data.get("CountryName", country)
    else:
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

async def health_check(request):
    """HTTP-обработчик для проверки здоровья"""
    return web.Response(text="OK", status=200)

async def run_http_server(port):
    """Запуск HTTP-сервера для Render"""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"HTTP-сервер запущен на порту {port}")
    return runner

async def run_bot():
    """Основная функция запуска бота"""
    # Загрузка базы данных
    if not load_db():
        logger.critical("Не удалось загрузить базу BIN-кодов!")
        return

    # Проверка токена
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("Токен бота не найден!")
        return

    # Сброс старых подключений
    temp_app = Application.builder().token(token).build()
    await temp_app.bot.delete_webhook(drop_pending_updates=True)
    await temp_app.shutdown()
    await asyncio.sleep(2)  # Короткая задержка

    # Получаем порт из переменных окружения (для Render)
    port = int(os.environ.get("PORT", 8080))

    # Запускаем HTTP-сервер
    http_runner = await run_http_server(port)

    # Создаем и настраиваем приложение бота
    application = Application.builder() \
        .token(token) \
        .concurrent_updates(False) \
        .build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_card))

    # Запускаем бота
    logger.info("Бот запускается...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    # Бесконечный цикл для поддержания работы
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Корректное завершение
        logger.info("Остановка бота...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await http_runner.cleanup()
        logger.info("Бот успешно остановлен")

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Бот остановлен по запросу пользователя")
    except Exception as e:
        logger.error(f"Фатальная ошибка: {str(e)}")
