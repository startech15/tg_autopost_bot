import asyncio
import logging
import os
import sqlite3
import re
from datetime import datetime, timedelta
import random

# Импортируем конфигурацию
from config import DB_FILE, CHECK_INTERVAL, BOT_TOKEN
from database import ContentDatabase
from content_manager import ContentManager
from telegram import Bot

logger = logging.getLogger(__name__)


class PostScheduler:
    def __init__(self, db_file):
        self.bot = Bot(token=BOT_TOKEN)
        self.db = ContentDatabase()
        self.content_manager = ContentManager()
        self.is_running = True
        self.db_file = db_file

    async def start_scheduler(self):
        """Запуск основного планировщика"""
        logger.info("Основной планировщик публикаций запущен")
        print("DEBUG: 🚀 Основной планировщик ЗАПУЩЕН")

        while self.is_running:
            try:
                await self.check_and_publish()
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Ошибка в основном планировщике: {e}")
                print(f"DEBUG: ❌ Ошибка основного планировщика: {e}")
                await asyncio.sleep(10)

    async def simple_scheduler(self):
        """Упрощенный планировщик для надежности"""
        print("🛠️ Упрощенный планировщик запущен")

        while self.is_running:
            try:
                # Простой запрос - все scheduled посты
                conn = sqlite3.connect(self.db_file)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM scheduled_posts 
                    WHERE status = 'scheduled'
                    ORDER BY scheduled_time ASC
                ''')
                all_scheduled = cursor.fetchall()
                conn.close()

                current_time = datetime.now()
                published_count = 0

                for post_data in all_scheduled:
                    try:
                        post_time = datetime.strptime(post_data[6], '%Y-%m-%d %H:%M:%S')

                        # Если время публикации наступило
                        if post_time <= current_time:
                            print(f"🛠️ Упрощенный планировщик: публикую пост {post_data[0]} в канал {post_data[2]}")

                            post = {
                                'id': post_data[0],
                                'user_id': post_data[1],
                                'channel_id': post_data[2],
                                'content_type': post_data[3],
                                'file_path': post_data[4],
                                'caption': post_data[5],
                                'scheduled_time': post_data[6],
                                'status': post_data[7]
                            }

                            success = await self.publish_post(post)
                            if success:
                                published_count += 1
                    except Exception as e:
                        print(f"🛠️ Ошибка обработки поста {post_data[0]}: {e}")

                if published_count > 0:
                    print(f"🛠️ Упрощенный планировщик опубликовал {published_count} постов")

                await asyncio.sleep(30)  # Проверяем каждые 30 секунд

            except Exception as e:
                print(f"🛠️ Ошибка упрощенного планировщика: {e}")
                await asyncio.sleep(30)

    async def check_and_publish(self):
        """Проверка и публикация запланированных постов"""
        posts_to_publish = self.get_posts_to_publish()

        if posts_to_publish:
            print(f"DEBUG: 📊 Основной планировщик нашел {len(posts_to_publish)} постов")

        for post in posts_to_publish:
            print(f"DEBUG: 🚀 Основной планировщик: публикую пост ID: {post['id']} в канал {post['channel_id']}")
            success = await self.publish_post(post)
            if success:
                print(f"DEBUG: ✅ Пост ID:{post['id']} опубликован через основной планировщик")

    def get_posts_to_publish(self):
        """Получение постов для публикации"""
        print("DEBUG: 🔍 Основной планировщик ищет посты для публикации")

        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM scheduled_posts 
            WHERE status = 'scheduled'
            ORDER BY scheduled_time ASC
        ''')

        all_scheduled = cursor.fetchall()
        conn.close()

        current_time = datetime.now()
        posts_to_publish = []

        for post_data in all_scheduled:
            try:
                post_time = datetime.strptime(post_data[6], '%Y-%m-%d %H:%M:%S')

                if post_time <= current_time:
                    posts_to_publish.append({
                        'id': post_data[0],
                        'user_id': post_data[1],
                        'channel_id': post_data[2],
                        'content_type': post_data[3],
                        'file_path': post_data[4],
                        'caption': post_data[5],
                        'scheduled_time': post_data[6],
                        'status': post_data[7]
                    })
            except Exception as e:
                print(f"DEBUG: ❌ Ошибка обработки поста {post_data[0]}: {e}")

        print(f"DEBUG: 📋 Основной планировщик нашел {len(posts_to_publish)} постов для публикации")
        return posts_to_publish

    async def publish_post(self, post):
        """Публикация отдельного поста с форматированием текста"""
        print(f"DEBUG: 🚀 Публикация поста ID: {post['id']} в канал {post['channel_id']}")

        try:
            file_path = self.content_manager.get_file_path(post['file_path'])

            # Проверяем существование файла
            if not os.path.exists(file_path) and post['content_type'] != 'text':
                print(f"DEBUG: ❌ Файл не существует: {file_path}")
                return False

            message = None
            caption = post['caption']

            # ФОРМАТИРУЕМ ТЕКСТ (добавляем эмодзи и хештеги)
            if caption:
                caption = self.format_text(caption)

            if post['content_type'] == 'photo':
                print(f"DEBUG: 📷 Публикуем фото в {post['channel_id']}")
                with open(file_path, 'rb') as photo:
                    message = await self.bot.send_photo(
                        chat_id=post['channel_id'],
                        photo=photo,
                        caption=caption,
                        parse_mode='HTML'
                    )

            elif post['content_type'] == 'video':
                print(f"DEBUG: 🎥 Публикуем видео в {post['channel_id']}")
                with open(file_path, 'rb') as video:
                    message = await self.bot.send_video(
                        chat_id=post['channel_id'],
                        video=video,
                        caption=caption,
                        parse_mode='HTML'
                    )

            elif post['content_type'] == 'document':
                print(f"DEBUG: 📄 Публикуем документ в {post['channel_id']}")
                with open(file_path, 'rb') as document:
                    message = await self.bot.send_document(
                        chat_id=post['channel_id'],
                        document=document,
                        caption=caption,
                        parse_mode='HTML'
                    )

            elif post['content_type'] == 'text':
                print(f"DEBUG: 📝 Публикуем текст в {post['channel_id']}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    text_content = f.read()

                # ФОРМАТИРУЕМ ТЕКСТОВЫЙ ПОСТ
                text_content = self.format_text(text_content)

                message = await self.bot.send_message(
                    chat_id=post['channel_id'],
                    text=text_content,
                    parse_mode='HTML'
                )

            if message is None:
                print(f"DEBUG: ❌ Сообщение не было отправлено в {post['channel_id']}")
                return False

            print(f"DEBUG: 💬 Сообщение отправлено в {post['channel_id']}. Message ID: {message.message_id}")

            # Обновляем статус в БД
            success = self.mark_as_published(post['id'], message.message_id)

            if success:
                # Очищаем временные файлы для текстовых постов
                if post['content_type'] == 'text':
                    self.content_manager.cleanup_file(file_path)
                print(f"DEBUG: ✅ Пост {post['id']} успешно опубликован в {post['channel_id']}")
                return True
            else:
                print(f"DEBUG: ❌ Не удалось обновить статус в БД")
                return False

        except Exception as e:
            print(f"DEBUG: 💥 Ошибка публикации поста {post['id']} в {post['channel_id']}: {e}")
            import traceback
            print(f"DEBUG: 🗂️ Трассировка: {traceback.format_exc()}")
            return False

    def format_text(self, text):
        """Форматирование текста: эмодзи для абзацев и релевантные хештеги"""
        if not text or not text.strip():
            return text

        # Извлекаем хештеги из текста
        extracted_hashtags = self.extract_hashtags_from_text(text)

        # Удаляем хештеги из основного текста
        clean_text = self.remove_hashtags_from_text(text)

        # Разбиваем на абзацы и добавляем эмодзи к каждому непустому абзацу
        paragraphs = clean_text.split('\n')
        formatted_paragraphs = []

        emojis = ['✨', '🌟', '💫', '🔥', '🎯', '📌', '💡', '🚀', '🎉', '🌈']

        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():  # если абзац не пустой
                emoji = emojis[i % len(emojis)]  # циклически выбираем эмодзи
                formatted_paragraphs.append(f"{emoji} {paragraph}")
            else:
                formatted_paragraphs.append(paragraph)  # пустые строки оставляем как есть

        formatted_text = '\n'.join(formatted_paragraphs)

        # Добавляем хештеги (извлеченные из текста + дополнительные релевантные)
        hashtags = self.generate_relevant_hashtags(clean_text, extracted_hashtags)
        if hashtags:
            formatted_text += f"\n\n{hashtags}"

        return formatted_text

    def extract_hashtags_from_text(self, text):
        """Извлечение хештегов из текста"""
        hashtags = re.findall(r'#\w+', text)
        return list(set(hashtags))  # Убираем дубликаты

    def remove_hashtags_from_text(self, text):
        """Удаление хештегов из текста"""
        return re.sub(r'#\w+', '', text).strip()

    def generate_relevant_hashtags(self, text, extracted_hashtags):
        """Генерация релевантных хештегов на основе текста"""
        # Словарь ключевых слов и соответствующих хештегов
        keyword_hashtags = {
            'техно': ['#технологии', '#гаджеты', '#инновации'],
            'айфон': ['#iPhone', '#Apple', '#iOS'],
            'андроид': ['#Android', '#Google', '#Samsung'],
            'телефон': ['#смартфон', '#мобильный', '#гаджет'],
            'ноутбук': ['#ноутбук', '#laptop', '#компьютер'],
            'игр': ['#игры', '#гейминг', '#киберспорт'],
            'программир': ['#программирование', '#кодинг', '#разработка'],
            'софт': ['#софт', '#программы', '#приложения'],
            'интернет': ['#интернет', '#онлайн', '#digital'],
            'новост': ['#новости', '#тренды', '#обновления'],
            'обзор': ['#обзор', '#рецензия', '#тест'],
            'совет': ['#советы', '#лайфхаки', '#рекомендации'],
            'кино': ['#кино', '#фильмы', '#кинопремьера'],
            'сериал': ['#сериал', '#сериалы', '#телесериал'],
            'актер': ['#актеры', '#актрисы', '#звезды'],
            'режиссер': ['#режиссер', '#продюсер', '#съемки'],
            'премьер': ['#премьера', '#новинка', '#релиз'],
            'трейлер': ['#трейлер', '#тизер', '#анонс'],
            'рецензи': ['#рецензия', '#отзыв', '#обзор'],
            'награ': ['#награды', '#премия', '#оскар']
        }

        # Добавляем извлеченные из текста хештеги
        all_hashtags = extracted_hashtags.copy()

        # Ищем ключевые слова в тексте и добавляем соответствующие хештеги
        text_lower = text.lower()
        added_count = 0
        max_additional_hashtags = 3

        for keyword, hashtags in keyword_hashtags.items():
            if keyword in text_lower and added_count < max_additional_hashtags:
                selected_hashtag = random.choice(hashtags)
                if selected_hashtag not in all_hashtags:
                    all_hashtags.append(selected_hashtag)
                    added_count += 1

        # Если хештегов мало, добавляем общие
        if len(all_hashtags) < 2:
            general_hashtags = ['#новости', '#интересное', '#популярное']
            for hashtag in general_hashtags:
                if hashtag not in all_hashtags and len(all_hashtags) < 3:
                    all_hashtags.append(hashtag)

        # Ограничиваем общее количество хештегов
        final_hashtags = all_hashtags[:5]

        return ' '.join(final_hashtags) if final_hashtags else ''

    def mark_as_published(self, post_id, message_id):
        """Отметка поста как опубликованного"""
        print(f"DEBUG: 📝 Обновляем статус поста {post_id}")

        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE scheduled_posts 
                SET status = 'published', message_id = ?
                WHERE id = ?
            ''', (message_id, post_id))

            conn.commit()
            conn.close()

            print(f"DEBUG: ✅ Статус поста {post_id} обновлен")
            return True

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка обновления статуса поста {post_id}: {e}")
            return False

    def stop_scheduler(self):
        """Остановка планировщика"""
        self.is_running = False
        logger.info("Планировщик публикаций остановлен")
        print("DEBUG: 🛑 Планировщик остановлен")