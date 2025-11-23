# meta developer: @RnPlugins
# meta name: MediaUPL
# meta version: 1.0.0
# meta banner: https://yufic.ru/api/hc/?a=MediaUPL&b=by%20@RnPlugins
# requires: aiohttp

import io
import json
import os
import aiohttp
from telethon.tl.types import Message
from .. import loader, utils


@loader.tds
class MediaUPLMod(loader.Module):
    """Загружает медиа на гитхаб через MediaUPL (upl.yufic.ru) и выдает прямую ссылку."""

    strings = {
        "name": "MediaUPL",
        "no_media": "<emoji document_id=5260342697075416641>❌</emoji> <b>Ответьте на медиафайл или прикрепите его к команде.</b>",
        "no_api_key": (
            "<emoji document_id=5258260149037965799>💼</emoji> <b>API ключ не настроен.</b>\n"
            "Настройте его командой: <code>.cfg MediaUPL</code>"
        ),
        "uploading": "<emoji document_id=5427181942934088912>💬</emoji> <b>Загрузка на <a href='https://upl.yufic.ru'>MediaUPL</a>...</b>",
        "success": (
            "<emoji document_id=5260726538302660868>✅</emoji> <b>Файл успешно загружен!</b>\n\n"
            "<emoji document_id=5260730055880876557>⛓</emoji> <b><a href='{}'>Ссылка</a>:</b> <code>{}</code>"
        ),
        "error": (
            "<emoji document_id=5260342697075416641>❌</emoji> <b>Произошла ошибка при загрузке.</b>\n\n"
            "<pre>{}</pre>"
        ),
        "error_401": (
            "<emoji document_id=5260342697075416641>❌</emoji> <b>Ошибка авторизации (401).</b>\n\n"
            "Пожалуйста, проверьте правильность вашего API ключа в "
            "<code>.cfg MediaUPL</code>."
        ),
        "config_api_key_doc": "Ваш API ключ от хостинга upl.yufic.ru",
    }

    strings_ru = {
        "_cls_doc": "Загружает медиа на хостинг yufic.ru и выдает прямую ссылку.",
        "_cmd_doc_mupl": "[название] <реплай/файл> - Загрузить медиа.",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                None,
                lambda: self.strings("config_api_key_doc"),
                validator=loader.validators.Hidden(loader.validators.String()),
            )
        )
        self.http = aiohttp.ClientSession()

    async def on_unload(self):
        await self.http.close()

    @loader.command(
        ru_doc="[название] <реплай/файл> - Загрузить медиа"
    )
    async def mupl(self, message: Message):
        """[filename] <reply/file> - Upload media to hosting."""
        api_key = self.config["api_key"]
        if not api_key:
            await utils.answer(message, self.strings("no_api_key"))
            return

        reply = await message.get_reply_message()
        media_msg = message if message.media else reply

        if not media_msg or not media_msg.media:
            await utils.answer(message, self.strings("no_media"))
            return

        status_msg = await utils.answer(message, self.strings("uploading"))

        try:
            media_bytes = await media_msg.download_media(bytes)
            
            original_filename = "upload.bin"
            mime_type = "application/octet-stream" 

            if media_msg.file:
                if hasattr(media_msg.file, "name"):
                    original_filename = media_msg.file.name
                if hasattr(media_msg.file, "mime_type"):
                    mime_type = media_msg.file.mime_type

            data = aiohttp.FormData()
            
            data.add_field(
                "image",
                media_bytes,
                filename=original_filename,
                content_type=mime_type,
            )

            args = utils.get_args_raw(message)
            if args:
                filename_base = os.path.splitext(args.strip())[0]
                data.add_field("filename", filename_base)

            url = "https://upl.yufic.ru/api/upload.php"
            headers = {"Authorization": f"Bearer {api_key}"}

            async with self.http.post(url, headers=headers, data=data) as response:
                response_text = await response.text()
                status_code = response.status

            if status_code == 401:
                await utils.answer(status_msg, self.strings("error_401"))
                return
            
            if status_code >= 400:
                 try:
                     error_json = json.loads(response_text)
                     error_message = error_json.get("error", response_text)
                 except json.JSONDecodeError:
                     error_message = response_text
                 
                 await utils.answer(
                     status_msg,
                     self.strings("error").format(f"Код: {status_code}\nОтвет: {utils.escape_html(error_message)}"),
                 )
                 return

            result_json = json.loads(response_text)
            link = result_json.get("url")
            if link:
                await utils.answer(status_msg, self.strings("success").format(link, link))
            else:
                error_msg = result_json.get("error", str(result_json))
                await utils.answer(
                    status_msg,
                    self.strings("error").format(utils.escape_html(error_msg)),
                )

        except Exception as e:
            await utils.answer(
                status_msg, self.strings("error").format(utils.escape_html(str(e)))
            )