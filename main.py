import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, Chat
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackContext,
    PreCheckoutQueryHandler
)

from config import BOT_TOKEN, FREE_TIER_POSTS, TRIAL_PERIOD_DAYS
from database import Database
from payment import PaymentHandler
from scheduler import PostScheduler

# Состояния для ConversationHandler
SELECTING_CHANNEL, SELECTING_CONTENT_TYPE, WAITING_FOR_CONTENT, WAITING_FOR_SCHEDULE = range(4)
ADDING_CHANNEL = 10

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class AutoPostBot:
    def __init__(self):
        self.db = Database()
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.payment_handler = PaymentHandler(self.db)
        self.scheduler = None

        # Инициализируем обработчики
        self.setup_handlers()

    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Базовые команды
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("subscription", self.subscription_info))
        self.application.add_handler(CommandHandler("myposts", self.my_posts))
        self.application.add_handler(CommandHandler("mychannels", self.my_channels))
        self.application.add_handler(CommandHandler("test_publish", self.test_publish))

        # Обработчик для добавления каналов
        add_channel_conv = ConversationHandler(
            entry_points=[CommandHandler('addchannel', self.add_channel)],
            states={
                ADDING_CHANNEL: [MessageHandler(filters.TEXT | filters.FORWARDED, self.process_channel_add)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)]
        )
        self.application.add_handler(add_channel_conv)

        # Команды для оплаты
        self.application.add_handler(CommandHandler("buy", self.payment_handler.start_payment))
        self.application.add_handler(
            MessageHandler(filters.SUCCESSFUL_PAYMENT, self.payment_handler.successful_payment))
        self.application.add_handler(PreCheckoutQueryHandler(self.payment_handler.pre_checkout))

        # Обработчик для создания постов
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('createpost', self.create_post)],
            states={
                SELECTING_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.select_channel)],
                SELECTING_CONTENT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.select_content_type)],
                WAITING_FOR_CONTENT: [
                    MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
                                   self.receive_content)],
                WAITING_FOR_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.schedule_post)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)]
        )
        self.application.add_handler(conv_handler)

        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.echo))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        self.db.add_admin(user.id, user.username, user.full_name)

        welcome_text = (
            f"👋 Привет, {user.full_name}!\n\n"
            "Я бот для автопостинга в Telegram каналах.\n\n"
            "📋 Доступные команды:\n"
            "/addchannel - Добавить канал\n"
            "/createpost - Создать пост\n"
            "/myposts - Мои запланированные посты\n"
            "/mychannels - Мои каналы\n"
            "/subscription - Информация о подписке\n"
            "/buy - Купить премиум подписку\n"
            "/help - Помощь\n\n"
            f"🎁 Бесплатный тариф: {FREE_TIER_POSTS} постов\n"
            f"⭐ Премиум: неограниченно постов + тестовый период {TRIAL_PERIOD_DAYS} дней"
        )

        await update.message.reply_text(welcome_text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "📖 Помощь по боту:\n\n"
            "1. Добавьте бота как администратора в ваш канал\n"
            "2. Используйте /addchannel чтобы добавить канал\n"
            "3. Создавайте посты через /createpost\n"
            "4. Указывайте время публикации в формате: DD.MM.YYYY HH:MM\n\n"
            "📌 Поддерживаемые типы контента:\n"
            "• Текст\n• Фото\n• Видео\n• Документы\n\n"
            "💎 Оплата производится через Telegram Stars"
        )
        await update.message.reply_text(help_text)

    async def subscription_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о подписке"""
        user_id = update.effective_user.id
        subscription = self.db.get_subscription_info(user_id)

        if subscription:
            sub_type, posts_remaining, start_date, end_date, trial_used = subscription

            if sub_type == 'free':
                text = (
                    f"📊 Ваш текущий тариф: БЕСПЛАТНЫЙ\n"
                    f"📝 Осталось постов: {posts_remaining}\n\n"
                    f"⭐ Премиум подписка включает:\n"
                    f"• Неограниченное количество постов\n"
                    f"• Тестовый период {TRIAL_PERIOD_DAYS} дней\n"
                    f"• Приоритетная публикация\n\n"
                    f"Используйте /buy для покупки"
                )
            else:
                text = (
                    f"💎 Ваш текущий тариф: ПРЕМИУМ\n"
                    f"📅 Подписка активна до: {end_date}\n"
                    f"✅ Тестовый период: {'Использован' if trial_used else 'Активен'}\n\n"
                    f"Вы можете создавать неограниченное количество постов!"
                )
        else:
            text = "Информация о подписке не найдена"

        await update.message.reply_text(text)

    async def my_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ каналов пользователя"""
        user_id = update.effective_user.id
        channels = self.db.get_admin_channels(user_id)

        if not channels:
            await update.message.reply_text(
                "У вас нет добавленных каналов. Добавьте канал с помощью /addchannel"
            )
            return

        text = "📋 Ваши каналы:\n\n"
        for i, channel in enumerate(channels, 1):
            channel_id, channel_username, channel_title = channel
            text += f"{i}. {channel_title}\n"
            text += f"   👤 @{channel_username if channel_username else 'нет_username'}\n"
            text += f"   📎 ID: {channel_id}\n\n"

        await update.message.reply_text(text)

    async def add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса добавления канала"""
        user_id = update.effective_user.id

        await update.message.reply_text(
            "📝 Чтобы добавить канал, выполните следующие шаги:\n\n"
            "1. Добавьте бота как администратора в ваш канал\n"
            "2. Дайте боту права на отправку сообщений\n"
            "3. Перешлите любое сообщение из канала в этот чат\n\n"
            "Или просто отправьте @username вашего канала (например: @my_channel)\n\n"
            "Для отмены используйте /cancel"
        )

        return ADDING_CHANNEL

    async def process_channel_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка добавления канала"""
        user_id = update.effective_user.id
        message = update.message

        try:
            channel_id = None
            channel_username = None
            channel_title = None

            # Способ 1: Пересланное сообщение из канала
            if message.forward_from_chat:
                if message.forward_from_chat.type == Chat.CHANNEL:
                    channel_id = message.forward_from_chat.id
                    channel_username = message.forward_from_chat.username
                    channel_title = message.forward_from_chat.title
                else:
                    await update.message.reply_text(
                        "❌ Это не канал! Пожалуйста, перешлите сообщение именно из канала."
                    )
                    return ADDING_CHANNEL

            # Способ 2: Username канала
            elif message.text and message.text.startswith('@'):
                channel_username = message.text.strip('@')
                # Попробуем получить информацию о канале
                try:
                    chat = await self.application.bot.get_chat(f"@{channel_username}")
                    if chat.type == Chat.CHANNEL:
                        channel_id = chat.id
                        channel_title = chat.title
                    else:
                        await update.message.reply_text(
                            "❌ Это не канал! Пожалуйста, укажите username канала."
                        )
                        return ADDING_CHANNEL
                except Exception as e:
                    logger.error(f"Ошибка получения информации о канале: {e}")
                    await update.message.reply_text(
                        f"❌ Не удалось найти канал {message.text}. "
                        "Убедитесь, что:\n"
                        "• Канал существует\n"
                        "• Бот добавлен как администратор в канал\n"
                        "• Бот имеет права на отправку сообщений"
                    )
                    return ADDING_CHANNEL

            else:
                await update.message.reply_text(
                    "❌ Пожалуйста, перешлите сообщение из канала или отправьте @username канала.\n"
                    "Для отмены используйте /cancel"
                )
                return ADDING_CHANNEL

            # Проверяем, добавлен ли канал уже
            existing_channels = self.db.get_admin_channels(user_id)
            for channel in existing_channels:
                if channel[0] == channel_id:
                    await update.message.reply_text(
                        f"❌ Канал '{channel_title}' уже добавлен!"
                    )
                    return ConversationHandler.END

            # Проверяем, является ли бот администратором канала
            try:
                chat_member = await self.application.bot.get_chat_member(channel_id, self.application.bot.id)
                if not chat_member.status in ['administrator', 'creator']:
                    await update.message.reply_text(
                        f"❌ Бот не является администратором в канале '{channel_title}'!\n"
                        "Пожалуйста, добавьте бота как администратора и дайте права на отправку сообщений."
                    )
                    return ADDING_CHANNEL

                if not chat_member.can_post_messages:
                    await update.message.reply_text(
                        f"❌ У бота нет прав на отправку сообщений в канале '{channel_title}'!\n"
                        "Пожалуйста, дайте боту права на отправку сообщений."
                    )
                    return ADDING_CHANNEL

            except Exception as e:
                logger.error(f"Ошибка проверки прав бота: {e}")
                await update.message.reply_text(
                    f"❌ Не удалось проверить права бота в канале '{channel_title}'.\n"
                    "Убедитесь, что бот добавлен как администратор."
                )
                return ADDING_CHANNEL

            # Добавляем канал в базу данных
            self.db.add_channel(channel_id, channel_username, channel_title, user_id)

            await update.message.reply_text(
                f"✅ Канал '{channel_title}' успешно добавлен!\n\n"
                f"📎 ID: {channel_id}\n"
                f"👤 Username: @{channel_username if channel_username else 'нет'}\n\n"
                "Теперь вы можете создавать посты для этого канала с помощью /createpost"
            )

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Ошибка при добавлении канала: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при добавлении канала. Попробуйте еще раз."
            )
            return ADDING_CHANNEL

    async def create_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало создания поста"""
        user_id = update.effective_user.id
        channels = self.db.get_admin_channels(user_id)

        if not channels:
            await update.message.reply_text(
                "У вас нет добавленных каналов. Сначала добавьте канал через /addchannel"
            )
            return ConversationHandler.END

        # Создаем клавиатуру с каналами
        keyboard = [[f"{channel[2]} (@{channel[1]})" if channel[1] else channel[2]] for channel in channels]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(
            "Выберите канал для публикации:",
            reply_markup=reply_markup
        )

        return SELECTING_CHANNEL

    async def select_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор канала для поста"""
        selected_channel_info = update.message.text
        user_id = update.effective_user.id

        # Извлекаем название канала из строки (может содержать username в скобках)
        channel_title = selected_channel_info.split(' (')[0] if ' (' in selected_channel_info else selected_channel_info

        # Сохраняем выбранный канал в контексте
        context.user_data['selected_channel'] = channel_title

        # Клавиатура для выбора типа контента
        keyboard = [['Текст', 'Фото'], ['Видео', 'Документ']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

        await update.message.reply_text(
            "Выберите тип контента:",
            reply_markup=reply_markup
        )

        return SELECTING_CONTENT_TYPE

    async def select_content_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор типа контента"""
        content_type_map = {
            'Текст': 'text',
            'Фото': 'photo',
            'Видео': 'video',
            'Документ': 'document'
        }

        selected_type = content_type_map.get(update.message.text)
        if not selected_type:
            await update.message.reply_text("Пожалуйста, выберите тип контента из предложенных вариантов")
            return SELECTING_CONTENT_TYPE

        context.user_data['content_type'] = selected_type

        if selected_type == 'text':
            await update.message.reply_text(
                "Введите текст поста:",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                f"Отправьте {update.message.text.lower()} для поста:",
                reply_markup=ReplyKeyboardRemove()
            )

        return WAITING_FOR_CONTENT

    async def receive_content(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение контента для поста"""
        content_type = context.user_data['content_type']
        file_id = None
        text_content = ""

        if content_type == 'text':
            text_content = update.message.text
        elif content_type == 'photo' and update.message.photo:
            file_id = update.message.photo[-1].file_id
            text_content = update.message.caption or ""
        elif content_type == 'video' and update.message.video:
            file_id = update.message.video.file_id
            text_content = update.message.caption or ""
        elif content_type == 'document' and update.message.document:
            file_id = update.message.document.file_id
            text_content = update.message.caption or ""
        else:
            await update.message.reply_text("Пожалуйста, отправьте корректный тип контента")
            return WAITING_FOR_CONTENT

        # Сохраняем контент в контексте
        context.user_data['file_id'] = file_id
        context.user_data['text_content'] = text_content

        await update.message.reply_text(
            "Введите дату и время публикации в формате:\n"
            "DD.MM.YYYY HH:MM\n\n"
            "Например: 25.12.2024 15:30"
        )

        return WAITING_FOR_SCHEDULE

    async def schedule_post(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Планирование времени публикации"""
        try:
            # Парсим дату и время
            scheduled_str = update.message.text
            scheduled_time = datetime.strptime(scheduled_str, '%d.%m.%Y %H:%M')

            if scheduled_time <= datetime.now():
                await update.message.reply_text("Время публикации должно быть в будущем. Попробуйте снова:")
                return WAITING_FOR_SCHEDULE

            # Получаем данные из контекста
            channel_title = context.user_data['selected_channel']
            content_type = context.user_data['content_type']
            text_content = context.user_data.get('text_content', '')
            file_id = context.user_data.get('file_id')

            user_id = update.effective_user.id

            # Получаем ID канала
            channels = self.db.get_admin_channels(user_id)
            channel_id = None
            for channel in channels:
                if channel[2] == channel_title:
                    channel_id = channel[0]
                    break

            if not channel_id:
                await update.message.reply_text("Ошибка: канал не найден")
                return ConversationHandler.END

            # Создаем пост в базе данных
            success, result = self.db.create_post(
                user_id, channel_id, content_type,
                text_content, file_id, scheduled_time
            )

            if success:
                # Также планируем пост в APScheduler
                self.scheduler.schedule_single_post(result, scheduled_time)

                await update.message.reply_text(
                    f"✅ Пост успешно запланирован на {scheduled_str}!\n"
                    f"Пост будет опубликован в канале {channel_title}\n\n"
                    f"ID поста: {result}"
                )
            else:
                await update.message.reply_text(f"❌ Ошибка: {result}")

        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты. Используйте: DD.MM.YYYY HH:MM\n"
                "Попробуйте снова:"
            )
            return WAITING_FOR_SCHEDULE
        except Exception as e:
            logger.error(f"Ошибка при планировании поста: {e}")
            await update.message.reply_text("Произошла ошибка при планировании поста")

        return ConversationHandler.END

    async def my_posts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ запланированных постов пользователя"""
        user_id = update.effective_user.id
        posts = self.db.get_scheduled_posts(user_id)

        if not posts:
            await update.message.reply_text("У вас нет запланированных постов")
            return

        text = "📅 Ваши запланированные посты:\n\n"
        for post in posts:
            post_id, channel_title, content_type, scheduled_time, published = post
            status = "✅ Опубликован" if published else "⏰ Ожидает публикации"
            text += f"📝 {channel_title}\n"
            text += f"Тип: {content_type}\n"
            text += f"Время: {scheduled_time}\n"
            text += f"Статус: {status}\n\n"

        await update.message.reply_text(text)

    async def test_publish(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Тестовая команда для проверки публикации"""
        try:
            await self.scheduler.publish_scheduled_posts()
            await update.message.reply_text("✅ Тестовая проверка публикации выполнена. Проверьте логи.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при тестовой публикации: {str(e)}")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущей операции"""
        await update.message.reply_text(
            "Операция отменена",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        await update.message.reply_text(
            "Используйте /help для просмотра доступных команд"
        )

    def run(self):
        """Запуск бота"""
        # Инициализируем планировщик
        self.scheduler = PostScheduler(self.db, self.application.bot)

        # Запускаем периодическую проверку постов
        self.scheduler.start_periodic_check()

        # Запускаем бота
        logger.info("Бот запущен")
        self.application.run_polling()


if __name__ == '__main__':
    bot = AutoPostBot()
    bot.run()