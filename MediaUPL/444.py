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
