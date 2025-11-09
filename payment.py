import logging
from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes, CallbackContext
from config import SUBSCRIPTION_PRICE_STARS, TRIAL_PERIOD_DAYS

logger = logging.getLogger(__name__)


class PaymentHandler:
    def __init__(self, database):
        self.db = database

    async def start_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса оплаты"""
        user = update.effective_user

        # Проверяем, не активирована ли уже премиум подписка
        subscription_info = self.db.get_subscription_info(user.id)
        if subscription_info and subscription_info[0] == 'premium':
            await update.message.reply_text(
                "✅ У вас уже активирована премиум подписка!\n"
                f"Она действует до: {subscription_info[3]}"
            )
            return

        # Создаем инвойс для оплаты звездами
        chat_id = update.effective_chat.id
        title = "Премиум подписка на автопостинг"
        description = f"Доступ к неограниченному количеству постов и дополнительным функциям. Тестовый период {TRIAL_PERIOD_DAYS} дней."
        payload = f"subscription_{user.id}"

        # В Telegram Stars цены указываются в центах (1 звезда = 100 центов)
        prices = [LabeledPrice("Премиум подписка", SUBSCRIPTION_PRICE_STARS * 100)]

        try:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # Для тестового режима можно оставить пустым
                currency="XTR",  # Валюта для Telegram Stars
                prices=prices,
                start_parameter="premium-subscription",
                need_email=False,
                need_phone_number=False,
                need_shipping_address=False,
                is_flexible=False
            )
        except Exception as e:
            logger.error(f"Ошибка при создании инвойса: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при создании платежа. "
                "Пожалуйста, попробуйте позже или обратитесь к администратору."
            )

    async def pre_checkout(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка предварительной проверки оплаты"""
        query = update.pre_checkout_query

        # Проверяем валидность платежа
        if query.invoice_payload.startswith('subscription_'):
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message="Что-то пошло не так...")

    async def successful_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка успешного платежа"""
        try:
            payment = update.message.successful_payment
            user_id = update.effective_user.id

            # Активируем премиум подписку
            self.db.activate_premium_subscription(user_id, payment.total_amount // 100)

            await update.message.reply_text(
                "🎉 Оплата прошла успешно! Премиум подписка активирована.\n\n"
                f"✅ Тестовый период {TRIAL_PERIOD_DAYS} дней начался\n"
                "✅ Неограниченное количество постов\n"
                "✅ Приоритетная публикация\n\n"
                "Теперь вы можете создавать неограниченное количество постов!"
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке успешного платежа: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при активации подписки. "
                "Пожалуйста, обратитесь к администратору."
            )
