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

    @loader.command(ru_doc="Создаёт файл любого типа. Пример: .file txt Привет мир! test")
    async def file(self, message: Message):
        """.file <расширение> <текст> [<имя_файла>] — создает файл и отправляет"""
        args = utils.get_args_raw(message)
        if not args or " " not in args:
            await utils.answer(message, self.strings("error"))
            return

        parts = args.split(" ", 2)
        ext = parts[0]  # расширение
        text = parts[1]  # содержимое
        filename = f"{parts[2]}.{ext}" if len(parts) == 3 else f"file.{ext}"

        # Создаем файл в памяти
        file_bytes = io.BytesIO(text.encode("utf-8"))
        file_bytes.name = filename

        # Отправляем файл
        await message.client.send_file(
            message.chat_id,
            file_bytes,
            caption=self.strings("success")
        )

        await message.delete()  # удаляем команду пользователя для чистоты чата
