import os
import logging
import asyncio
import signal
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.error import NetworkError, RetryAfter
from binance.client import Client
import requests

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНСТАНТЫ ==========
BOT_TOKEN = "8279909476:AAF4bRExh18Ve5pQ2F-wAHdBcQLfda-yNOU"  # Ваш токен

# ========== ИНИЦИАЛИЗАЦИЯ КЛИЕНТОВ ==========
try:
    client = Client()
    logger.info("Binance client initialized successfully")
except Exception as e:
    logger.warning(f"Binance client init failed: {e}")
    client = None

# ========== КЛАВИАТУРЫ ==========
def get_main_reply_keyboard():
    """Главная reply-клавиатура"""
    keyboard = [
        [KeyboardButton("💰 Узнать курс"), KeyboardButton("🧮 Конвертировать")],
        [KeyboardButton("📋 Меню"), KeyboardButton("🆘 Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_main_inline_keyboard():
    """Главная inline-клавиатура"""
    keyboard = [
        [InlineKeyboardButton("💰 Узнать курс TON", callback_data='get_price')],
        [InlineKeyboardButton("🧮 Конвертировать", switch_inline_query_current_chat="/convert ")],
        [InlineKeyboardButton("📊 Источники данных", callback_data='sources')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ФУНКЦИИ ДЛЯ ПОЛУЧЕНИЯ ЦЕН ==========
async def get_p2p_price_binance():
    """Получаем цену USDT/RUB с P2P Binance"""
    try:
        data = {
            "proMerchantAds": False,
            "page": 1,
            "rows": 20,
            "payTypes": [],
            "countries": [],
            "publisherType": None,
            "fiat": "RUB",
            "tradeType": "BUY",
            "asset": "USDT",
            "transAmount": ""
        }

        response = requests.post(
            'https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search',
            headers={'Content-Type': 'application/json'},
            json=data,
            timeout=10
        )
        
        result = response.json()
        
        if not result['success'] or not result['data']:
            logger.warning("Binance P2P: no offers found")
            return None

        ads = result['data']
        prices = []

        for ad in ads:
            try:
                adv_info = ad['adv']
                if (float(adv_info['surplusAmount']) > 0 and 
                    adv_info['tradeMethods'] and
                    adv_info['price']):
                    price = float(adv_info['price'])
                    prices.append(price)
            except (KeyError, ValueError):
                continue

        if prices:
            top_prices = sorted(prices)[:5]
            average_price = sum(top_prices) / len(top_prices)
            logger.info(f"Binance P2P: found {len(prices)} offers, average price: {average_price}")
            return round(average_price, 2)
        else:
            logger.warning("Binance P2P: no valid offers found")
            return None

    except Exception as e:
        logger.error(f"Binance P2P error: {e}")
        return None

async def get_spot_price_binance():
    """Получаем цену USDT/RUB с спотового рынка Binance"""
    if client is None:
        return None
    try:
        ticker = client.get_symbol_ticker(symbol="USDTRUB")
        usdt_rub_price = float(ticker['price'])
        logger.info(f"Binance Spot price: {usdt_rub_price}")
        return round(usdt_rub_price, 2)
    except Exception as e:
        logger.error(f"Binance Spot error: {e}")
        return None

async def get_price_coingecko():
    """Получаем цену USDT/RUB с CoinGecko"""
    try:
        response = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub',
            timeout=10
        )
        data = response.json()
        usdt_rub_price = data['tether']['rub']
        logger.info(f"CoinGecko price: {usdt_rub_price}")
        return usdt_rub_price
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return None

async def get_ton_price():
    """Получаем текущую цену TON к USDT"""
    if client is None:
        return None
    try:
        ticker = client.get_symbol_ticker(symbol="TONUSDT")
        ton_price = float(ticker['price'])
        logger.info(f"TON price: {ton_price}")
        return ton_price
    except Exception as e:
        logger.error(f"TON price error: {e}")
        return None

async def get_usdt_rub_price():
    """Главная функция получения цены USDT/RUB"""
    price_sources = [
        (get_p2p_price_binance, "P2P Binance"),
        (get_spot_price_binance, "Spot Binance"),
        (get_price_coingecko, "CoinGecko")
    ]
    
    for price_func, source in price_sources:
        price = await price_func()
        if price is not None:
            return price, source
    
    return None, "No data"

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    welcome_text = (
        f"👋 <b>Добро пожаловать, {user.first_name}!</b>\n\n"
        "💎 <b>TON Price Bot</b> поможет отслеживать актуальный курс TON\n"
        "на основе реальных P2P-сделок в рублях.\n\n"
        "🚀 <b>Выберите действие:</b>\n"
        "• <b>Узнать курс</b> - текущая цена TON\n"
        "• <b>Конвертировать</b> - перевести TON в рубли\n"
        "• <b>Меню</b> - информация о командах\n\n"
        "📊 <i>Данные обновляются в реальном времени</i>\n\n"
        "💡 <i>Используйте кнопки ниже для быстрого доступа</i>"
    )
    
    await update.message.reply_text(welcome_text, 
                                  reply_markup=get_main_inline_keyboard(), 
                                  parse_mode='HTML')
    await update.message.reply_text("⌨️ <b>Быстрые команды:</b>", 
                                  reply_markup=get_main_reply_keyboard(), 
                                  parse_mode='HTML')

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /menu"""
    menu_text = (
        "📋 <b>Меню TON Price Bot</b>\n\n"
        "💎 <b>О боте:</b>\n"
        "Я анализирую рынок P2P-торговли на крупнейших биржах \n"
        "и показываю реальную стоимость TON в рублях.\n\n"
        "🚀 <b>Доступные команды:</b>\n"
        "• <b>/start</b> - начать работу с ботом\n"
        "• <b>/menu</b> - показать это меню\n"
        "• <b>/price</b> - текущий курс TON\n"
        "• <b>/convert</b> - конвертировать TON в рубли\n\n"
        "💡 <b>Примеры:</b>\n"
        "<code>/convert 5.5</code> - посчитать стоимость 5.5 TON\n\n"
        "📊 <i>Данные обновляются в реальном времени</i>"
    )
    await update.message.reply_text(menu_text, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "🆘 <b>Помощь по TON Price Bot</b>\n\n"
        "💎 <b>Как использовать:</b>\n"
        "• Нажмите <b>💰 Узнать курс</b> для получения текущей цены\n"
        "• Нажмите <b>🧮 Конвертировать</b> для перевода TON в рубли\n"
        "• Или используйте команды:\n"
        "  <code>/price</code> - курс TON\n"
        "  <code>/convert 10</code> - конвертация 10 TON\n\n"
        "🔧 <b>Источники данных:</b>\n"
        "• P2P Binance (основной)\n"
        "• Spot Binance (резервный)\n"
        "• CoinGecko (аварийный)\n\n"
        "📞 <b>Если возникли проблемы:</b>\n"
        "Перезапустите бота командой /start"
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на inline-кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'get_price':
        await send_price_message(query.message)
    elif query.data == 'sources':
        sources_text = (
            "📊 <b>Источники данных:</b>\n\n"
            "• <b>P2P Binance</b> - основные данные с P2P-площадки\n"
            "• <b>Spot Binance</b> - биржевые данные (резерв)\n"
            "• <b>CoinGecko</b> - агрегатор цен (аварийный источник)\n\n"
            "💡 Бот автоматически выбирает самый надежный источник"
        )
        await query.message.reply_text(sources_text, parse_mode='HTML')

async def send_price_message(message):
    """Отправляет сообщение с текущей ценой"""
    await message.reply_chat_action(action="typing")
    
    usdt_rub_price, source = await get_usdt_rub_price()
    ton_usdt_price = await get_ton_price()

    if usdt_rub_price and ton_usdt_price:
        ton_rub_price = ton_usdt_price * usdt_rub_price
        message_text = (
            f"💎 <b>Актуальный курс TON</b>\n\n"
            f"• <b>1 TON</b> = <b>{ton_rub_price:,.2f} ₽</b>\n"
            f"• 1 USDT = {usdt_rub_price} ₽ ({source})\n"
            f"• 1 TON = {ton_usdt_price:,.4f} $\n\n"
            f"📊 <i>Обновлено: {source}</i>\n"
            f"🔄 <i>Используйте /convert для расчетов</i>"
        )
    else:
        message_text = (
            "😕 <b>Не удалось получить данные</b>\n\n"
            "Попробуйте снова через несколько минут.\n"
            "Если проблема persists, используйте /help"
        )
    
    await message.reply_text(message_text, parse_mode='HTML')

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /price"""
    await send_price_message(update.message)

async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /convert"""
    await update.message.reply_chat_action(action="typing")
    
    if not context.args:
        help_text = (
            "🧮 <b>Конвертация TON в рубли</b>\n\n"
            "💡 <i>Введите количество TON после команды:</i>\n"
            "<code>/convert 5.5</code>\n\n"
            "📝 <i>Или просто напишите число после нажатия кнопки \"Конвертировать\"</i>"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')
        return

    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ <b>Ошибка!</b> Пожалуйста, укажите корректное положительное число.\n\n"
            "<i>Пример:</i> <code>/convert 5.5</code>", 
            parse_mode='HTML'
        )
        return

    usdt_rub_price, source = await get_usdt_rub_price()
    ton_usdt_price = await get_ton_price()

    if usdt_rub_price and ton_usdt_price:
        result = (amount * ton_usdt_price) * usdt_rub_price
        message_text = (
            f"🧮 <b>Конвертация TON</b>\n\n"
            f"• <b>{amount} TON</b> = <b>{result:,.2f} ₽</b>\n"
            f"• Курс: 1 TON = {ton_usdt_price:,.4f} $\n"
            f"• Курс: 1 USDT = {usdt_rub_price} ₽\n"
            f"• Источник: {source}\n\n"
            f"💡 <i>Для актуального курса используйте /price</i>"
        )
        await update.message.reply_text(message_text, parse_mode='HTML')
    else:
        error_text = (
            "😕 <b>Не удалось получить данные для конвертации</b>\n\n"
            "Попробуйте снова через несколько минут.\n"
            "Используйте /price для проверки доступности данных"
        )
        await update.message.reply_text(error_text, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (для reply-кнопок)"""
    text = update.message.text
    
    if text == "💰 Узнать курс":
        await send_price_message(update.message)
    elif text == "🧮 Конвертировать":
        await update.message.reply_text(
            "💡 Введите количество TON для конвертации:\n\n"
            "<i>Пример:</i> <code>5.5</code> или <code>/convert 5.5</code>",
            parse_mode='HTML'
        )
    elif text == "📋 Меню":
        await menu(update, context)
    elif text == "🆘 Помощь":
        await help_command(update, context)

# ========== ОБРАБОТЧИК ОШИБОК ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    if isinstance(context.error, (NetworkError, RetryAfter)):
        # Это временные ошибки сети, просто логируем
        return
        
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="😕 <b>Произошла ошибка</b>\n\nПопробуйте снова через несколько секунд.",
            parse_mode='HTML'
        )
    except:
        pass

# ========== ЗАПУСК БОТА ==========
def main():
    """Запускает бота с обработкой ошибок"""
    if not BOT_TOKEN:
        logger.error("Токен бота не найден! Убедитесь, что переменная BOT_TOKEN установлена.")
        return

    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("convert", convert))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик текстовых сообщений для reply-кнопок
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Обработчики сигналов для graceful shutdown
    def shutdown(signum, frame):
        logger.info("Бот останавливается...")
        application.stop()
        application.shutdown()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    logger.info("Бот запущен...")
    
    # Запускаем бота с бесконечным циклом
    try:
        application.run_polling()
    except Exception as e:
        logger.error(f"Critical error: {e}")

if __name__ == '__main__':
    main()
