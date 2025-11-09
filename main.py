import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.ext import CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_TOKEN
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
scheduler = PostScheduler("scheduler_database.db")

# Состояния для ConversationHandler
SELECTING_CHANNEL, SELECTING_CONTENT_TYPE, WAITING_CONTENT, WAITING_CAPTION, WAITING_SCHEDULE_TIME = range(5)


class TelegramAutopostBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Базовые команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("myschedule", self.myschedule_command))
        self.application.add_handler(CommandHandler("calendar", self.calendar_command))
        self.application.add_handler(CommandHandler("publish_now", self.publish_now_command))

        # Команды управления каналами
        self.application.add_handler(CommandHandler("channels", self.channels_command))
        self.application.add_handler(CommandHandler("add_channel", self.add_channel_command))
        self.application.add_handler(CommandHandler("set_channel", self.set_channel_command))

        # Обработчик для планирования постов
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('schedule', self.schedule_command)],
            states={
                SELECTING_CHANNEL: [
                    CallbackQueryHandler(self.select_channel_callback, pattern='^channel_')
                ],
                SELECTING_CONTENT_TYPE: [
                    CallbackQueryHandler(self.select_content_type_callback, pattern='^(photo|video|document|text)$')
                ],
                WAITING_CONTENT: [
                    MessageHandler(filters.ALL, self.content_input_handler)
                ],
                WAITING_CAPTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.caption_input_handler),
                    CommandHandler('skip', self.skip_caption_command)
                ],
                WAITING_SCHEDULE_TIME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.schedule_time_handler)
                ]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_command)],
            per_message=False
        )
        self.application.add_handler(conv_handler)

        # Обработчики для отмены и переноса
        self.application.add_handler(CommandHandler("cancel_post", self.cancel_post_command))
        self.application.add_handler(CommandHandler("reschedule", self.reschedule_command))

        # Обработчик для немедленной публикации
        self.application.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.Document.ALL | (filters.TEXT & ~filters.COMMAND),
            self.publish_now_handler
        ))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - начало работы с ботом"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name

        welcome_text = f"""
🤖 <b>Добро пожаловать, {user_name}!</b>

Я - ваш помощник для автоматической публикации контента в Telegram каналах.

<b>📋 Основные команды:</b>
/schedule - Запланировать новый пост
/myschedule - Мои запланированные посты  
/calendar - Календарь публикаций
/stats - Статистика постов

<b>📢 Управление каналами:</b>
/channels - Мои каналы
/add_channel - Добавить канал
/set_channel - Выбрать активный канал

<b>⚡ Быстрые действия:</b>
/publish_now - Немедленная публикация
/cancel_post - Отмена поста
/reschedule - Перенос публикации

Для начала работы добавьте канал с помощью /add_channel и установите его активным с помощью /set_channel.
        """

        await update.message.reply_text(welcome_text, parse_mode='HTML')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - справка по командам"""
        help_text = """
<b>📖 Справка по командам:</b>

<b>📋 Основные команды:</b>
/start - Начало работы
/help - Эта справка
/schedule - Запланировать новый пост
/myschedule - Мои запланированные посты (7 дней)
/calendar - Календарь публикаций (30 дней)
/stats - Статистика постов

<b>📢 Управление каналами:</b>
/channels - Список моих каналов
/add_channel - Добавить новый канал
/set_channel - Выбрать активный канал

<b>⚡ Быстрые действия:</b>
/publish_now - Немедленная публикация
/cancel_post - Отмена запланированного поста
/reschedule - Перенос времени публикации

<b>💡 Как использовать:</b>
1. Добавьте канал командой /add_channel
2. Установите активный канал /set_channel
3. Планируйте посты командой /schedule
4. Следите за расписанием через /myschedule
        """
        await update.message.reply_text(help_text, parse_mode='HTML')

    async def channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /channels - список каналов пользователя"""
        user_id = update.effective_user.id

        channels = db.get_user_channels(user_id)
        active_channel = db.get_active_channel(user_id)

        if not channels:
            await update.message.reply_text(
                "📢 У вас пока нет добавленных каналов.\n\n"
                "Добавьте канал с помощью команды /add_channel"
            )
            return

        channels_text = "📢 <b>Ваши каналы:</b>\n\n"
        for i, channel in enumerate(channels, 1):
            status = "✅ АКТИВЕН" if channel['channel_id'] == active_channel else "⚪"
            channels_text += f"{i}. {channel['channel_name']} ({channel['channel_id']}) {status}\n"

        channels_text += f"\nИспользуйте /set_channel для выбора активного канала."

        await update.message.reply_text(channels_text, parse_mode='HTML')

    async def add_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /add_channel - добавление нового канала"""
        user_id = update.effective_user.id
        args = context.args

        if not args:
            await update.message.reply_text(
                "📝 <b>Добавление канала</b>\n\n"
                "Использование: /add_channel @username_канала \"Название канала\"\n\n"
                "Пример:\n"
                "<code>/add_channel @my_channel \"Мой Техно Блог\"</code>",
                parse_mode='HTML'
            )
            return

        if len(args) < 2:
            await update.message.reply_text("❌ Пожалуйста, укажите username канала и название в кавычках.")
            return

        channel_id = args[0]
        channel_name = ' '.join(args[1:]).strip('"')

        # Проверяем формат channel_id
        if not channel_id.startswith('@'):
            channel_id = '@' + channel_id

        # Проверяем, что бот является администратором в канале
        try:
            bot = context.bot
            chat = await bot.get_chat(channel_id)

            # Проверяем права бота
            chat_member = await bot.get_chat_member(chat.id, bot.id)
            if chat_member.status not in ['administrator', 'creator']:
                await update.message.reply_text(
                    "❌ Бот не является администратором в указанном канале.\n\n"
                    "Пожалуйста, добавьте бота как администратора с правом публикации сообщений."
                )
                return

            # Добавляем канал в базу
            success = db.add_user_channel(user_id, channel_id, channel_name)

            if success:
                # Устанавливаем этот канал как активный по умолчанию
                db.set_active_channel(user_id, channel_id)

                await update.message.reply_text(
                    f"✅ Канал <b>{channel_name}</b> ({channel_id}) успешно добавлен и установлен как активный!\n\n"
                    f"Теперь вы можете планировать посты для этого канала.",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text("❌ Ошибка при добавлении канала.")

        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка при добавлении канала: {str(e)}\n\n"
                f"Убедитесь, что:\n"
                f"• Канал существует\n"
                f"• Бот добавлен как администратор\n"
                f"• Username канала указан правильно"
            )

    async def set_channel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /set_channel - выбор активного канала"""
        user_id = update.effective_user.id
        args = context.args

        channels = db.get_user_channels(user_id)

        if not channels:
            await update.message.reply_text(
                "❌ У вас нет добавленных каналов.\n\n"
                "Добавьте канал с помощью /add_channel"
            )
            return

        if not args:
            # Показываем список каналов для выбора
            keyboard = []
            for channel in channels:
                keyboard.append([InlineKeyboardButton(
                    f"{channel['channel_name']} ({channel['channel_id']})",
                    callback_data=f"channel_{channel['channel_id']}"
                )])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "📢 <b>Выберите активный канал:</b>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return

        # Если передан аргумент
        channel_id = args[0]
        if not channel_id.startswith('@'):
            channel_id = '@' + channel_id

        # Проверяем, что канал принадлежит пользователю
        user_channels = [ch['channel_id'] for ch in channels]
        if channel_id not in user_channels:
            await update.message.reply_text("❌ Этот канал не найден в вашем списке каналов.")
            return

        # Устанавливаем активный канал
        success = db.set_active_channel(user_id, channel_id)
        if success:
            channel_name = next(ch['channel_name'] for ch in channels if ch['channel_id'] == channel_id)
            await update.message.reply_text(
                f"✅ Активный канал изменен на: <b>{channel_name}</b> ({channel_id})",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Ошибка при установке активного канала.")

    async def schedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /schedule - начало процесса планирования"""
        user_id = update.effective_user.id
        print(f"DEBUG: 🚀 Начало планирования для пользователя {user_id}")

        # Проверяем наличие каналов
        channels = db.get_user_channels(user_id)
        if not channels:
            await update.message.reply_text(
                "❌ У вас нет добавленных каналов.\n\n"
                "Добавьте канал с помощью /add_channel перед планированием постов."
            )
            return ConversationHandler.END

        active_channel = db.get_active_channel(user_id)
        print(f"DEBUG: 📢 Активный канал: {active_channel}")

        if not active_channel:
            # Если нет активного канала, просим выбрать
            print(f"DEBUG: 🔄 Нет активного канала, показываем выбор")
            keyboard = []
            for channel in channels:
                keyboard.append([InlineKeyboardButton(
                    f"{channel['channel_name']} ({channel['channel_id']})",
                    callback_data=f"channel_{channel['channel_id']}"
                )])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "📢 <b>Выберите канал для публикации:</b>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return SELECTING_CHANNEL
        else:
            # Если есть активный канал, показываем выбор типа контента
            channel_name = next((ch['channel_name'] for ch in channels if ch['channel_id'] == active_channel),
                                active_channel)
            print(f"DEBUG: 📋 Показываем выбор типа контента для канала {channel_name}")

            keyboard = [
                [InlineKeyboardButton("📷 Фото", callback_data='photo')],
                [InlineKeyboardButton("🎥 Видео", callback_data='video')],
                [InlineKeyboardButton("📄 Документ", callback_data='document')],
                [InlineKeyboardButton("📝 Текст", callback_data='text')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"📋 <b>Выберите тип контента для публикации в {channel_name}:</b>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return SELECTING_CONTENT_TYPE

    async def select_channel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик выбора канала"""
        query = update.callback_query
        await query.answer()

        channel_id = query.data.replace('channel_', '')
        user_id = query.from_user.id

        print(f"DEBUG: ✅ Выбран канал {channel_id} для пользователя {user_id}")

        # Устанавливаем активный канал
        success = db.set_active_channel(user_id, channel_id)

        if success:
            # Получаем название канала
            channels = db.get_user_channels(user_id)
            channel_name = next((ch['channel_name'] for ch in channels if ch['channel_id'] == channel_id), channel_id)

            await query.edit_message_text(
                f"✅ Активный канал: <b>{channel_name}</b> ({channel_id})\n\n"
                f"Теперь выберите тип контента:",
                parse_mode='HTML'
            )

            # Показываем выбор типа контента
            keyboard = [
                [InlineKeyboardButton("📷 Фото", callback_data='photo')],
                [InlineKeyboardButton("🎥 Видео", callback_data='video')],
                [InlineKeyboardButton("📄 Документ", callback_data='document')],
                [InlineKeyboardButton("📝 Текст", callback_data='text')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.message.reply_text(
                "📋 <b>Выберите тип контента:</b>",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

            return SELECTING_CONTENT_TYPE
        else:
            await query.edit_message_text("❌ Ошибка при выборе канала.")
            return ConversationHandler.END

    async def select_content_type_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик выбора типа контента"""
        query = update.callback_query
        await query.answer()

        content_type = query.data
        context.user_data['content_type'] = content_type

        print(f"DEBUG: 📋 Выбран тип контента: {content_type}")

        content_type_names = {
            'photo': '📷 фото',
            'video': '🎥 видео',
            'document': '📄 документ',
            'text': '📝 текст'
        }

        await query.edit_message_text(
            f"✅ Выбран тип: <b>{content_type_names[content_type]}</b>\n\n"
            f"Теперь отправьте {'текст' if content_type == 'text' else 'файл'} для публикации:",
            parse_mode='HTML'
        )

        return WAITING_CONTENT

    async def content_input_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ввода контента"""
        user_id = update.effective_user.id
        content_type = context.user_data.get('content_type')

        print(f"DEBUG: 📥 Получен контент типа {content_type}")

        try:
            if content_type == 'text':
                # Для текстовых постов
                text_content = update.message.text
                print(f"DEBUG: 📝 Текстовый контент: {text_content[:100]}...")
                file_path = content_manager.save_text_content(text_content)
                context.user_data['file_path'] = file_path

                await update.message.reply_text(
                    "📝 Теперь введите подпись к посту (или отправьте /skip чтобы пропустить):"
                )
                return WAITING_CAPTION

            else:
                # Для файловых постов
                if content_type == 'photo' and update.message.photo:
                    file_data = update.message.photo[-1].get_file()
                    print(f"DEBUG: 📷 Получено фото")
                elif content_type == 'video' and update.message.video:
                    file_data = update.message.video.get_file()
                    print(f"DEBUG: 🎥 Получено видео")
                elif content_type == 'document' and update.message.document:
                    file_data = update.message.document.get_file()
                    print(f"DEBUG: 📄 Получен документ")
                else:
                    await update.message.reply_text(
                        f"❌ Пожалуйста, отправьте {'текст' if content_type == 'text' else content_type}"
                    )
                    return WAITING_CONTENT

                # Сохраняем файл с использованием await для file_data
                file_path = await content_manager.save_file(content_type, file_data)
                context.user_data['file_path'] = file_path

                await update.message.reply_text(
                    "📝 Теперь введите подпись к посту (или отправьте /skip чтобы пропустить):"
                )
                return WAITING_CAPTION

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка при обработке контента: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка при обработке контента: {str(e)}")
            return ConversationHandler.END


    async def caption_input_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ввода подписи"""
        caption = update.message.text
        print(f"DEBUG: 📝 Получена подпись: {caption}")

        context.user_data['caption'] = caption

        await update.message.reply_text(
            "⏰ Теперь укажите время публикации в формате:\n\n"
            "<code>ГГГГ-ММ-ДД ЧЧ:ММ</code>\n\n"
            "Примеры:\n"
            "<code>2024-12-31 20:00</code> - 31 декабря в 20:00\n"
            "<code>20:00</code> - сегодня в 20:00\n"
            "<code>+2 hours</code> - через 2 часа\n"
            "<code>tomorrow 14:00</code> - завтра в 14:00",
            parse_mode='HTML'
        )

        return WAITING_SCHEDULE_TIME

    async def skip_caption_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /skip для пропуска подписи"""
        print(f"DEBUG: ⏩ Пропуск подписи")
        context.user_data['caption'] = ""

        await update.message.reply_text(
            "⏰ Теперь укажите время публикации в формате:\n\n"
            "<code>ГГГГ-ММ-ДД ЧЧ:ММ</code>\n\n"
            "Примеры:\n"
            "<code>2024-12-31 20:00</code> - 31 декабря в 20:00\n"
            "<code>20:00</code> - сегодня в 20:00\n"
            "<code>+2 hours</code> - через 2 часа\n"
            "<code>tomorrow 14:00</code> - завтра в 14:00",
            parse_mode='HTML'
        )

        return WAITING_SCHEDULE_TIME

    async def schedule_time_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ввода времени публикации"""
        user_id = update.effective_user.id
        time_input = update.message.text
        active_channel = db.get_active_channel(user_id)

        print(f"DEBUG: ⏰ Введено время: {time_input}")

        try:
            # Парсим время
            scheduled_time = self.parse_time_input(time_input)

            if scheduled_time <= datetime.now():
                await update.message.reply_text("❌ Время публикации должно быть в будущем!")
                return WAITING_SCHEDULE_TIME

            # Сохраняем пост в базу
            post_id = db.add_scheduled_post(
                user_id=user_id,
                channel_id=active_channel,
                content_type=context.user_data['content_type'],
                file_path=context.user_data['file_path'],
                caption=context.user_data.get('caption', ''),
                scheduled_time=scheduled_time
            )

            if post_id:
                channels = db.get_user_channels(user_id)
                channel_name = next((ch['channel_name'] for ch in channels if ch['channel_id'] == active_channel),
                                    active_channel)

                await update.message.reply_text(
                    f"✅ Пост успешно запланирован!\n\n"
                    f"📅 <b>Канал:</b> {channel_name}\n"
                    f"⏰ <b>Время:</b> {scheduled_time.strftime('%d.%m.%Y в %H:%M')}\n"
                    f"📋 <b>Тип:</b> {context.user_data['content_type']}\n"
                    f"🆔 <b>ID поста:</b> {post_id}",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text("❌ Ошибка при сохранении поста в базу данных.")

        except ValueError as e:
            await update.message.reply_text(f"❌ Неверный формат времени: {str(e)}")
            return WAITING_SCHEDULE_TIME
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка при планировании: {str(e)}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

        return ConversationHandler.END

    def parse_time_input(self, time_input):
        """Парсинг времени"""
        time_input = time_input.strip().lower()
        now = datetime.now()

        print(f"DEBUG: ⏳ Парсим время: {time_input}")

        try:
            # Формат: ГГГГ-ММ-ДД ЧЧ:ММ
            if '-' in time_input and ':' in time_input:
                return datetime.strptime(time_input, '%Y-%m-%d %H:%M')

            # Формат: ЧЧ:ММ (сегодня)
            elif ':' in time_input and len(time_input) <= 5:
                time_part = datetime.strptime(time_input, '%H:%M').time()
                result = datetime.combine(now.date(), time_part)
                # Если время уже прошло сегодня, планируем на завтра
                if result <= now:
                    result += timedelta(days=1)
                return result

            # Относительное время: +N hours/minutes/days
            elif time_input.startswith('+'):
                parts = time_input[1:].split()
                if len(parts) == 2:
                    amount = int(parts[0])
                    unit = parts[1].lower()

                    if 'hour' in unit:
                        return now + timedelta(hours=amount)
                    elif 'minute' in unit:
                        return now + timedelta(minutes=amount)
                    elif 'day' in unit:
                        return now + timedelta(days=amount)
                    else:
                        raise ValueError("Неизвестная единица времени")
                else:
                    raise ValueError("Неверный формат относительного времени")

            # Завтра в ЧЧ:ММ
            elif time_input.startswith('tomorrow'):
                parts = time_input.split()
                if len(parts) == 2 and ':' in parts[1]:
                    time_part = datetime.strptime(parts[1], '%H:%M').time()
                    return datetime.combine(now.date() + timedelta(days=1), time_part)
                else:
                    raise ValueError("Неверный формат времени для 'tomorrow'")

            else:
                raise ValueError("Неизвестный формат времени")

        except Exception as e:
            raise ValueError(f"Не удалось распознать время: {str(e)}")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда отмены диалога"""
        print(f"DEBUG: ❌ Отмена операции")
        await update.message.reply_text("❌ Операция отменена.")
        return ConversationHandler.END

    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats - статистика постов"""
        user_id = update.effective_user.id
        active_channel = db.get_active_channel(user_id)

        if active_channel:
            stats = db.get_post_stats(user_id, active_channel)
            channels = db.get_user_channels(user_id)
            channel_name = next((ch['channel_name'] for ch in channels if ch['channel_id'] == active_channel),
                                active_channel)

            stats_text = f"""
📊 <b>Статистика для канала {channel_name}:</b>

📝 Всего постов: {stats['total']}
⏳ Запланировано: {stats['scheduled']}
✅ Опубликовано: {stats['published']}
❌ Отменено: {stats['cancelled']}
            """
        else:
            stats = db.get_post_stats(user_id)

            stats_text = f"""
📊 <b>Общая статистика по всем каналам:</b>

📝 Всего постов: {stats['total']}
⏳ Запланировано: {stats['scheduled']}
✅ Опубликовано: {stats['published']}
❌ Отменено: {stats['cancelled']}
            """

        await update.message.reply_text(stats_text, parse_mode='HTML')

    async def myschedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /myschedule - мои запланированные посты"""
        user_id = update.effective_user.id
        active_channel = db.get_active_channel(user_id)

        if active_channel:
            schedule = db.get_user_schedule(user_id, active_channel, days=7)
            channels = db.get_user_channels(user_id)
            channel_name = next((ch['channel_name'] for ch in channels if ch['channel_id'] == active_channel),
                                active_channel)

            if not schedule:
                await update.message.reply_text(
                    f"📅 У вас нет запланированных постов для канала <b>{channel_name}</b> на ближайшие 7 дней.",
                    parse_mode='HTML'
                )
                return

            schedule_text = f"📅 <b>Ваше расписание для {channel_name} (7 дней):</b>\n\n"
        else:
            schedule = db.get_user_schedule(user_id, days=7)

            if not schedule:
                await update.message.reply_text(
                    "📅 У вас нет запланированных постов на ближайшие 7 дней."
                )
                return

            schedule_text = "📅 <b>Ваше расписание по всем каналам (7 дней):</b>\n\n"

        for i, post in enumerate(schedule, 1):
            post_time = datetime.strptime(post['scheduled_time'], '%Y-%m-%d %H:%M:%S')
            schedule_text += (
                f"{i}. <b>ID:{post['id']}</b> | {post_time.strftime('%d.%m %H:%M')}\n"
                f"   📋 {post['content_type']} | {post['caption'][:50]}{'...' if len(post['caption']) > 50 else ''}\n"
            )

            if not active_channel:
                schedule_text += f"   📢 {post['channel_id']}\n"

            schedule_text += "\n"

        await update.message.reply_text(schedule_text, parse_mode='HTML')

    async def calendar_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /calendar - календарь публикаций"""
        user_id = update.effective_user.id
        active_channel = db.get_active_channel(user_id)

        if active_channel:
            schedule = db.get_user_schedule(user_id, active_channel, days=30)
            channels = db.get_user_channels(user_id)
            channel_name = next((ch['channel_name'] for ch in channels if ch['channel_id'] == active_channel),
                                active_channel)

            if not schedule:
                await update.message.reply_text(
                    f"📅 У вас нет запланированных постов для канала <b>{channel_name}</b> на ближайшие 30 дней.",
                    parse_mode='HTML'
                )
                return

            calendar_text = f"📅 <b>Календарь публикаций для {channel_name} (30 дней):</b>\n\n"
        else:
            schedule = db.get_user_schedule(user_id, days=30)

            if not schedule:
                await update.message.reply_text(
                    "📅 У вас нет запланированных постов на ближайшие 30 дней."
                )
                return

            calendar_text = "📅 <b>Календарь публикаций по всем каналам (30 дней):</b>\n\n"

        # Группируем по дням
        posts_by_day = {}
        for post in schedule:
            post_time = datetime.strptime(post['scheduled_time'], '%Y-%m-%d %H:%M:%S')
            day_key = post_time.strftime('%Y-%m-%d')
            if day_key not in posts_by_day:
                posts_by_day[day_key] = []
            posts_by_day[day_key].append(post)

        for day in sorted(posts_by_day.keys()):
            day_date = datetime.strptime(day, '%Y-%m-%d')
            calendar_text += f"<b>📅 {day_date.strftime('%d.%m.%Y')}:</b>\n"

            for post in posts_by_day[day]:
                post_time = datetime.strptime(post['scheduled_time'], '%Y-%m-%d %H:%M:%S')
                calendar_text += (
                    f"   🕐 {post_time.strftime('%H:%M')} | "
                    f"<b>ID:{post['id']}</b> | {post['content_type']}\n"
                )

            calendar_text += "\n"

        await update.message.reply_text(calendar_text, parse_mode='HTML')

    async def publish_now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /publish_now - немедленная публикация"""
        user_id = update.effective_user.id
        active_channel = db.get_active_channel(user_id)

        if not active_channel:
            await update.message.reply_text(
                "❌ У вас нет активного канала.\n\n"
                "Используйте /set_channel чтобы выбрать канал для публикации."
            )
            return

        context.user_data['publish_now'] = True
        await update.message.reply_text(
            "🚀 <b>Немедленная публикация</b>\n\n"
            "Отправьте контент для публикации (фото, видео, документ или текст).\n"
            "Пост будет опубликован сразу после получения.",
            parse_mode='HTML'
        )

    async def publish_now_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик немедленной публикации"""
        if not context.user_data.get('publish_now'):
            return

        user_id = update.effective_user.id
        active_channel = db.get_active_channel(user_id)

        if not active_channel:
            await update.message.reply_text("❌ Нет активного канала.")
            return

        try:
            # Определяем тип контента
            if update.message.photo:
                content_type = 'photo'
                file_data = update.message.photo[-1].get_file()
                caption = update.message.caption or ""
            elif update.message.video:
                content_type = 'video'
                file_data = update.message.video.get_file()
                caption = update.message.caption or ""
            elif update.message.document:
                content_type = 'document'
                file_data = update.message.document.get_file()
                caption = update.message.caption or ""
            elif update.message.text:
                content_type = 'text'
                text_content = update.message.text
                caption = ""
            else:
                await update.message.reply_text("❌ Неподдерживаемый тип контента.")
                return

            # Сохраняем контент
            if content_type == 'text':
                file_path = content_manager.save_text_content(text_content)
            else:
                file_path = await content_manager.save_file(content_type, file_data)

            # Публикуем пост
            post = {
                'channel_id': active_channel,
                'content_type': content_type,
                'file_path': file_path,
                'caption': caption
            }

            success = await scheduler.publish_post(post)

            if success:
                await update.message.reply_text("✅ Пост успешно опубликован!")
            else:
                await update.message.reply_text("❌ Ошибка при публикации поста.")

            # Очищаем флаг публикации
            context.user_data['publish_now'] = False

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            context.user_data['publish_now'] = False

    async def cancel_post_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /cancel_post - отмена запланированного поста"""
        user_id = update.effective_user.id
        args = context.args

        if not args:
            await update.message.reply_text(
                "❌ <b>Отмена поста</b>\n\n"
                "Использование: /cancel_post ID_поста\n\n"
                "Пример:\n"
                "<code>/cancel_post 123</code>\n\n"
                "Чтобы узнать ID поста, используйте /myschedule",
                parse_mode='HTML'
            )
            return

        try:
            post_id = int(args[0])

            # Отменяем пост в базе данных
            success = db.cancel_scheduled_post(post_id, user_id)

            if success:
                await update.message.reply_text(
                    f"✅ Пост с ID {post_id} отменен."
                )
            else:
                await update.message.reply_text(
                    f"❌ Не удалось отменить пост с ID {post_id}.\n"
                    f"Возможно, пост не существует или у вас нет прав для его отмены."
                )

        except ValueError:
            await update.message.reply_text("❌ Неверный формат ID поста. ID должен быть числом.")

    async def reschedule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /reschedule - перенос публикации"""
        user_id = update.effective_user.id
        args = context.args

        if not args or len(args) < 2:
            await update.message.reply_text(
                "🕐 <b>Перенос публикации</b>\n\n"
                "Использование: /reschedule ID_поста новое_время\n\n"
                "Пример:\n"
                "<code>/reschedule 123 2024-12-31 20:00</code>\n\n"
                "Чтобы узнать ID поста, используйте /myschedule",
                parse_mode='HTML'
            )
            return

        try:
            post_id = int(args[0])
            new_time = ' '.join(args[1:])

            # Парсим новое время
            scheduled_time = self.parse_time_input(new_time)

            if scheduled_time <= datetime.now():
                await update.message.reply_text("❌ Время публикации должно быть в будущем!")
                return

            # Обновляем время поста в базе данных
            success = db.reschedule_post(post_id, user_id, scheduled_time)

            if success:
                await update.message.reply_text(
                    f"✅ Время публикации поста {post_id} изменено на {scheduled_time.strftime('%d.%m.%Y в %H:%M')}."
                )
            else:
                await update.message.reply_text(
                    f"❌ Не удалось перенести пост с ID {post_id}.\n"
                    f"Возможно, пост не существует, у вас нет прав или он уже опубликован/отменен."
                )

        except ValueError as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    def run(self):
        """Запуск бота"""
        print("🤖 Бот запускается...")

        # Запуск планировщика в отдельном потоке
        import threading

        def run_scheduler():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scheduler.start_scheduler())

        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        # Запускаем бота
        print("✅ Бот успешно запущен!")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = TelegramAutopostBot()
    bot.run()