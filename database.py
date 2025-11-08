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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                content_type TEXT,
                file_path TEXT,
                caption TEXT,
                scheduled_time DATETIME,
                status TEXT DEFAULT 'scheduled',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_id INTEGER
            )
        ''')

        conn.commit()
        conn.close()

    def add_scheduled_post(self, user_id, content_type, file_path, caption, scheduled_time):
        """Добавление запланированного поста"""
        print(f"DEBUG: 💾 Сохраняем пост в БД")

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
                (user_id, content_type, file_path, caption, scheduled_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, content_type, file_path, caption, scheduled_time_str))

            post_id = cursor.lastrowid
            conn.commit()
            conn.close()

            print(f"DEBUG: ✅ Пост ID:{post_id} сохранен в БД")
            return post_id

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка сохранения: {e}")
            return None

    def get_user_schedule(self, user_id, days=7):
        """Получение расписания пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

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
                'content_type': row[2],
                'caption': row[4],
                'scheduled_time': row[5],
                'status': row[6],
                'message_id': row[8]
            })

        return schedule

    def get_post_stats(self, user_id):
        """Статистика постов пользователя"""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

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