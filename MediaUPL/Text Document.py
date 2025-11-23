from telethon.tl.types import Message
from .. import loader, utils

@loader.tds
class HiMod(loader.Module):
    """Простой модуль, который реагирует на команду hi"""

    strings = {
        "name": "HiModule",
        "response": "Привет! 👋"
    }

    @loader.command(ru_doc="Отвечает на команду hi")
    async def hi(self, message: Message):
        """Команда .hi — бот отвечает"""
        await message.respond(self.strings("response"))
