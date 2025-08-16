import csv
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Читаем базу BIN в словарь при старте
bin_db = {}
with open("bins_filtered.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        bin_db[row["BIN"]] = {
            "Brand": row["Brand"],
            "Issuer": row["Issuer"],
            "CountryName": row["CountryName"]
        }

# Функция определения платёжной системы по BIN
def get_card_scheme(bin_code):
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

# Функция /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Отправь мне номер карты (Visa, MasterCard, МИР), "
        "и я скажу банк, страну и платёжную систему.\n"
        "⚠️ Безопасно — беру только первые 6 цифр."
    )

# Функция обработки номера карты
async def check_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card_number = update.message.text.strip().replace(" ", "")
    if not card_number.isdigit() or len(card_number) < 6:
        await update.message.reply_text("Пожалуйста, отправь правильный номер карты.")
        return

    bin_code = card_number[:6]

    # Определяем платёжную систему
    brand = get_card_scheme(bin_code)

    # Сначала проверяем локальную базу
    if bin_code in bin_db:
        data = bin_db[bin_code]
        issuer = data.get("Issuer", "Unknown")
        country = data.get("CountryName", "Unknown")
    else:
        # Если нет в локальной базе — запрос к API
        url = f"https://lookup.binlist.net/{bin_code}"
        headers = {"Accept-Version": "3"}
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data_api = response.json()
                issuer = data_api.get("bank", {}).get("name", "Unknown")
                country = data_api.get("country", {}).get("name", "Unknown")
            else:
                issuer = "Unknown"
                country = "Unknown"
        except:
            issuer = "Unknown"
            country = "Unknown"

    result = (
        f"💳 Brand: {brand}\n"
        f"🏦 Bank: {issuer}\n"
        f"🌍 Country: {country}"
    )
    await update.message.reply_text(result)

# Запуск бота
if __name__ == "__main__":
    TOKEN = "8273272016:AAFoBAyO9CcmmuL_bcixf8jjHC8y33NUNEY"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_card))
    print("Бот запущен...")
    app.run_polling()
