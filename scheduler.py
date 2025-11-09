import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class PostScheduler:
    def __init__(self, database, bot):
        self.db = database
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()

    async def publish_scheduled_posts(self):
        """Публикация запланированных постов - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            logger.info("🔍 Проверка запланированных постов...")
            pending_posts = self.db.get_pending_posts()
            logger.info(f"📋 Найдено {len(pending_posts)} постов для публикации")

            for post in pending_posts:
                post_id, channel_id, content_type, text_content, file_id = post

                logger.info(f"🔄 Публикация поста {post_id} в канале {channel_id}")

                try:
                    # Публикуем пост в зависимости от типа контента
                    if content_type == 'text':
                        await self.bot.send_message(
                            chat_id=channel_id,
                            text=text_content
                        )
                        logger.info(f"✅ Текстовый пост {post_id} опубликован")

                    elif content_type == 'photo':
                        await self.bot.send_photo(
                            chat_id=channel_id,
                            photo=file_id,
                            caption=text_content or None
                        )
                        logger.info(f"✅ Фото пост {post_id} опубликован")

                    elif content_type == 'video':
                        await self.bot.send_video(
                            chat_id=channel_id,
                            video=file_id,
                            caption=text_content or None
                        )
                        logger.info(f"✅ Видео пост {post_id} опубликован")

                    elif content_type == 'document':
                        await self.bot.send_document(
                            chat_id=channel_id,
                            document=file_id,
                            caption=text_content or None
                        )
                        logger.info(f"✅ Документ пост {post_id} опубликован")

                    # Отмечаем пост как опубликованный
                    self.db.mark_post_published(post_id)
                    logger.info(f"✅ Пост {post_id} отмечен как опубликованный")

                except Exception as e:
                    logger.error(f"❌ Ошибка при публикации поста {post_id}: {str(e)}")
                    # Не помечаем пост как опубликованный при ошибке

        except Exception as e:
            logger.error(f"❌ Критическая ошибка в планировщике: {str(e)}")

    def start_periodic_check(self):
        """Запуск периодической проверки постов - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            # Запускаем проверку каждые 30 секунд
            self.scheduler.add_job(
                self.publish_scheduled_posts,
                'interval',
                seconds=30,
                id='periodic_post_check'
            )
            logger.info("✅ Периодическая проверка постов запущена (каждые 30 секунд)")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска периодической проверки: {str(e)}")

    def schedule_single_post(self, post_id, scheduled_time):
        """Планирование отдельного поста на конкретное время"""
        try:
            trigger = DateTrigger(run_date=scheduled_time)
            self.scheduler.add_job(
                self._publish_single_post,
                trigger,
                args=[post_id],
                id=f'post_{post_id}'
            )
            logger.info(f"✅ Пост {post_id} запланирован на {scheduled_time}")
        except Exception as e:
            logger.error(f"❌ Ошибка планирования поста {post_id}: {str(e)}")

    async def _publish_single_post(self, post_id):
        """Публикация одного конкретного поста"""
        try:
            # Получаем информацию о посте
            with self.db.conn:
                cursor = self.db.conn.cursor()
                cursor.execute('''
                    SELECT p.channel_id, p.content_type, p.text_content, p.file_id
                    FROM posts p WHERE p.post_id = ? AND p.published = FALSE
                ''', (post_id,))
                post = cursor.fetchone()

            if post:
                channel_id, content_type, text_content, file_id = post
                await self._send_post(channel_id, content_type, text_content, file_id)
                self.db.mark_post_published(post_id)
                logger.info(f"✅ Одиночный пост {post_id} опубликован")
        except Exception as e:
            logger.error(f"❌ Ошибка публикации одиночного поста {post_id}: {str(e)}")

    async def _send_post(self, channel_id, content_type, text_content, file_id):
        """Отправка поста в канал"""
        try:
            if content_type == 'text':
                await self.bot.send_message(chat_id=channel_id, text=text_content)
            elif content_type == 'photo':
                await self.bot.send_photo(
                    chat_id=channel_id,
                    photo=file_id,
                    caption=text_content or None
                )
            elif content_type == 'video':
                await self.bot.send_video(
                    chat_id=channel_id,
                    video=file_id,
                    caption=text_content or None
                )
            elif content_type == 'document':
                await self.bot.send_document(
                    chat_id=channel_id,
                    document=file_id,
                    caption=text_content or None
                )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста в канал {channel_id}: {str(e)}")
            raise e