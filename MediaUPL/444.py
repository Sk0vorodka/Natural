от telethon.tl.types импорт Сообщение
от .. импорт загрузчик, утилиты
импорт ио

@загрузчик.tds
класс UniversalFileMod(загрузчик.Модуль):
    """Модуль для создания файлов любого типа и отправки их в чат"""

 строки = {
        "имя": "УниверсальныйФайловыйМодуль",
        "использование": "Использование: .файл <расширение> <текст> [<имя_файла>]",
        "ошибка": "❌ Нужно указать расширение и текст!",
        "успех": "✅ Файл создан и отправлен!"
    }

    @загрузчик.команда(ru_doc="Создаёт файл любого типа. Пример: .file txt Привет мир! тест")
    асинхронный деф файл(я, сообщение: Сообщение):
        """.файл <расширение> <текст> [<имя_файла>] — создает файл и отправляет"""
 args = утилиты.get_args_raw(сообщение)
        если нет аргс или " " нет в аргументы:
            ждать утилиты.отвечать(сообщение, я.струны("ошибка"))
            возвращаться

 части = аргументы.расколоть(" ", 2)
 доб. = части[0]  # расширение
 текст = части[1]  # содержимое
 имя файла = ф"{части[2]}.{доб}" если лен(части) == 3 еще f"файл.{доб}"

        # Создаем файл в памяти
 file_bytes = io.BytesIO(текст.кодировать("утф-8"))
 байты_файла.имя = имя файла

        # Отправляем файл
        ждать сообщение.клиент.отправить_файл(
 сообщение.идентификатор_чата,
 байты_файла,
 подпись=self.струны("успех")
        )

        ждать сообщение.удалить()  # удаляем команду пользователя для чистоты чата

from telethon.tl.types import Message
from .. import loader, utils
import io

@loader.tds
class UniversalFileMod(loader.Module):
    """Модуль для создания файлов любого типа и отправки их в чат"""

    strings = {
        "name": "UniversalFileModule",
        "usage": "Использование: .file <расширение> <текст> [<имя_файла>]",
        "error": "❌ Нужно указать расширение и текст!",
        "success": "✅ Файл создан и отправлен!"
    }

    @loader.command(ru_doc="Создаёт файл любого типа. Пример: .file txt Привет мир! test file")
    async def file(self, message: Message):
        """.file <расширение> <текст> [<имя_файла>] — создает файл и отправляет"""
        args = utils.get_args_raw(message)
        if not args or " " not in args:
            await utils.answer(message, self.strings("error"))
            return

        # Разделяем на расширение и остальное
        parts = args.split(" ", 1)
        ext = parts[0]
        rest = parts[1]

        # Проверяем, указано ли имя файла в конце через пробел
        if " " in rest:
            *text_parts, filename_part = rest.split(" ")
            text = " ".join(text_parts)
            filename = f"{filename_part}.{ext}"
        else:
            text = rest
            filename = f"file.{ext}"

        # Создаем файл в памяти
        file_bytes = io.BytesIO(text.encode("utf-8"))
        file_bytes.name = filename

        # Отправляем файл
        await message.client.send_file(
            message.chat_id,
            file_bytes,
            caption=self.strings("success")
        )

        await message.delete()  # удаляем команду пользователя
