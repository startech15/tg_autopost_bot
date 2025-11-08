import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, Bot, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes
from telegram.ext import filters
import re
import sqlite3

from config import BOT_TOKEN, CHANNEL_ID, ADMIN_IDS, DB_FILE
from database import ContentDatabase
from content_manager import ContentManager
from scheduler import PostScheduler

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация компонентов
db = ContentDatabase()
content_manager = ContentManager()
scheduler = PostScheduler(DB_FILE)

# Глобальные переменные для хранения состояния пользователей
user_states = {}


class TelegramSchedulerBot:
    def __init__(self):
        self.application = None

    async def initialize(self):
        """Инициализация бота"""
        self.application = Application.builder().token(BOT_TOKEN).build()
        await self.setup_handlers()
        await self.setup_menu_commands()

    async def setup_menu_commands(self):
        """Настройка меню команд бота"""
        commands = [
            BotCommand("start", "🚀 Начать работу с ботом"),
            BotCommand("help", "📖 Получить справку по командам"),
            BotCommand("schedule", "📅 Запланировать новый пост"),
            BotCommand("myschedule", "📋 Показать мои запланированные посты"),
            BotCommand("calendar", "🗓️ Календарь публикаций"),
            BotCommand("stats", "📊 Статистика публикаций"),
            BotCommand("all_posts", "📂 Все посты в базе данных"),
            BotCommand("publish_now", "⚡ Немедленно опубликовать пост"),
            BotCommand("cancel", "❌ Отменить запланированный пост"),
            BotCommand("reschedule", "🕐 Перенести публикацию"),
            BotCommand("check_files", "🔍 Проверить загруженные файлы"),
            BotCommand("debug", "🐛 Отладочная информация")
        ]

        await self.application.bot.set_my_commands(commands)
        print("✅ Меню команд настроено")

    async def setup_handlers(self):
        """Настройка обработчиков"""
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("schedule", self.schedule_command))
        self.application.add_handler(CommandHandler("myschedule", self.myschedule_command))
        self.application.add_handler(CommandHandler("calendar", self.calendar_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("all_posts", self.all_posts_command))
        self.application.add_handler(CommandHandler("publish_now", self.publish_now_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        self.application.add_handler(CommandHandler("reschedule", self.reschedule_command))
        self.application.add_handler(CommandHandler("check_files", self.check_files_command))
        self.application.add_handler(CommandHandler("debug", self.debug_command))

        # Обработчики медиа
        self.application.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION, self.handle_media_with_caption))
        self.application.add_handler(MessageHandler(filters.VIDEO & filters.CAPTION, self.handle_media_with_caption))
        self.application.add_handler(
            MessageHandler(filters.Document.ALL & filters.CAPTION, self.handle_media_with_caption))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input))

    async def start_bot(self):
        """Запуск бота"""
        if not self.application:
            await self.initialize()

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("Бот планировщика запущен")
        print("✅ Бот успешно запущен и готов к работе!")
        print("📋 Меню команд доступно в интерфейсе Telegram")

    async def stop_bot(self):
        """Остановка бота"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

        logger.info("Бот планировщика остановлен")

    def get_user_state(self, user_id):
        """Получение состояния пользователя"""
        return user_states.get(user_id, {})

    def set_user_state(self, user_id, state, temp_data=None):
        """Установка состояния пользователя"""
        user_states[user_id] = {
            'state': state,
            'temp_data': temp_data or {}
        }

    def clear_user_state(self, user_id):
        """Очистка состояния пользователя"""
        if user_id in user_states:
            del user_states[user_id]

    # КОМАНДЫ БОТА
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет доступа к этому боту.")
            return

        welcome_text = """
🤖 **Бот-планировщик публикаций для Telegram**

✨ **Основные команды:**
📅 /schedule - Запланировать новый пост
📋 /myschedule - Мои запланированные посты
🗓️ /calendar - Календарь публикаций
📊 /stats - Статистика публикаций

⚡ **Быстрые действия:**
⚡ /publish_now - Немедленно опубликовать пост
❌ /cancel - Отменить запланированный пост
🕐 /reschedule - Перенести публикацию

🔧 **Дополнительные команды:**
📖 /help - Полная справка по командам
📂 /all_posts - Все посты в базе данных
🔍 /check_files - Проверить загруженные файлы
🐛 /debug - Отладочная информация

🌟 **Автоформатирование:**
• Эмодзи для каждого абзаца
• Автоматические хештеги из текста
• Красивое оформление

💡 **Быстрый старт:**
1. Используйте /schedule
2. Отправьте контент (фото, видео, документ или текст)
3. Укажите дату и время публикации
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        self.clear_user_state(user_id)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📖 **Помощь по использованию планировщика**

**📅 Основные команды:**
• /schedule - Запланировать новый пост
• /myschedule - Мои запланированные посты  
• /calendar - Календарь публикаций
• /stats - Статистика публикаций

**⚡ Быстрые действия:**
• /publish_now ID - Немедленно опубликовать пост
• /cancel ID - Отменить запланированный пост
• /reschedule ID ВРЕМЯ - Перенести публикацию

**🔧 Дополнительные команды:**
• /all_posts - Все посты в базе данных
• /check_files - Проверить загруженные файлы
• /debug - Отладочная информация

**⏰ Форматы даты и времени:**
• `15:30` - сегодня в 15:30
• `18:00 25.12` - 25 декабря в 18:00
• `+2h` - через 2 часа
• `+1d` - через 1 день
• `tomorrow 14:00` - завтра в 14:00

**📄 Поддерживаемые типы контента:**
• 📷 Фотографии (с подписью)
• 🎥 Видео (с подписью)
• 📄 Документы (с подписью)
• 📝 Текстовые сообщения

**🌟 Автоформатирование:**
Текст автоматически форматируется:
• Добавляются эмодзи к абзацам
• Извлекаются хештеги из текста
• Добавляются релевантные хештеги

**💡 Примеры использования:**
• `/schedule` - начать планирование
• `/cancel 5` - отменить пост с ID 5
• `/reschedule 5 18:00` - перенести пост 5 на 18:00
• `/publish_now 5` - немедленно опубликовать пост 5
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса планирования"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        self.set_user_state(user_id, 'waiting_for_content')

        await update.message.reply_text(
            "📝 **Режим планирования**\n\n"
            "Отправьте мне контент для публикации:\n"
            "- 📷 Фото с подписью\n"
            "- 🎥 Видео с подписью\n"
            "- 📄 Документ с подписью\n"
            "- 📝 Текст сообщения\n\n"
            "После загрузки контента я запрошу дату и время публикации.",
            parse_mode='Markdown'
        )

    async def handle_media_with_caption(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка медиа с подписью"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            return

        user_state = self.get_user_state(user_id)

        if user_state.get('state') != 'waiting_for_content':
            # Если не в режиме планирования, предлагаем начать
            await update.message.reply_text(
                "💡 Чтобы запланировать этот контент, сначала используйте /schedule"
            )
            return

        try:
            # Определяем тип контента
            if update.message.photo:
                content_type = 'photo'
                file = await update.message.photo[-1].get_file()
                file_name = f"photo_{int(datetime.now().timestamp())}.jpg"
            elif update.message.video:
                content_type = 'video'
                file = await update.message.video.get_file()
                file_name = f"video_{int(datetime.now().timestamp())}.mp4"
            else:  # document
                content_type = 'document'
                file = await update.message.document.get_file()
                file_name = update.message.document.file_name or f"document_{int(datetime.now().timestamp())}"

            print(f"DEBUG: Сохраняем {content_type} файл: {file_name}")

            # Сохраняем файл (АСИНХРОННО!)
            file_path = await content_manager.save_file(content_type, file, file_name)
            caption = update.message.caption

            print(f"DEBUG: Файл сохранен: {file_path}")
            print(f"DEBUG: Подпись: {caption}")

            # Сохраняем временные данные
            self.set_user_state(user_id, 'waiting_for_schedule', {
                'content_type': content_type,
                'file_path': file_path,
                'caption': caption
            })

            await update.message.reply_text(
                f"✅ **{content_type.upper()} сохранен!**\n\n"
                f"Теперь укажите время публикации:\n\n"
                f"**Примеры:**\n"
                f"• `15:30` - сегодня в 15:30\n"
                f"• `18:00 25.12` - 25 декабря\n"
                f"• `+2h` - через 2 часа\n"
                f"• `tomorrow 14:00` - завтра в 14:00\n\n"
                f"Отправьте время в любом из этих форматов:",
                parse_mode='Markdown'
            )

        except Exception as e:
            print(f"DEBUG: Ошибка обработки медиа: {e}")
            await update.message.reply_text("❌ Ошибка обработки медиа. Попробуйте снова.")
            self.clear_user_state(user_id)

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка всех текстовых сообщений"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            return

        user_state = self.get_user_state(user_id)
        text = update.message.text

        print(f"DEBUG: Получен текст от {user_id}: '{text}'")
        print(f"DEBUG: Состояние пользователя: {user_state}")

        # Если пользователь в состоянии ожидания времени
        if user_state.get('state') == 'waiting_for_schedule':
            await self.process_schedule_time(update, text, user_state)
        elif user_state.get('state') == 'waiting_for_content':
            # Если пользователь отправил текст вместо медиа
            await self.handle_text_content(update, text)
        else:
            # Обычное текстовое сообщение
            await update.message.reply_text(
                "💡 Чтобы запланировать пост, используйте /schedule"
            )

    async def handle_text_content(self, update: Update, text):
        """Обработка текстового контента для планирования"""
        user_id = update.effective_user.id

        try:
            print(f"DEBUG: Сохраняем текстовый контент: {text[:50]}...")

            # Сохраняем текст в файл
            file_path = content_manager.save_text_content(text)

            print(f"DEBUG: Текст сохранен в: {file_path}")

            # Сохраняем временные данные
            self.set_user_state(user_id, 'waiting_for_schedule', {
                'content_type': 'text',
                'file_path': file_path,
                'caption': text
            })

            await update.message.reply_text(
                "✅ **Текст сохранен!**\n\n"
                "Теперь укажите время публикации:\n\n"
                "**Примеры:**\n"
                "• `15:30` - сегодня в 15:30\n"
                "• `18:00 25.12` - 25 декабря\n"
                "• `+2h` - через 2 часа\n"
                "• `tomorrow 14:00` - завтра в 14:00\n\n"
                "Отправьте время в любом из этих форматов:",
                parse_mode='Markdown'
            )

        except Exception as e:
            print(f"DEBUG: Ошибка сохранения текста: {e}")
            await update.message.reply_text("❌ Ошибка сохранения текста. Попробуйте снова.")
            self.clear_user_state(user_id)

    async def process_schedule_time(self, update: Update, time_input, user_state):
        """Обработка времени публикации"""
        user_id = update.effective_user.id

        try:
            print(f"DEBUG: Обрабатываем время: '{time_input}'")

            scheduled_time = self.parse_time_input(time_input)

            if not scheduled_time:
                await update.message.reply_text(
                    "❌ Неверный формат времени.\n\n"
                    "**Попробуйте так:**\n"
                    "• 15:30\n"
                    "• 18:00 25.12\n"
                    "• +2h\n"
                    "• tomorrow 14:00\n\n"
                    "Отправьте время еще раз:",
                    parse_mode='Markdown'
                )
                return

            # Проверяем что время в будущем
            if scheduled_time <= datetime.now():
                await update.message.reply_text(
                    "❌ Время публикации должно быть в будущем!\n"
                    "Укажите более позднее время:"
                )
                return

            print(f"DEBUG: Время распознано: {scheduled_time}")

            # Сохраняем запланированный пост
            post_id = db.add_scheduled_post(
                user_id=user_id,
                content_type=user_state['temp_data']['content_type'],
                file_path=user_state['temp_data']['file_path'],
                caption=user_state['temp_data']['caption'],
                scheduled_time=scheduled_time
            )

            if post_id is None:
                await update.message.reply_text(
                    "❌ Ошибка сохранения поста в базу данных. Попробуйте снова."
                )
                return

            # Очищаем состояние
            self.clear_user_state(user_id)

            await update.message.reply_text(
                f"✅ **Пост успешно запланирован!**\n\n"
                f"📅 ID: {post_id}\n"
                f"⏰ Время: {scheduled_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"📋 Тип: {user_state['temp_data']['content_type']}\n\n"
                f"🌟 *Текст будет автоматически отформатирован:*\n"
                f"• Добавлены эмодзи к абзацам\n"
                f"• Извлечены хештеги из текста\n"
                f"• Добавлены релевантные хештеги\n\n"
                f"Пост будет автоматически опубликован в указанное время.",
                parse_mode='Markdown'
            )

            print(f"DEBUG: Пост {post_id} успешно запланирован")

        except Exception as e:
            print(f"DEBUG: Критическая ошибка в process_schedule_time: {e}")
            await update.message.reply_text("❌ Критическая ошибка. Начните заново с /schedule")
            self.clear_user_state(user_id)

    def parse_time_input(self, time_input):
        """Парсинг ввода времени"""
        time_input = time_input.lower().strip()
        now = datetime.now()

        try:
            # Формат: 15:30
            if re.match(r'^\d{1,2}:\d{2}$', time_input):
                hours, minutes = map(int, time_input.split(':'))
                scheduled = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                if scheduled <= now:
                    scheduled += timedelta(days=1)
                return scheduled

            # Формат: 18:00 25.12
            match = re.match(r'^(\d{1,2}:\d{2})\s+(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$', time_input)
            if match:
                time_part, day, month, year = match.groups()
                hours, minutes = map(int, time_part.split(':'))
                year = int(year) if year else now.year
                month = int(month)
                day = int(day)
                return datetime(year, month, day, hours, minutes, 0)

            # Формат: +2h, +30m
            match = re.match(r'^\+(\d+)([hmd])$', time_input)
            if match:
                value, unit = int(match.group(1)), match.group(2)
                if unit == 'h':
                    return now + timedelta(hours=value)
                elif unit == 'm':
                    return now + timedelta(minutes=value)
                elif unit == 'd':
                    return now + timedelta(days=value)

            # Формат: tomorrow 14:00
            if time_input.startswith('tomorrow'):
                time_part = time_input.replace('tomorrow', '').strip()
                if re.match(r'^\d{1,2}:\d{2}$', time_part):
                    hours, minutes = map(int, time_part.split(':'))
                    scheduled = (now + timedelta(days=1)).replace(hour=hours, minute=minutes, second=0, microsecond=0)
                    return scheduled

            # Формат: YYYY-MM-DD HH:MM
            try:
                return datetime.strptime(time_input, '%Y-%m-%d %H:%M')
            except ValueError:
                pass

        except Exception:
            pass

        return None

    async def calendar_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать календарь публикаций"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        try:
            schedule = db.get_user_schedule(user_id, days=14)  # 2 недели

            if not schedule:
                await update.message.reply_text(
                    "📅 На ближайшие 2 недели нет запланированных публикаций.\n\n"
                    "Используйте /schedule чтобы запланировать первый пост!"
                )
                return

            calendar_text = "🗓️ **Календарь публикаций (14 дней):**\n\n"

            current_date = None
            for post in schedule:
                post_time = datetime.strptime(post['scheduled_time'], '%Y-%m-%d %H:%M:%S')
                post_date = post_time.date()

                if post_date != current_date:
                    current_date = post_date
                    calendar_text += f"\n**{current_date.strftime('%d.%m.%Y')}:**\n"

                emoji = self.get_media_emoji(post['content_type'])
                time_str = post_time.strftime('%H:%M')
                preview = post['caption'][:30] + "..." if post['caption'] and len(post['caption']) > 30 else post[
                                                                                                                 'caption'] or 'без подписи'

                calendar_text += f"{emoji} `{time_str}` ID:{post['id']} {preview}\n"

            await update.message.reply_text(calendar_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка календаря: {e}")
            await update.message.reply_text("❌ Ошибка загрузки календаря")

    async def myschedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Мои запланированные посты"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        try:
            schedule = db.get_user_schedule(user_id, days=30)
            stats = db.get_post_stats(user_id)

            if not schedule:
                await update.message.reply_text(
                    "📭 Нет запланированных публикаций.\n\n"
                    "💡 Используйте /schedule чтобы запланировать первый пост!"
                )
                return

            schedule_text = f"""
📋 **Мои запланированные публикации:**

📊 Статистика:
✅ Опубликовано: {stats['published']}
⏳ Запланировано: {stats['scheduled']}
❌ Отменено: {stats['cancelled']}

**Ближайшие посты:**
"""

            for post in schedule[:10]:  # Показываем первые 10
                emoji = self.get_media_emoji(post['content_type'])
                time = datetime.strptime(post['scheduled_time'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m %H:%M')
                preview = post['caption'][:40] + "..." if post['caption'] and len(post['caption']) > 40 else post[
                                                                                                                 'caption'] or 'без подписи'

                schedule_text += f"\n{emoji} `ID:{post['id']}` {time}\n   {preview}\n"

            if len(schedule) > 10:
                schedule_text += f"\n... и еще {len(schedule) - 10} постов"

            schedule_text += "\n\nℹ️ Используйте /cancel ID для отмены"

            await update.message.reply_text(schedule_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка расписания: {e}")
            await update.message.reply_text("❌ Ошибка загрузки расписания")

    async def all_posts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все посты в БД"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            return

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            # Получаем ВСЕ посты
            cursor.execute('SELECT * FROM scheduled_posts ORDER BY id DESC')
            all_posts = cursor.fetchall()
            conn.close()

            response = f"📂 **Все посты в БД:** {len(all_posts)} записей\n\n"

            for post in all_posts:
                status_emoji = "✅" if post[6] == 'published' else "⏳" if post[6] == 'scheduled' else "❌"
                response += f"{status_emoji} **ID:{post[0]}** - {post[2]} - {post[6]}\n"
                response += f"   ⏰ {post[5]}\n"
                response += f"   💬 Message ID: {post[8] or 'нет'}\n"
                response += f"   📝 {post[4][:30] + '...' if post[4] and len(post[4]) > 30 else post[4] or 'нет подписи'}\n\n"

            if not all_posts:
                response = "📭 База данных пуста"

            await update.message.reply_text(response, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена запланированного поста"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        if not context.args:
            await update.message.reply_text(
                "❌ Укажите ID поста: /cancel 123\n\n"
                "ID можно посмотреть в /myschedule"
            )
            return

        try:
            post_id = int(context.args[0])

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE scheduled_posts 
                SET status = 'cancelled'
                WHERE id = ? AND user_id = ? AND status = 'scheduled'
            ''', (post_id, user_id))

            affected = cursor.rowcount
            conn.commit()
            conn.close()

            if affected > 0:
                await update.message.reply_text(f"✅ Пост ID:{post_id} отменен")
            else:
                await update.message.reply_text(
                    f"❌ Не удалось отменить пост ID:{post_id}\n"
                    f"Возможно, пост уже опубликован или не существует"
                )

        except ValueError:
            await update.message.reply_text("❌ Неверный ID поста")
        except Exception as e:
            logger.error(f"Ошибка отмены: {e}")
            await update.message.reply_text("❌ Ошибка отмены поста")

    async def reschedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Перенос публикации"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Используйте: /reschedule ID ВРЕМЯ\n\n"
                "Пример: /reschedule 5 18:00"
            )
            return

        try:
            post_id = int(context.args[0])
            time_input = ' '.join(context.args[1:])

            new_time = self.parse_time_input(time_input)
            if not new_time:
                await update.message.reply_text("❌ Неверный формат времени")
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE scheduled_posts 
                SET scheduled_time = ?
                WHERE id = ? AND user_id = ? AND status = 'scheduled'
            ''', (new_time, post_id, user_id))

            affected = cursor.rowcount
            conn.commit()
            conn.close()

            if affected > 0:
                await update.message.reply_text(
                    f"✅ Пост ID:{post_id} перенесен на {new_time.strftime('%d.%m.%Y %H:%M')}"
                )
            else:
                await update.message.reply_text(
                    f"❌ Не удалось перенести пост ID:{post_id}\n"
                    f"Возможно, пост уже опубликован или не существует"
                )

        except ValueError:
            await update.message.reply_text("❌ Неверный ID поста")
        except Exception as e:
            logger.error(f"Ошибка переноса: {e}")
            await update.message.reply_text("❌ Ошибка переноса поста")

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика публикаций"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ У вас нет доступа к этой команде.")
            return

        try:
            stats = db.get_post_stats(user_id)
            schedule = db.get_user_schedule(user_id, days=7)

            stats_text = f"""
📊 **Статистика публикаций**

📨 Всего постов: {stats['total']}
✅ Опубликовано: {stats['published']}
⏳ Запланировано: {stats['scheduled']}
❌ Отменено: {stats['cancelled']}

📅 **На этой неделе:**
"""

            if schedule:
                # Группируем по дням
                from collections import defaultdict
                daily_stats = defaultdict(int)

                for post in schedule:
                    date = datetime.strptime(post['scheduled_time'], '%Y-%m-%d %H:%M:%S').strftime('%a')
                    daily_stats[date] += 1

                for day, count in daily_stats.items():
                    stats_text += f"   {day}: {count} пост(ов)\n"
            else:
                stats_text += "   Нет запланированных постов\n"

            stats_text += "\n💡 Используйте /schedule для добавления новых постов"

            await update.message.reply_text(stats_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка статистики: {e}")
            await update.message.reply_text("❌ Ошибка загрузки статистики")

    async def publish_now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Принудительно опубликовать пост"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            return

        if not context.args:
            await update.message.reply_text("❌ Укажите ID поста: /publish_now 123")
            return

        try:
            post_id = int(context.args[0])

            # Получаем пост из БД
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scheduled_posts WHERE id = ?', (post_id,))
            post_data = cursor.fetchone()
            conn.close()

            if not post_data:
                await update.message.reply_text(f"❌ Пост с ID {post_id} не найден")
                return

            if post_data[6] == 'published':
                await update.message.reply_text(f"❌ Пост ID {post_id} уже опубликован")
                return

            # Создаем структуру поста для публикации
            post = {
                'id': post_data[0],
                'user_id': post_data[1],
                'content_type': post_data[2],
                'file_path': post_data[3],
                'caption': post_data[4],
                'scheduled_time': post_data[5],
                'status': post_data[6]
            }

            print(f"DEBUG: 🚀 Принудительная публикация поста {post_id}")

            # Публикуем пост
            success = await scheduler.publish_post(post)

            if success:
                await update.message.reply_text(f"✅ Пост ID {post_id} успешно опубликован!")
            else:
                await update.message.reply_text(f"❌ Ошибка публикации поста ID {post_id}")

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для отладки"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            return

        # Проверяем планировщик
        posts_to_publish = scheduler.get_posts_to_publish()
        all_posts = db.get_user_schedule(user_id, days=30)

        response = f"""
🔧 **Отладочная информация:**

📊 **Планировщик:**
• Постов для публикации: {len(posts_to_publish)}
• Всего запланировано: {len([p for p in all_posts if p['status'] == 'scheduled'])}
• Опубликовано: {len([p for p in all_posts if p['status'] == 'published'])}

⏰ **Время:**
• Сервер: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
• UTC: {datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S')}

🔄 **Состояние:**
• User ID: {user_id}
• State: {self.get_user_state(user_id)}
"""

        await update.message.reply_text(response, parse_mode='Markdown')

    async def check_files_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка загруженных файлов"""
        user_id = update.effective_user.id

        if user_id not in ADMIN_IDS:
            return

        content_manager.list_uploaded_files()

        await update.message.reply_text(
            "🔍 Проверка файлов выполнена. Смотрите вывод в консоли."
        )

    def get_media_emoji(self, media_type):
        """Получить emoji для типа медиа"""
        emoji_map = {
            'photo': '📷',
            'video': '🎥',
            'document': '📄',
            'text': '📝'
        }
        return emoji_map.get(media_type, '📁')


async def main():
    """Основная функция"""
    bot = TelegramSchedulerBot()

    print("🚀 Запуск улучшенного бота-планировщика...")
    print("🌟 Новые функции:")
    print("   • 📋 Меню команд в интерфейсе Telegram")
    print("   • ✨ Автоформатирование текста с эмодзи")
    print("   • 🏷️ Умные хештеги из текста")
    print("   • 💾 Исправлено сохранение файлов")

    try:
        # ЗАПУСКАЕМ ОБА ПЛАНИРОВЩИКА
        print("🔄 Запускаем планировщики...")
        scheduler_task1 = asyncio.create_task(scheduler.start_scheduler())
        scheduler_task2 = asyncio.create_task(scheduler.simple_scheduler())

        # Даем планировщику время на запуск
        await asyncio.sleep(2)

        # ЗАПУСКАЕМ БОТА
        print("🤖 Запускаем бота...")
        await bot.start_bot()

        # Ждем завершения обеих задач
        print("⏳ Система запущена. Ожидаем команды...")
        await asyncio.gather(scheduler_task1, scheduler_task2, return_exceptions=True)

    except KeyboardInterrupt:
        print("🛑 Получен сигнал остановки...")
    except Exception as e:
        print(f"💥 Ошибка в main: {e}")
    finally:
        print("🧹 Останавливаем систему...")
        # Останавливаем планировщик
        scheduler.stop_scheduler()

        # Останавливаем бота
        await bot.stop_bot()

        print("✅ Система остановлена")


if __name__ == "__main__":
    asyncio.run(main())