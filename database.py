import sqlite3
import logging
from datetime import datetime, timedelta
from config import DATABASE_NAME, FREE_TIER_POSTS, TRIAL_PERIOD_DAYS

logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        cursor = self.conn.cursor()

        # Таблица администраторов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица каналов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                channel_username TEXT,
                channel_title TEXT,
                admin_id INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES admins (user_id)
            )
        ''')

        # Таблица подписок
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                subscription_type TEXT DEFAULT 'free',
                posts_remaining INTEGER DEFAULT {FREE_TIER_POSTS},
                subscription_start TIMESTAMP,
                subscription_end TIMESTAMP,
                trial_used BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES admins (user_id)
            )
        ''')

        # Таблица постов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                channel_id INTEGER,
                content_type TEXT,
                text_content TEXT,
                file_id TEXT,
                scheduled_time TIMESTAMP,
                published BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES admins (user_id),
                FOREIGN KEY (channel_id) REFERENCES channels (channel_id)
            )
        ''')

        # Таблица платежей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                stars_amount INTEGER,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                successful BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES admins (user_id)
            )
        ''')

        self.conn.commit()

    def add_admin(self, user_id, username, full_name):
        """Добавление администратора"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO admins (user_id, username, full_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, full_name))

        # Создаем запись о подписке
        cursor.execute('''
            INSERT OR IGNORE INTO subscriptions (user_id, posts_remaining)
            VALUES (?, ?)
        ''', (user_id, FREE_TIER_POSTS))

        self.conn.commit()

    def add_channel(self, channel_id, channel_username, channel_title, admin_id):
        """Добавление канала"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO channels (channel_id, channel_username, channel_title, admin_id)
            VALUES (?, ?, ?, ?)
        ''', (channel_id, channel_username, channel_title, admin_id))
        self.conn.commit()

    def get_admin_channels(self, admin_id):
        """Получение каналов администратора"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT channel_id, channel_username, channel_title 
            FROM channels 
            WHERE admin_id = ?
        ''', (admin_id,))
        return cursor.fetchall()

    def create_post(self, admin_id, channel_id, content_type, text_content, file_id, scheduled_time):
        """Создание поста"""
        cursor = self.conn.cursor()

        # Проверяем лимит постов
        cursor.execute('''
            SELECT posts_remaining FROM subscriptions WHERE user_id = ?
        ''', (admin_id,))
        result = cursor.fetchone()

        if not result or result[0] <= 0:
            return False, "Недостаточно постов в вашем тарифе"

        # Преобразуем scheduled_time в строку для SQLite
        if isinstance(scheduled_time, datetime):
            scheduled_time_str = scheduled_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            scheduled_time_str = scheduled_time

        cursor.execute('''
            INSERT INTO posts (admin_id, channel_id, content_type, text_content, file_id, scheduled_time)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (admin_id, channel_id, content_type, text_content, file_id, scheduled_time_str))

        # Уменьшаем количество доступных постов
        cursor.execute('''
            UPDATE subscriptions 
            SET posts_remaining = posts_remaining - 1 
            WHERE user_id = ?
        ''', (admin_id,))

        post_id = cursor.lastrowid
        self.conn.commit()

        logger.info(f"📝 Создан пост {post_id} для канала {channel_id} на {scheduled_time_str}")
        return True, post_id

    def get_pending_posts(self):
        """Получение постов, готовых к публикации - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT p.post_id, p.channel_id, p.content_type, p.text_content, p.file_id
            FROM posts p
            WHERE p.published = FALSE AND datetime(p.scheduled_time) <= datetime('now', 'localtime')
        ''')
        posts = cursor.fetchall()
        logger.info(f"🔍 Найдено {len(posts)} постов для публикации")
        return posts

    def mark_post_published(self, post_id):
        """Отметка поста как опубликованного"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE posts SET published = TRUE WHERE post_id = ?
        ''', (post_id,))
        self.conn.commit()
        logger.info(f"✅ Пост {post_id} отмечен как опубликованный")

    def get_subscription_info(self, user_id):
        """Получение информации о подписке"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT s.subscription_type, s.posts_remaining, s.subscription_start, 
                   s.subscription_end, s.trial_used
            FROM subscriptions s
            WHERE s.user_id = ?
        ''', (user_id,))
        return cursor.fetchone()

    def activate_premium_subscription(self, user_id, stars_amount):
        """Активация премиум подписки"""
        cursor = self.conn.cursor()

        # Добавляем trial период
        subscription_start = datetime.now()
        subscription_end = subscription_start + timedelta(days=TRIAL_PERIOD_DAYS)

        cursor.execute('''
            UPDATE subscriptions 
            SET subscription_type = 'premium',
                subscription_start = ?,
                subscription_end = ?,
                posts_remaining = posts_remaining + 100,
                trial_used = TRUE
            WHERE user_id = ?
        ''', (subscription_start, subscription_end, user_id))

        # Записываем платеж
        cursor.execute('''
            INSERT INTO payments (user_id, stars_amount, successful)
            VALUES (?, ?, ?)
        ''', (user_id, stars_amount, True))

        self.conn.commit()

    def get_scheduled_posts(self, admin_id):
        """Получение запланированных постов администратора"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT p.post_id, c.channel_title, p.content_type, p.scheduled_time, p.published
            FROM posts p
            JOIN channels c ON p.channel_id = c.channel_id
            WHERE p.admin_id = ?
            ORDER BY p.scheduled_time DESC
            LIMIT 10
        ''', (admin_id,))
        return cursor.fetchall()

    def remove_channel(self, channel_id, admin_id):
        """Удаление канала"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM channels 
            WHERE channel_id = ? AND admin_id = ?
        ''', (channel_id, admin_id))
        self.conn.commit()
        return cursor.rowcount > 0