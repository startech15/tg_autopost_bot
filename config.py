import os

# Конфигурация бота
BOT_TOKEN = "6104374357:AAGO3m_9dLf5u6-PeKNZ6UmHjngV97JcD-Q"  # Замените на ваш токен

# Настройки базы данных
DB_FILE = "scheduler_database.db"

# Директории для хранения контента
UPLOAD_DIRS = {
    'photo': 'uploaded_content/images',
    'video': 'uploaded_content/videos',
    'document': 'uploaded_content/documents',
    'audio': 'uploaded_content/audio'
}

# Создаем директории если не существуют
for dir_path in UPLOAD_DIRS.values():
    os.makedirs(dir_path, exist_ok=True)
os.makedirs('uploaded_content', exist_ok=True)

# Настройки планировщика
CHECK_INTERVAL = 30  # секунды
MAX_SCHEDULE_DAYS = 30  # максимальное планирование на дней вперед