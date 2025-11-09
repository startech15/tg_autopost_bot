import os
from datetime import timedelta

# Конфигурация бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '6104374357:AAG2AoC3_WnK0itiVJphmpWp1GegAprrV0U')

# Настройки базы данных
DATABASE_NAME = 'autopost_bot.db'

# Настройки подписки
FREE_TIER_POSTS = 10
TRIAL_PERIOD_DAYS = 14
SUBSCRIPTION_PRICE_STARS = 100  # Цена подписки в звездах

# Доступные типы контента
ALLOWED_CONTENT_TYPES = ['text', 'photo', 'video', 'document']

# Настройки планировщика
SCHEDULER_TIMEZONE = 'UTC+3'