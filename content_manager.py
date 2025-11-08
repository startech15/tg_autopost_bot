import os
import uuid
import requests
from config import UPLOAD_DIRS, BOT_TOKEN


class ContentManager:
    def __init__(self):
        self.upload_dirs = UPLOAD_DIRS

    async def save_file(self, file_type, file_data, filename=None):
        """Сохранение загруженного файла"""
        print(f"DEBUG: 💾 Сохраняем файл типа {file_type}")

        if file_type not in self.upload_dirs:
            raise ValueError(f"Unsupported file type: {file_type}")

        # Генерируем уникальное имя файла
        if not filename:
            file_ext = os.path.splitext(getattr(file_data, 'file_name', 'file'))[1]
            filename = f"{uuid.uuid4()}{file_ext or '.bin'}"

        file_path = os.path.join(self.upload_dirs[file_type], filename)

        print(f"DEBUG: 📁 Сохраняем в: {file_path}")

        try:
            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # СПОСОБ 1: Пытаемся использовать download_to_drive
            try:
                await file_data.download_to_drive(custom_path=file_path)
                print(f"DEBUG: ✅ Файл успешно сохранен (способ 1): {file_path}")
                return file_path
            except Exception as e1:
                print(f"DEBUG: ⚠️ Способ 1 не сработал: {e1}")

                # СПОСОБ 2: Используем download_as_bytearray
                try:
                    file_bytes = await file_data.download_as_bytearray()
                    with open(file_path, 'wb') as f:
                        f.write(file_bytes)
                    print(f"DEBUG: ✅ Файл успешно сохранен (способ 2): {file_path}")
                    return file_path
                except Exception as e2:
                    print(f"DEBUG: ⚠️ Способ 2 не сработал: {e2}")

                    # СПОСОБ 3: Используем file_path из Telegram
                    try:
                        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_data.file_path}"
                        response = requests.get(file_url)
                        with open(file_path, 'wb') as f:
                            f.write(response.content)
                        print(f"DEBUG: ✅ Файл успешно сохранен (способ 3): {file_path}")
                        return file_path
                    except Exception as e3:
                        print(f"DEBUG: ❌ Все способы не сработали: {e3}")
                        raise Exception(f"Не удалось сохранить файл: {e3}")

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка сохранения файла: {e}")
            raise

    def save_text_content(self, text):
        """Сохранение текстового контента в файл"""
        print(f"DEBUG: 💾 Сохраняем текстовый контент")

        filename = f"text_{uuid.uuid4()}.txt"
        file_path = os.path.join('uploaded_content', filename)

        print(f"DEBUG: 📝 Сохраняем текст в: {file_path}")
        print(f"DEBUG: 📄 Длина текста: {len(text)} символов")

        try:
            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(text)

            # Проверяем что файл создан
            file_size = os.path.getsize(file_path)
            print(f"DEBUG: ✅ Текст успешно сохранен: {file_path} ({file_size} байт)")
            return file_path

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка сохранения текста: {e}")
            raise

    def get_file_path(self, file_path):
        """Получение полного пути к файлу"""
        # Если путь относительный, делаем его абсолютным
        if not os.path.isabs(file_path):
            full_path = os.path.abspath(file_path)
        else:
            full_path = file_path

        print(f"DEBUG: 📍 Полный путь к файлу: {full_path}")
        print(f"DEBUG: 🔍 Файл существует: {os.path.exists(full_path)}")

        return full_path

    def cleanup_file(self, file_path):
        """Удаление файла"""
        full_path = self.get_file_path(file_path)
        print(f"DEBUG: 🗑️ Удаляем файл: {full_path}")

        try:
            if os.path.exists(full_path):
                os.remove(full_path)
                print(f"DEBUG: ✅ Файл удален: {full_path}")
                return True
            else:
                print(f"DEBUG: ⚠️ Файл не существует: {full_path}")
                return False
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка удаления файла {full_path}: {e}")
            return False

    def file_exists(self, file_path):
        """Проверка существования файла"""
        exists = os.path.exists(file_path)
        print(f"DEBUG: 🔍 Файл {file_path} существует: {exists}")
        return exists

    def list_uploaded_files(self):
        """Список всех загруженных файлов (для отладки)"""
        print("DEBUG: 📂 Список загруженных файлов:")

        for content_type, dir_path in self.upload_dirs.items():
            if os.path.exists(dir_path):
                files = os.listdir(dir_path)
                print(f"DEBUG: 📁 {content_type}: {len(files)} файлов")
                for file in files[:5]:  # Показываем первые 5 файлов
                    file_path = os.path.join(dir_path, file)
                    file_size = os.path.getsize(file_path)
                    print(f"DEBUG:    📄 {file} ({file_size} байт)")
            else:
                print(f"DEBUG: 📁 {content_type}: директория не существует")

        # Проверяем текстовые файлы
        text_dir = 'uploaded_content'
        if os.path.exists(text_dir):
            text_files = [f for f in os.listdir(text_dir) if f.endswith('.txt')]
            print(f"DEBUG: 📁 text: {len(text_files)} файлов")
            for file in text_files[:5]:
                file_path = os.path.join(text_dir, file)
                file_size = os.path.getsize(file_path)
                print(f"DEBUG:    📄 {file} ({file_size} байт)")