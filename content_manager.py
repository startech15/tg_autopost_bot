import os
import uuid
from datetime import time

import requests
import aiohttp
import asyncio
from config import UPLOAD_DIRS, BOT_TOKEN


class ContentManager:
    def __init__(self):
        self.upload_dirs = UPLOAD_DIRS

    async def save_file(self, file_type, file_data, filename=None):
        """Сохранение загруженного файла с улучшенной обработкой ошибок"""
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

            # Получаем файл как объект
            file_obj = file_data

            # СПОСОБ 1: Пытаемся использовать download_to_drive
            try:
                await file_obj.download_to_drive(custom_path=file_path)
                print(f"DEBUG: ✅ Файл успешно сохранен (способ 1): {file_path}")

                # Проверяем размер файла
                file_size = os.path.getsize(file_path)
                print(f"DEBUG: 📏 Размер файла: {file_size} байт")

                return file_path
            except Exception as e1:
                print(f"DEBUG: ⚠️ Способ 1 не сработал: {e1}")

                # СПОСОБ 2: Используем download_as_bytearray
                try:
                    file_bytes = await file_obj.download_as_bytearray()
                    with open(file_path, 'wb') as f:
                        f.write(file_bytes)
                    print(f"DEBUG: ✅ Файл успешно сохранен (способ 2): {file_path}")

                    # Проверяем размер файла
                    file_size = os.path.getsize(file_path)
                    print(f"DEBUG: 📏 Размер файла: {file_size} байт")

                    return file_path
                except Exception as e2:
                    print(f"DEBUG: ⚠️ Способ 2 не сработал: {e2}")

                    # СПОСОБ 3: Используем file_path из Telegram через aiohttp
                    try:
                        if hasattr(file_obj, 'file_path'):
                            file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_obj.file_path}"

                            async with aiohttp.ClientSession() as session:
                                async with session.get(file_url) as response:
                                    if response.status == 200:
                                        file_content = await response.read()
                                        with open(file_path, 'wb') as f:
                                            f.write(file_content)
                                        print(f"DEBUG: ✅ Файл успешно сохранен (способ 3): {file_path}")

                                        # Проверяем размер файла
                                        file_size = os.path.getsize(file_path)
                                        print(f"DEBUG: 📏 Размер файла: {file_size} байт")

                                        return file_path
                                    else:
                                        raise Exception(f"HTTP {response.status}")
                        else:
                            raise Exception("File path not available")
                    except Exception as e3:
                        print(f"DEBUG: ❌ Все способы не сработали: {e3}")
                        raise Exception(f"Не удалось сохранить файл: {e3}")

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка сохранения файла: {e}")
            # Пытаемся удалить частично сохраненный файл
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            raise

    def save_text_content(self, text):
        """Сохранение текстового контента в файл с улучшенной обработкой"""
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

            # Проверяем читаемость файла
            with open(file_path, 'r', encoding='utf-8') as f:
                content_check = f.read()
                if content_check != text:
                    print(f"DEBUG: ⚠️ Предупреждение: сохраненный текст не соответствует исходному")

            return file_path

        except Exception as e:
            print(f"DEBUG: ❌ Ошибка сохранения текста: {e}")
            # Пытаемся удалить частично сохраненный файл
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            raise

    def get_file_path(self, file_path):
        """Получение полного пути к файлу с проверкой существования"""
        # Если путь относительный, делаем его абсолютным
        if not os.path.isabs(file_path):
            full_path = os.path.abspath(file_path)
        else:
            full_path = file_path

        print(f"DEBUG: 📍 Полный путь к файлу: {full_path}")

        # Проверяем существование файла
        file_exists = os.path.exists(full_path)
        print(f"DEBUG: 🔍 Файл существует: {file_exists}")

        if file_exists:
            file_size = os.path.getsize(full_path)
            print(f"DEBUG: 📏 Размер файла: {file_size} байт")
        else:
            print(f"DEBUG: ⚠️ Файл не найден: {full_path}")

        return full_path

    def cleanup_file(self, file_path):
        """Удаление файла с улучшенной обработкой ошибок"""
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
        """Проверка существования файла с дополнительной информацией"""
        exists = os.path.exists(file_path)
        print(f"DEBUG: 🔍 Файл {file_path} существует: {exists}")

        if exists:
            file_size = os.path.getsize(file_path)
            print(f"DEBUG: 📏 Размер файла: {file_size} байт")

        return exists

    def get_file_info(self, file_path):
        """Получение информации о файле"""
        full_path = self.get_file_path(file_path)

        if not os.path.exists(full_path):
            return None

        try:
            file_stats = os.stat(full_path)
            return {
                'path': full_path,
                'size': file_stats.st_size,
                'created': file_stats.st_ctime,
                'modified': file_stats.st_mtime,
                'exists': True
            }
        except Exception as e:
            print(f"DEBUG: ❌ Ошибка получения информации о файле: {e}")
            return None

    def cleanup_old_files(self, max_age_hours=24):
        """Очистка старых файлов для экономии места"""
        print(f"DEBUG: 🧹 Очистка файлов старше {max_age_hours} часов")

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        cleaned_count = 0

        # Проверяем все директории для загрузки
        for dir_type, dir_path in self.upload_dirs.items():
            if os.path.exists(dir_path):
                for filename in os.listdir(dir_path):
                    file_path = os.path.join(dir_path, filename)
                    try:
                        file_age = current_time - os.path.getctime(file_path)
                        if file_age > max_age_seconds:
                            os.remove(file_path)
                            cleaned_count += 1
                            print(f"DEBUG: 🗑️ Удален старый файл: {file_path}")
                    except Exception as e:
                        print(f"DEBUG: ❌ Ошибка удаления файла {file_path}: {e}")

        # Также проверяем основную директорию uploaded_content
        main_dir = 'uploaded_content'
        if os.path.exists(main_dir):
            for filename in os.listdir(main_dir):
                file_path = os.path.join(main_dir, filename)
                try:
                    file_age = current_time - os.path.getctime(file_path)
                    if file_age > max_age_seconds:
                        os.remove(file_path)
                        cleaned_count += 1
                        print(f"DEBUG: 🗑️ Удален старый файл: {file_path}")
                except Exception as e:
                    print(f"DEBUG: ❌ Ошибка удаления файла {file_path}: {e}")

        print(f"DEBUG: ✅ Очистка завершена. Удалено файлов: {cleaned_count}")
        return cleaned_count