import sqlite3
from datetime import datetime
from config import DB_FILE


class ContentDatabase:
    def __init__(self):
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Таблица для запланированных постов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                content_type TEXT,
                file_path TEXT,
                caption TEXT,
                scheduled_time DATETIME,
                status TEXT DEFAULT 'scheduled',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_id INTEGER
            )
        ''')

        # Таблица для каналов пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT UNIQUE,
                channel_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица для текущего активного канала пользователя
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                active_channel_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def add_scheduled_post(self, user_id, channel_id, content_type, file_path, caption, scheduled_time):
        """Добавление запланированного поста"""
        print(f"DEBUG: 💾 Сохраняем пост в БД для канала {channel_id}")

        # Преобразуем время в правильный формат для SQLite
        if isinstance(scheduled_time, datetime):
            scheduled_time_str = scheduled_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            scheduled_time_str = str(scheduled_time)

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO scheduled_posts 
                (user_id, channel_id, content_type, file_path, caption, scheduled_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, channel_id, content_type, file_path, caption, scheduled_time_str))

            post_id = cursor.lastrowid
            conn.commit()
            conn.close()

            print(f"DEBUG: ✅ Пост ID:{post_id} сохранен в БД для канала {channel_id}")
            return post_id

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка сохранения: {e}")
            return None

    def get_user_schedule(self, user_id, channel_id=None, days=7):
        """Получение расписания пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        if channel_id:
            # Получаем расписание для конкретного канала
            cursor.execute('''
                SELECT * FROM scheduled_posts 
                WHERE user_id = ? AND channel_id = ?
                AND scheduled_time >= datetime('now')
                AND scheduled_time <= datetime('now', ?)
                ORDER BY scheduled_time ASC
            ''', (user_id, channel_id, f'+{days} days'))
        else:
            # Получаем расписание для всех каналов пользователя
            cursor.execute('''
                SELECT * FROM scheduled_posts 
                WHERE user_id = ? 
                AND scheduled_time >= datetime('now')
                AND scheduled_time <= datetime('now', ?)
                ORDER BY scheduled_time ASC
            ''', (user_id, f'+{days} days'))

        results = cursor.fetchall()
        conn.close()

        schedule = []
        for row in results:
            schedule.append({
                'id': row[0],
                'channel_id': row[2],
                'content_type': row[3],
                'file_path': row[4],
                'caption': row[5],
                'scheduled_time': row[6],
                'status': row[7],
                'message_id': row[9]
            })

        return schedule

    def get_post_stats(self, user_id, channel_id=None):
        """Статистика постов пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        if channel_id:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) as scheduled,
                    SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                FROM scheduled_posts 
                WHERE user_id = ? AND channel_id = ?
            ''', (user_id, channel_id))
        else:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) as scheduled,
                    SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                FROM scheduled_posts 
                WHERE user_id = ?
            ''', (user_id,))

        result = cursor.fetchone()
        conn.close()

        return {
            'total': result[0],
            'scheduled': result[1],
            'published': result[2],
            'cancelled': result[3]
        }

    # Методы для работы с каналами
    def add_user_channel(self, user_id, channel_id, channel_name):
        """Добавление канала пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO user_channels 
                (user_id, channel_id, channel_name)
                VALUES (?, ?, ?)
            ''', (user_id, channel_id, channel_name))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка добавления канала: {e}")
            conn.close()
            return False

    def get_user_channels(self, user_id):
        """Получение всех каналов пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT channel_id, channel_name FROM user_channels 
            WHERE user_id = ? AND is_active = 1
            ORDER BY created_at DESC
        ''', (user_id,))

        results = cursor.fetchall()
        conn.close()

        channels = []
        for row in results:
            channels.append({
                'channel_id': row[0],
                'channel_name': row[1]
            })

        return channels

    def set_active_channel(self, user_id, channel_id):
        """Установка активного канала для пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO user_settings 
                (user_id, active_channel_id)
                VALUES (?, ?)
            ''', (user_id, channel_id))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка установки активного канала: {e}")
            conn.close()
            return False

    def get_active_channel(self, user_id):
        """Получение активного канала пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT active_channel_id FROM user_settings 
            WHERE user_id = ?
        ''', (user_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return result[0]
        return None

    def remove_user_channel(self, user_id, channel_id):
        """Удаление канала пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        try:
            # Деактивируем канал
            cursor.execute('''
                UPDATE user_channels 
                SET is_active = 0 
                WHERE user_id = ? AND channel_id = ?
            ''', (user_id, channel_id))

            # Если это был активный канал, сбрасываем настройки
            active_channel = self.get_active_channel(user_id)
            if active_channel == channel_id:
                cursor.execute('''
                    DELETE FROM user_settings 
                    WHERE user_id = ?
                ''', (user_id,))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка удаления канала: {e}")
            conn.close()
            return False

    def cancel_scheduled_post(self, post_id, user_id):
        """Отмена запланированного поста"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE scheduled_posts 
                SET status = 'cancelled'
                WHERE id = ? AND user_id = ? AND status = 'scheduled'
            ''', (post_id, user_id))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка отмены поста {post_id}: {e}")
            conn.close()
            return False

    def reschedule_post(self, post_id, user_id, new_time):
        """Перенос запланированного поста"""
        # Преобразуем время в правильный формат для SQLite
        if isinstance(new_time, datetime):
            new_time_str = new_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            new_time_str = str(new_time)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE scheduled_posts 
                SET scheduled_time = ?
                WHERE id = ? AND user_id = ? AND status = 'scheduled'
            ''', (new_time_str, post_id, user_id))

            conn.commit()
            success = cursor.rowcount > 0
            conn.close()
            return success
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка переноса поста {post_id}: {e}")
            conn.close()
            return False

    def get_post_by_id(self, post_id, user_id):
        """Получение поста по ID"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM scheduled_posts 
            WHERE id = ? AND user_id = ?
        ''', (post_id, user_id))

        result = cursor.fetchone()
        conn.close()

        if result:
            return {
                'id': result[0],
                'user_id': result[1],
                'channel_id': result[2],
                'content_type': result[3],
                'file_path': result[4],
                'caption': result[5],
                'scheduled_time': result[6],
                'status': result[7],
                'message_id': result[9]
            }
        return None