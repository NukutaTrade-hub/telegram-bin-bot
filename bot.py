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

    # Сброс старых подключений перед запуском
    await Application.builder().token(token).build().bot.delete_webhook(drop_pending_updates=True)

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
