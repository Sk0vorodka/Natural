# meta developer: @PluginIDEbot
# meta banner: https://yufic.ru/api/hc/?a=VideoDownloader&b=@PluginIDEbot
# meta name: VideoDownloader
# requires: yt-dlp

import os
import asyncio
import logging
import re
import glob
import time
import concurrent.futures
from urllib.parse import urlparse, parse_qs
from collections import deque

from telethon.tl.types import Message, DocumentAttributeVideo, DocumentAttributeFilename, DocumentAttributeAnimated
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, MessageEntityMention, MessageEntityHashtag, MessageEntityCashtag, MessageEntityBotCommand, MessageEntityUrl, MessageEntityEmail, MessageEntityPhone, MessageEntityBold, MessageEntityItalic, MessageEntityCode, MessageEntityPre, MessageEntityTextUrl, MessageEntityMentionName, MessageEntityPhone, MessageEntityCashtag, MessageEntityUnderline, MessageEntityStrike, MessageEntityBlockquote, MessageEntityBankCard, MessageEntitySpoiler, MessageEntityCustomEmoji
from telethon.errors import FloodWaitError, RPCError, MessageNotModifiedError
from .. import loader, utils

logger = logging.getLogger(__name__)

class DownloadProgress:
    """Класс для отслеживания прогресса скачивания"""
    def __init__(self, message, total_size=0, update_interval=2):
        self.message = message
        self.total_size = total_size
        self.downloaded = 0
        self.start_time = time.time()
        self.last_update = 0
        self.update_interval = update_interval  # Обновлять каждые N секунды
        
        # Эмодзи для прогресса
        self.emojis = ['⬜', '⬜', '⬜', '⬜', '⬜', '⬜', '⬜', '⬜', '⬜', '⬜']
        self.download_emojis = ['⬛', '⬛', '⬛', '⬛', '⬛', '⬛', '⬛', '⬛', '⬛', '⬛']
        
    async def update_progress(self, downloaded, total, speed=0):
        """Обновление прогресса (async)"""
        try:
            current_time = time.time()
            if (current_time - self.last_update) < self.update_interval and downloaded < total:
                return  # Не обновляем слишком часто
                
            self.downloaded = downloaded
            self.last_update = current_time
            
            if total > 0:
                percent = min(100, int((downloaded / total) * 100))
                bar_length = 10
                
                # Создаем прогресс-бар
                filled_length = int(bar_length * downloaded / total)
                progress_bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                # Эмодзи прогресс
                emoji_bar = ''.join(self.download_emojis[:filled_length] + self.emojis[filled_length:])
                
                # Скорость
                elapsed = current_time - self.start_time
                if elapsed > 0 and downloaded > 0:
                    speed_mb = downloaded / (1024 * 1024) / elapsed
                    eta = (total - downloaded) / (1024 * 1024) / speed_mb if speed_mb > 0 else 0
                else:
                    speed_mb = 0
                    eta = 0
                
                # Форматируем время
                if eta > 3600:
                    eta_str = f"{int(eta//3600)}ч {int((eta%3600)//60)}м"
                elif eta > 60:
                    eta_str = f"{int(eta//60)}м {int(eta%60)}с"
                else:
                    eta_str = f"{int(eta)}с"
                
                # Размеры
                downloaded_mb = downloaded / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                
                progress_text = (
                    f"📥 <b>Скачиваю...</b>\n"
                    f"{emoji_bar} <b>{percent}%</b>\n"
                    f"<code>{progress_bar}</code>\n"
                    f"💾 <b>{downloaded_mb:.1f}/{total_mb:.1f} MB</b>\n"
                    f"⚡ <b>{speed_mb:.1f} MB/s</b> | ⏱ <b>Осталось: {eta_str}</b>"
                )
                
                try:
                    await self.message.edit(progress_text)
                except MessageNotModifiedError:
                    pass  # Игнорируем, если сообщение не изменилось
                except Exception as e:
                    logger.debug(f"Progress edit error: {e}")
            else:
                # Неизвестный размер - показываем только скачанное
                downloaded_mb = downloaded / (1024 * 1024)
                elapsed = current_time - self.start_time
                speed_mb = downloaded_mb / elapsed if elapsed > 0 else 0
                
                progress_text = (
                    f"📥 <b>Скачиваю...</b>\n"
                    f"💾 <b>{downloaded_mb:.1f} MB</b>\n"
                    f"⚡ <b>{speed_mb:.1f} MB/s</b>"
                )
                
                try:
                    await self.message.edit(progress_text)
                except MessageNotModifiedError:
                    pass
                except Exception as e:
                    logger.debug(f"Progress edit error (unknown size): {e}")
                
        except Exception as e:
            logger.debug(f"Progress update error: {e}")
            pass

    def finish(self, final_size):
        """Завершение скачивания"""
        self.total_size = final_size
        self.downloaded = final_size

@loader.tds
class VideoDownloader(loader.Module):
    """Универсальный загрузчик: реплай на ссылки/видео/GIF/аудио + 100+ платформ с прогресс-баром"""

    strings = {
        "name": "VideoDownloader",
        "version_check": (
            "🚀 <b>VideoDownloader v2025.3 - ПРОГРЕСС-БАР + РЕПЛАЙ БЕЗ COOKIES!</b>\n\n"
            "📊 <b>Новые фичи:</b>\n"
            "• Прогресс-бар (%, скорость, ETA)\n"
            "• Реплай на ссылки (автоскачивание)\n"
            "• Реплай на видео/GIF/аудио\n"
            "• YouTube без cookies (fallback)\n"
            "• TikTok, Instagram +100\n\n"
            "<b>Команды:</b>\n"
            "<code>.domp</code> (авто + прогресс)\n"
            "<code>.domp https://tiktok.com/@user/video/123</code>\n"
            "<i>Авто: YouTube→TikTok→Instagram + fallback без авторизации</i>\n\n"
            "<b>🆕 Без cookies: YouTube использует низкое качество/аудио при ошибке</b>"
        ),
        "working": "🔄 <b>Анализирую реплай...</b>",
        "ready": "✅ <b>Готов с прогресс-баром!</b>\n<i>yt-dlp: v{version} | Реплай: ✓ | Платформы: {count} | Cookies: опционально</i>",
        "install_yt_dlp": (
            "❌ <b>yt-dlp НЕ УСТАНОВЛЕН!</b>\n\n"
            "<b>🚀 УСТАНОВКА:</b>\n"
            "<code>pip install yt-dlp==2024.4.9</code>\n\n"
            "<b>Heroku:</b>\n"
            "1. <code>echo 'yt-dlp==2024.4.9' >> requirements.txt</code>\n"
            "2. <code>git add . && git commit -m 'add yt-dlp' && git push</code>\n\n"
            "<b>Проверка:</b>\n"
            "<code>.vdtest</code>\n\n"
            "<b>💡 Без cookies YouTube может требовать авторизации - fallback на аудио/низкое качество</b>"
        ),
        "install_ffmpeg": (
            "⚠️ <b>FFmpeg отсутствует</b>\n\n"
            "<b>Для видео с прогрессом рекомендуется:</b>\n"
            "<code>sudo apt install ffmpeg</code>\n"
            "<code>brew install ffmpeg</code>\n\n"
            "<b>Heroku buildpack:</b>\n"
            "<code>heroku buildpacks:add https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git</code>"
        ),
        "error": "❌ <b>Ошибка:</b>\n<i>{}</i>",
        "no_content": "❌ <b>Реплай на пустое сообщение!</b>\n<i>Реплайните на ссылку или медиа</i>",
        "success": "✅ <b>{type} загружено!</b>",
        "download_failed": (
            "❌ <b>Не удалось загрузить с {platform}</b>\n<i>Проверьте ссылку или формат</i>\n\n"
            "<b>🔧 Общие советы:</b>\n"
            "• Запустите <code>.vdtest</code> для проверки\n"
            "• Если файл >50MB: fallback на аудио/низкое качество\n"
            "• Прямые MP4/MP3 работают без проблем\n"
            "• Для {platform}: попробуйте другую ссылку или формат"
        ),
        "processing": "⏳ <b>Скачиваю {type}...</b>",
        "video_info": (
            "📹 <b>{title}</b>\n"
            "🔗 <b>Источник:</b> {source}\n"
            "⏱ <b>{duration}</b> | 💾 <b>{size}</b>"
        ),
        "link_reply": (
            "🔗 <b>Ссылка обнаружена!</b>\n"
            "🌐 <b>Платформа:</b> {platform}\n"
            "⏳ <b>Скачиваю с прогрессом...</b>"
        ),
        "media_reply": (
            "💾 <b>Медиа из реплая!</b>\n"
            "📁 <b>{filename}</b>\n"
            "⏳ <b>Обрабатываю...</b>"
        ),
        "reply_success": (
            "✅ <b>Из реплая!</b>\n"
            "📁 <b>{filename}</b>\n"
            "💾 <b>{size}</b>"
        ),
        "not_media": "❌ <b>Не медиа/ссылка!</b>\n<i>Реплайните на видео, GIF, аудио или ссылку</i>",
        "large_file": "⚠️ <b>Файл >50MB</b>\n<i>Telegram ограничение. Fallback: аудио/низкое качество</i>",
        "source_detected": "🔍 <b>Платформа: {platform}</b>\n⏳ <b>Автоопределение → Скачиваю с прогрессом</b>",
        "url_fixed": "🔧 <b>URL исправлен</b>",
        "playlist_warning": "📋 <b>Плейлист</b>\n⏳ Беру первое",
        "audio_only": "🎵 <b>Аудио (fallback без cookies)</b>\n💾 <b>{format}</b>",
        "gif_detected": "🎭 <b>GIF</b>\n⏳ Обрабатываю",
        "youtube_auth_error": (
            "🚫 <b>YouTube: fallback без cookies</b>\n\n"
            "<b>🔧 Автоматически:</b>\n"
            "• Переключаюсь на низкое качество (480p)\n"
            "• Или только аудио (MP3)\n"
            "• Прогресс продолжается...\n\n"
            "<b>💡 Для полного доступа:</b>\n"
            "<code>.vdhelp cookies</code>\n\n"
            "<i>Без cookies: ограничения на видео с защитой</i>"
        ),
        "cookies_not_set": (
            "⚠️ <b>Cookies опциональны</b>\n\n"
            "<b>YouTube без cookies:</b>\n"
            "• Fallback: 480p видео или аудио\n"
            "• Возрастные видео могут не работать\n\n"
            "<b>🔗 Если нужно:</b>\n"
            "<code>.vdhelp cookies</code>"
        ),
        "platforms_list": (
            "🌐 <b>ПОДДЕРЖИВАЕМЫЕ ПЛАТФОРМЫ (100+ без cookies):</b>\n\n"
            "<b>📺 Видео:</b>\n"
            "• YouTube (fallback 480p/аудио)\n"
            "• TikTok (видео, дуэты)\n"
            "• Instagram (Reels, Posts)\n"
            "• Twitter/X (видео)\n"
            "• Facebook, VK +100\n\n"
            "<b>🎵 Аудио:</b>\n"
            "• SoundCloud, Spotify\n"
            "• Deezer, Bandcamp\n\n"
            "<b>📱 Соцсети:</b>\n"
            "• Reddit, Pinterest\n"
            "• Tumblr, Vimeo\n\n"
            "<b>📺 Прямые:</b>\n"
            "• MP4, WebM, MP3 файлы\n\n"
            "<b>🔧 yt-dlp: 1000+ сайтов</b>\n"
            "<i>Список: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md</i>"
        ),
        "debug_info": (
            "🔧 <b>DIAGNOSTICS v2025.3 (без cookies):</b>\n\n"
            "📦 <b>yt-dlp:</b> {version}\n"
            "⚙️ <b>FFmpeg:</b> {ffmpeg}\n"
            "🍪 <b>Cookies:</b> Опционально (fallback OK)\n"
            "📊 <b>Прогресс-бар:</b> ✓\n"
            "🔗 <b>Реплай ссылки:</b> ✓\n"
            "💾 <b>Реплай медиа:</b> ✓\n"
            "🌐 <b>Платформы:</b> {count}\n\n"
            "🚀 <b>Статус:</b> {status}"
        ),
        "reply_help": (
            "🔗 <b>РЕПЛАЙ НА ССЫЛКИ С ПРОГРЕССОМ (без cookies):</b>\n\n"
            "<b>✅ ССЫЛКИ:</b>\n"
            "• YouTube (fallback 480p/аудио)\n"
            "• TikTok, Instagram Reels\n"
            "• Twitter, VK +100\n\n"
            "<b>✅ МЕДИА:</b>\n"
            "• Видео (MP4, GIF)\n"
            "• Аудио (MP3, OGG)\n\n"
            "<b>📊 ПРОГРЕСС:</b>\n"
            "• % загрузки + бар\n"
            "• Скорость MB/s\n"
            "• ETA время\n\n"
            "<b>Использование:</b>\n"
            "<code>[ссылка]</code> ↓ <code>.domp</code>\n\n"
            "<b>Пример:</b>\n"
            "<code>⬛⬛⬜⬜... 45% | 2.1 MB/s | 1м 23с</code>"
        ),
        "terminal_install": (
            "💻 <b>УСТАНОВКА БЕЗ COOKIES:</b>\n\n"
            "<b>1. yt-dlp:</b>\n"
            "<code>pip install yt-dlp==2024.4.9</code>\n\n"
            "<b>2. FFmpeg (рекомендуется):</b>\n"
            "<code>sudo apt install ffmpeg</code>\n\n"
            "<b>3. Cookies (опционально):</b>\n"
            "<code># Без cookies: fallback на аудио/480p</code>\n"
            "<code># Для полного YouTube: .vdhelp cookies</code>\n\n"
            "<b>4. Тест:</b>\n"
            "<code>.vdtest</code>\n"
            "<code>[YouTube] ↓ .domp</code>\n\n"
            "<b>Heroku:</b>\n"
            "<code>echo 'yt-dlp==2024.4.9' >> requirements.txt</code>\n"
            "<code>git push</code>"
        ),
        "cookies_help": (
            "🍪 <b>COOKIES ОПЦИОНАЛЬНЫ ДЛЯ YOUTUBE:</b>\n\n"
            "<b>Без cookies (fallback):</b>\n"
            "• 480p видео или аудио (MP3)\n"
            "• Возрастные видео могут не работать\n"
            "• Прогресс-бар работает\n\n"
            "<b>С cookies (полный доступ):</b>\n"
            "• HD видео (720p+), плейлисты\n"
            "• Обход 'Sign in to confirm'\n\n"
            "<b>Как получить (если нужно):</b>\n"
            "1. <b>Chrome:</b> Расширение 'Get cookies.txt LOCALLY'\n"
            "   • YouTube → авторизация → Export\n"
            "2. <b>Firefox:</b> 'cookies.txt' → Export\n"
            "3. <b>Онлайн:</b> https://puppeteers.net/cookies\n\n"
            "<b>Настройка:</b>\n"
            "• .config → cookies_path: <code>cookies.txt</code>\n"
            "• git add cookies.txt && git push\n\n"
            "<b>🔗 Доки:</b>\n"
            "https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
        )
    }

    def __init__(self):
        self.temp_files = set()
        self.download_dir = "downloads"
        self.yt_dlp_version = None
        self.progress_instance = None
        self.progress_queue = asyncio.Queue()  # Очередь для прогресса из потока
        self.supported_mime = {
            'video': ['video/mp4', 'video/webm', 'video/x-msvideo', 'video/avi', 'video/mpeg', 'video/quicktime'],
            'gif': ['image/gif', 'video/gif'],
            'audio': ['audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/ogg', 'audio/flac', 'audio/x-wav'],
            'voice': ['audio/ogg']
        }
        self.supported_ext = {
            'video': ['.mp4', '.webm', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.3gp', '.m4v'],
            'audio': ['.mp3', '.m4a', '.wav', '.flac', '.aac', '.ogg'],
            'gif': ['.gif']
        }
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "cookies_path",
                "",
                lambda: self.strings("cookies_help"),
                validator=loader.validators.String()
            ),
            loader.ConfigValue(
                "progress_update_interval",
                2,
                lambda: "Интервал обновления прогресса в секундах (1-5)",
                validator=loader.validators.Integer()
            )
        )

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Инициализация
        self.yt_dlp_version = await self._get_yt_dlp_version()
        self.ffmpeg_available = await self._check_ffmpeg()
        
        cookies_status = "Опционально" if not self.config["cookies_path"] else "✓"
        
        logger.info(f"🚀 VideoDownloader v2025.3 - ПРОГРЕСС + БЕЗ COOKIES")
        logger.info(f"yt-dlp: {self.yt_dlp_version}")
        logger.info(f"FFmpeg: {self.ffmpeg_available}")
        logger.info(f"Cookies: {cookies_status} (fallback OK)")
        logger.info(f"Reply support: Links + Media ✓")
        logger.info(f"Progress queue: Enabled for thread safety")
        
        # Статус в ЛС
        try:
            if self.yt_dlp_version:
                await utils.answer(
                    await client.get_messages('me', limit=1),
                    self.strings("ready").format(
                        version=self.yt_dlp_version,
                        count="100+"
                    )
                )
                await utils.answer(
                    await client.get_messages('me', limit=1),
                    self.strings("version_check")
                )
            else:
                await utils.answer(
                    await client.get_messages('me', limit=1),
                    self.strings("install_yt_dlp")
                )
        except:
            pass

    async def _get_yt_dlp_version(self):
        """Версия yt-dlp"""
        try:
            import yt_dlp
            version = getattr(yt_dlp.version, '__version__', None)
            if version:
                logger.info(f"yt-dlp v{version}")
                return version
            return None
        except ImportError:
            return None

    async def _check_ffmpeg(self):
        """FFmpeg"""
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=10)
            return result.returncode == 0
        except:
            return False

    def _extract_urls_from_text(self, message: Message) -> list[str]:
        """Извлечение чистых URL из текста с учетом entities"""
        urls = []
        try:
            if not message or not message.text:
                return urls

            text_lower = message.text.lower()
            
            # 1. Простой поиск URL в тексте (fallback)
            url_pattern = r'https?://[^\s<>"]+'
            matches = re.findall(url_pattern, message.text)
            for match in matches:
                # Удаляем HTML-теги, если они есть
                clean_url = re.sub(r'<[^>]*>', '', match).strip()
                if clean_url and clean_url.startswith('http') and len(clean_url) > 10:
                    urls.append(clean_url)

            # 2. Парсинг через entities (более надежно)
            if hasattr(message, 'entities') and message.entities:
                text_offset = 0
                for entity in message.entities:
                    if isinstance(entity, (MessageEntityTextUrl, MessageEntityUrl)):
                        if isinstance(entity, MessageEntityTextUrl):
                            url = entity.url
                            # Проверяем, валидный ли URL
                            if url and url.startswith('http') and len(url) > 10:
                                urls.append(url)
                        else:  # MessageEntityUrl
                            start = text_offset + entity.offset
                            end = start + entity.length
                            url_text = message.text[start:end]
                            # Удаляем теги из url_text
                            clean_url_text = re.sub(r'<[^>]*>', '', url_text).strip()
                            if clean_url_text and clean_url_text.startswith('http') and len(clean_url_text) > 10:
                                urls.append(clean_url_text)
                            # Fallback: если текст содержит YouTube ID, попробуем извлечь
                            if 'youtube' in text_lower:
                                yt_match = re.search(r'v=([a-zA-Z0-9_-]{11})', clean_url_text)
                                if yt_match:
                                    video_id = yt_match.group(1)
                                    if len(video_id) == 11:
                                        urls.append(f"https://www.youtube.com/watch?v={video_id}")

                    text_offset += entity.length

            # Удаляем дубликаты
            urls = list(set(urls))
            logger.debug(f"Extracted URLs from text: {urls}")

        except Exception as e:
            logger.error(f"Error extracting URLs from text: {e}")

        return urls

    def _is_reply_content(self, message: Message) -> tuple[bool, dict]:
        """Проверка содержимого реплая"""
        try:
            if not message:
                return False, {}
                
            content_type = None
            content_data = {}
            text_lower = message.text.lower() if message.text else ""
            
            # 1. ПРОВЕРКА НА ССЫЛКУ В ТЕКСТЕ
            if message.text:
                # Извлекаем чистые URL
                extracted_urls = self._extract_urls_from_text(message)
                
                # YouTube ссылки (расширенные паттерны)
                youtube_patterns = [
                    r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/|youtube-nocookie\.com/embed/|m\.youtube\.com/watch\?v=|youtube\.com/v/|youtube\.com/playlist\?list=|youtube\.com/channel/)([a-zA-Z0-9_-]{11})',
                    r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
                    r'youtu\.be/([a-zA-Z0-9_-]{11})',
                    r'v=([a-zA-Z0-9_-]{11})'  # Fallback для ID в тексте
                ]
                
                for url in extracted_urls:
                    url_lower = url.lower()
                    for pattern in youtube_patterns:
                        match = re.search(pattern, url)
                        if match:
                            video_id = match.group(1)
                            if len(video_id) == 11:
                                content_type = 'youtube_link'
                                content_data = {
                                    'type': 'link',
                                    'platform': 'YouTube',
                                    'url': f"https://www.youtube.com/watch?v={video_id}",
                                    'text': message.text,
                                    'video_id': video_id,
                                    'original_urls': extracted_urls
                                }
                                logger.info(f"Reply link detected: YouTube {video_id}")
                                return True, content_data
                
                # Fallback: если 'youtube' в тексте, ищем ID
                if 'youtube' in text_lower and not content_type:
                    yt_match = re.search(r'v=([a-zA-Z0-9_-]{11})', message.text)
                    if yt_match:
                        video_id = yt_match.group(1)
                        if len(video_id) == 11:
                            content_type = 'youtube_link'
                            content_data = {
                                'type': 'link',
                                'platform': 'YouTube',
                                'url': f"https://www.youtube.com/watch?v={video_id}",
                                'text': message.text,
                                'video_id': video_id,
                                'original_urls': extracted_urls
                            }
                            logger.info(f"Reply fallback YouTube ID: {video_id}")
                            return True, content_data

                # TikTok ссылки (расширенные, включая musical.ly)
                tiktok_patterns = [
                    r'(?:https?://)?(?:www\.)?(?:tiktok\.com/@[^/]+/video/|vm\.tiktok\.com/|musical\.ly/)([0-9]+)',
                    r'tiktok\.com/@[^/]+/video/([0-9]+)',
                    r'vm\.tiktok\.com/([a-zA-Z0-9]+)'
                ]
                
                for url in extracted_urls:
                    url_lower = url.lower()
                    for pattern in tiktok_patterns:
                        match = re.search(pattern, url)
                        if match:
                            video_id = match.group(1)
                            content_type = 'tiktok_link'
                            content_data = {
                                'type': 'link',
                                'platform': 'TikTok',
                                'url': url,
                                'text': message.text,
                                'video_id': video_id,
                                'original_urls': extracted_urls
                            }
                            logger.info(f"Reply link detected: TikTok {video_id}")
                            return True, content_data
                
                # Fallback для TikTok (улучшенный)
                if 'tiktok' in text_lower and not content_type:
                    tt_match = re.search(r'(?:tiktok\.com/@[^/]+/video/|vm\.tiktok\.com/|musical\.ly/)([0-9]+)', message.text)
                    if tt_match:
                        video_id = tt_match.group(1)
                        content_type = 'tiktok_link'
                        content_data = {
                            'type': 'link',
                            'platform': 'TikTok',
                            'url': f"https://www.tiktok.com/@user/video/{video_id}",
                            'text': message.text,
                            'video_id': video_id,
                            'original_urls': extracted_urls
                        }
                        logger.info(f"Reply fallback TikTok ID: {video_id}")
                        return True, content_data

                # Instagram ссылки (расширенные, включая /tv/)
                instagram_patterns = [
                    r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_-]+)',
                    r'instagram\.com/(?:stories|reel)/[^/]+/([a-zA-Z0-9_-]+)'
                ]
                
                for url in extracted_urls:
                    url_lower = url.lower()
                    for pattern in instagram_patterns:
                        match = re.search(pattern, url)
                        if match:
                            post_id = match.group(1)
                            content_type = 'instagram_link'
                            content_data = {
                                'type': 'link',
                                'platform': 'Instagram',
                                'url': url,
                                'text': message.text,
                                'post_id': post_id,
                                'original_urls': extracted_urls
                            }
                            logger.info(f"Reply link detected: Instagram {post_id}")
                            return True, content_data

                # Twitter ссылки (расширенные)
                twitter_patterns = [
                    r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/[^/]+/status/([0-9]+)',
                    r'(?:twitter\.com|x\.com)/i/web/status/([0-9]+)'
                ]
                
                for url in extracted_urls:
                    url_lower = url.lower()
                    for pattern in twitter_patterns:
                        match = re.search(pattern, url)
                        if match:
                            status_id = match.group(1)
                            content_type = 'twitter_link'
                            content_data = {
                                'type': 'link',
                                'platform': 'Twitter',
                                'url': url,
                                'text': message.text,
                                'status_id': status_id,
                                'original_urls': extracted_urls
                            }
                            logger.info(f"Reply link detected: Twitter {status_id}")
                            return True, content_data

                # Общие ссылки (любые http/https)
                if extracted_urls:
                    for url in extracted_urls:
                        platform = self._detect_platform(url)
                        if platform != "Unknown":
                            content_type = f'{platform.lower()}_link'
                            content_data = {
                                'type': 'link',
                                'platform': platform,
                                'url': url,
                                'text': message.text,
                                'full_text': True,
                                'original_urls': extracted_urls
                            }
                            logger.info(f"Reply link detected: {platform}")
                            return True, content_data

            # 2. ПРОВЕРКА НА МЕДИА
            media_type, file_ext = self._get_media_type(message)
            if media_type:
                content_type = f'{media_type}_media'
                content_data = {
                    'type': 'media',
                    'media_type': media_type,
                    'file_ext': file_ext,
                    'message': message
                }
                logger.info(f"Reply media detected: {media_type}")
                return True, content_data

            return False, {}
            
        except Exception as e:
            logger.error(f"Reply content check error: {e}")
            return False, {}

    def _get_media_type(self, message: Message) -> tuple[str, str]:
        """Определение типа медиа"""
        try:
            if not message or not hasattr(message, 'media'):
                return None, None

            # Видео
            if hasattr(message, 'video') and message.video:
                return 'video', 'mp4'

            # Документ
            if hasattr(message, 'document') and message.document:
                doc = message.document
                mime_type = getattr(doc, 'mime_type', '').lower()
                
                # Видео форматы
                if any(vmime in mime_type for vmime in self.supported_mime['video']):
                    ext = 'mp4'
                    if 'webm' in mime_type:
                        ext = 'webm'
                    elif 'avi' in mime_type:
                        ext = 'avi'
                    return 'video', ext
                
                # GIF
                if any(gmime in mime_type for gmime in self.supported_mime['gif']):
                    return 'gif', 'gif'
                
                # Аудио
                if any(amime in mime_type for amime in self.supported_mime['audio']):
                    ext = 'mp3'
                    if 'm4a' in mime_type:
                        ext = 'm4a'
                    elif 'wav' in mime_type:
                        ext = 'wav'
                    return 'audio', ext
                
                # Голосовые (OGG)
                if 'ogg' in mime_type:
                    return 'voice', 'ogg'

                # Проверка атрибутов
                if hasattr(doc, 'attributes') and doc.attributes:
                    for attr in doc.attributes:
                        attr_type = type(attr).__name__
                        
                        if attr_type == 'DocumentAttributeVideo':
                            return 'video', 'mp4'
                        elif attr_type == 'DocumentAttributeAnimated':
                            return 'gif', 'gif'
                        
                        # Имя файла
                        if attr_type == 'DocumentAttributeFilename':
                            filename = getattr(attr, 'file_name', '').lower()
                            
                            for media_t, exts in self.supported_ext.items():
                                for ext in exts:
                                    if ext in filename:
                                        return media_t, ext[1:]  # без точки

            return None, None
            
        except Exception as e:
            logger.error(f"Media type error: {e}")
            return None, None

    def _detect_platform(self, url: str) -> str:
        """Определение платформы"""
        try:
            url_lower = url.lower()
            
            # TikTok (улучшенная проверка, чтобы избежать ложного YouTube)
            if any(domain in url_lower for domain in ['tiktok.com', 'vm.tiktok.com', 'musical.ly']):
                # Дополнительная проверка: убедимся, что нет YouTube в URL
                if 'youtube' not in url_lower:
                    return "TikTok"
            
            # YouTube (расширенная проверка)
            if any(ind in url_lower for ind in ['youtube.com', 'youtu.be', 'youtube-nocookie.com', 'm.youtube.com', 'watch?v=', 'shorts/', 'embed/', 'v/']):
                return "YouTube"
            
            # Instagram
            if 'instagram.com' in url_lower and any(path in url_lower for path in ['/reel/', '/p/', '/tv/', '/stories/']):
                return "Instagram"
            
            # Twitter/X
            if any(domain in url_lower for domain in ['twitter.com', 'x.com']) and any(path in url_lower for path in ['/status/', '/i/web/status/']):
                return "Twitter"
            
            # Facebook
            if 'facebook.com' in url_lower and any(path in url_lower for path in ['/watch/', '/video/', '/reel/', '?v=']):
                return "Facebook"
            
            # VK
            if 'vk.com' in url_lower and any(path in url_lower for path in ['/video', '/clip']):
                return "VK"
            
            # SoundCloud
            if 'soundcloud.com' in url_lower and any(path in url_lower for path in ['/track/', '/sets/', '/playlist/']):
                return "SoundCloud"
            
            # Twitch
            if 'twitch.tv' in url_lower and any(path in url_lower for path in ['/videos/', '/clip/', '/v/']):
                return "Twitch"
            
            # Reddit
            if 'reddit.com' in url_lower and any(path in url_lower for path in ['/comments/', '/r/']):
                return "Reddit"
            
            # Pinterest
            if 'pinterest.com' in url_lower and '/pin/' in url_lower:
                return "Pinterest"
            
            # Tumblr
            if 'tumblr.com' in url_lower and any(path in url_lower for path in ['/post/', '/video/']):
                return "Tumblr"
            
            # Vimeo
            if 'vimeo.com' in url_lower and any(path in url_lower for path in ['/video/', '/channels/', '/groups/']):
                return "Vimeo"
            
            # Dailymotion
            if 'dailymotion.com' in url_lower and any(path in url_lower for path in ['/video/', '/embed/']):
                return "Dailymotion"
            
            # Rumble
            if 'rumble.com' in url_lower and any(path in url_lower for path in ['/v', '/embed/']):
                return "Rumble"
            
            # Bitchute
            if 'bitchute.com' in url_lower and any(path in url_lower for path in ['/video/', '/embed/']):
                return "Bitchute"
            
            # Прямые файлы
            if any(ext in url_lower for ext in ['.mp4', '.webm', '.avi', '.mkv', '.mp3', '.m4a']):
                return "Direct File"
            
            return "Other"
        except:
            return "Unknown"

    def _fix_url(self, url: str, platform: str) -> str:
        """Исправление URL"""
        try:
            original = url.strip()
            
            if not original.startswith(('http', 'https')):
                if platform in ['YouTube', 'TikTok', 'Instagram', 'Twitter']:
                    url = 'https://' + original
                else:
                    url = original
            else:
                url = original
            
            # YouTube youtu.be и другие
            if platform == "YouTube":
                if 'youtu.be/' in url:
                    video_id = url.split('youtu.be/')[1].split('?')[0].split('/')[0][:11]
                    if len(video_id) == 11:
                        return f"https://www.youtube.com/watch?v={video_id}"
                
                # Из query parameters или /v/
                parsed = urlparse(url)
                if 'v' in parse_qs(parsed.query):
                    video_id = parse_qs(parsed.query)['v'][0][:11]
                    if len(video_id) == 11:
                        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                        return f"{base}?v={video_id}"
                
                # /embed/ или /shorts/
                if '/embed/' in url:
                    video_id_match = re.search(r'/embed/([a-zA-Z0-9_-]{11})', url)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        return f"https://www.youtube.com/watch?v={video_id}"
                
                # /shorts/
                if '/shorts/' in url:
                    video_id_match = re.search(r'/shorts/([a-zA-Z0-9_-]{11})', url)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        return f"https://www.youtube.com/watch?v={video_id}"
                
                # /v/ (старый формат)
                if '/v/' in url:
                    video_id_match = re.search(r'/v/([a-zA-Z0-9_-]{11})', url)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        return f"https://www.youtube.com/watch?v={video_id}"
            
            # Instagram stories (fallback)
            if platform == "Instagram" and '/stories/' in url and not url.startswith('http'):
                return f"https://www.instagram.com{url}"
            
            # TikTok fallback (улучшенный)
            if platform == "TikTok" and not url.startswith('http'):
                return f"https://www.tiktok.com{url}"
            
            return url
        except:
            return url

    def _is_valid_url(self, text: str) -> tuple[bool, str]:
        """Валидация URL"""
        try:
            original = text.strip()
            if not original:
                return False, ""
                
            if not original.startswith(('http', 'https')):
                normalized = 'https://' + original
            else:
                normalized = original

            parsed = urlparse(normalized)
            return parsed.scheme in ['http', 'https'] and parsed.netloc, normalized
        except:
            return False, text

    async def _safe_run_in_executor(self, func, *args, **kwargs):
        """Безопасный run_in_executor с fallback для Heroku/модулей"""
        try:
            loop = asyncio.get_running_loop()
            if loop:
                return await loop.run_in_executor(None, func, *args, **kwargs)
            else:
                # Fallback: используем ThreadPoolExecutor напрямую
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(func, *args, **kwargs)
                    return future.result()
        except RuntimeError as e:
            if "no running event loop" in str(e):
                logger.warning(f"Loop error fallback: {e}")
                # Python 3.9+ to_thread
                if hasattr(asyncio, 'to_thread'):
                    return await asyncio.to_thread(func, *args, **kwargs)
                else:
                    # Старый fallback
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(func, *args, **kwargs)
                        return future.result()
            else:
                raise e

    async def _progress_processor(self, progress_instance):
        """Процессор очереди прогресса (async)"""
        while True:
            try:
                data = await self.progress_queue.get()
                if data is None:  # Сигнал завершения
                    break
                downloaded, total, speed = data
                await progress_instance.update_progress(downloaded, total, speed)
                self.progress_queue.task_done()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.debug(f"Progress processor error: {e}")
                await asyncio.sleep(0.1)

    async def _download_generic(self, message: Message, url: str, platform: str, opts_overrides=None):
        """Общий метод скачивания с прогрессом и fallback без cookies"""
        progress_msg = None
        progress_task = None
        try:
            import yt_dlp
            
            # Инициализируем прогресс
            progress_msg = await utils.answer(message, self.strings("processing").format(type=platform))
            self.progress_instance = DownloadProgress(progress_msg, update_interval=self.config["progress_update_interval"])
            
            # Запуск процессора прогресса
            progress_task = asyncio.create_task(self._progress_processor(self.progress_instance))
            
            # Базовые опции (cookies опционально)
            cookiefile = self.config["cookies_path"] if self.config["cookies_path"] else None
            base_opts = {
                'format': 'best[height<=720]/best',
                'outtmpl': f"{self.download_dir}/%(title:.100)s_%(id)s.%(ext)s",
                'quiet': True,
                'cookiefile': cookiefile,
                'progress_hooks': [self._progress_hook],
                'extractor_args': {
                    'generic': {'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}}
                }
            }
            
            # Платформо-специфичные опции
            platform_opts = {
                'YouTube': {
                    'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                    'merge_output_format': 'mp4',
                    'extractor_args': {'youtube': {'skip': ['hls', 'dash']}}
                },
                'TikTok': {
                    'format': 'best[height<=720]',
                    'extractor_args': {'tiktok': {'mobile': True, 'guest': True}}
                },
                'Instagram': {
                    'format': 'best[height<=720]',
                    'extractor_args': {'instagram': {'login': None}}
                },
                'Twitter': {
                    'format': 'best[height<=720]',
                    'extractor_args': {'twitter': {'guest': True}}
                },
                'Facebook': {
                    'format': 'best[height<=720]',
                    'extractor_args': {'facebook': {'http_headers': {'User-Agent': 'Mozilla/5.0'}}}
                },
                'VK': {
                    'format': 'best[height<=720]',
                    'extractor_args': {'vk': {'https_header': 'Mozilla/5.0'}}
                },
                'SoundCloud': {
                    'format': 'bestaudio/best',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
                },
                'Twitch': {
                    'format': 'best[height<=720]',
                    'extractor_args': {'twitch': {'player_client': 'twitchweb'}}
                },
                'Pinterest': {
                    'format': 'best',
                    'extractor_args': {'generic': {'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Referer': 'https://www.pinterest.com/'
                    }}}
                },
                'Other': {
                    'format': 'best',
                    'extractor_args': {'generic': {'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}}}
                }
            }
            
            # Fallback форматы (для YouTube без cookies)
            fallback_formats = [
                'best[height<=720]/best',  # Основной
                'bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]',  # С мержем
                'worst[height<=480]/worst',  # Низкое качество (fallback без auth)
                'bestaudio/best',  # Только аудио
                'best'  # Универсальный
            ]
            
            # Применяем опции
            opts = {**base_opts, **platform_opts.get(platform, platform_opts.get('Other', {}))}
            if opts_overrides:
                opts.update(opts_overrides)
            
            # Информация о видео (в executor для consistency)
            def extract_info():
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, **{k: v for k, v in opts.items() if k in ['cookiefile', 'extractor_args']}}) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await self._safe_run_in_executor(extract_info)
                
            if not info or not info.get('id'):
                logger.error(f"No info or ID for {url}")
                await self._safe_edit_or_reply(progress_msg, message, self.strings("download_failed").format(platform=platform))
                if progress_msg:
                    try:
                        await progress_msg.delete()
                    except:
                        pass
                if progress_task:
                    self.progress_queue.put_nowait(None)  # Сигнал завершения
                    await progress_task
                return False, None

            title = info.get('title', 'Unknown')[:50]
            duration = info.get('duration', 0)
            filesize = info.get('filesize', 0) or 0  # Fallback 0
            
            # Установка размера для прогресса
            self.progress_instance.total_size = filesize
            
            duration_str = f"{duration}s" if duration else "N/A"
            info_text = self.strings("video_info").format(
                title=title,
                source=platform,
                duration=duration_str,
                size=self._format_size(filesize)
            )
            await self._safe_edit_or_reply(progress_msg, message, info_text)

            # Скачивание с fallback
            download_success = False
            current_fallback = 0
            for fmt in fallback_formats:
                try:
                    current_fallback += 1
                    current_opts = opts.copy()
                    current_opts['format'] = fmt
                    
                    # Для YouTube fallback без cookies
                    if platform == "YouTube" and current_fallback > 1 and cookiefile:
                        current_opts['cookiefile'] = None  # Отключаем cookies для fallback
                        await self._safe_edit_or_reply(progress_msg, message, self.strings("youtube_auth_error"))
                        await asyncio.sleep(0.5)  # Задержка между fallback'ами
                    
                    logger.info(f"Trying fallback {current_fallback}/{len(fallback_formats)} for {platform}: {fmt}")
                    
                    # Скачивание в executor
                    def download_func():
                        with yt_dlp.YoutubeDL(current_opts) as ydl:
                            ydl.download([url])
                    
                    await self._safe_run_in_executor(download_func)
                    
                    # Проверка файла
                    files = glob.glob(f"{self.download_dir}/*{info['id']}*")
                    if files:
                        latest_file = max(files, key=os.path.getctime)
                        if os.path.exists(latest_file) and os.path.getsize(latest_file) > 0:
                            file_size = os.path.getsize(latest_file)
                            if file_size > 50 * 1024 * 1024:
                                await self._safe_edit_or_reply(progress_msg, message, self.strings("large_file"))
                                if progress_msg:
                                    try:
                                        await progress_msg.delete()
                                    except:
                                        pass
                                if progress_task:
                                    self.progress_queue.put_nowait(None)
                                    await progress_task
                                return False, None
                            download_success = True
                            self.progress_instance.finish(file_size)
                            break
                        else:
                            # Логируем форматы
                            list_opts = current_opts.copy()
                            list_opts['listformats'] = True
                            def list_formats():
                                with yt_dlp.YoutubeDL(list_opts) as ydl_list:
                                    return ydl_list.extract_info(url, download=False).get('formats', [])
                            
                            formats_info = await self._safe_run_in_executor(list_formats)
                            logger.info(f"Available formats ({len(formats_info)}): { [f.get('format_id') for f in formats_info[:3]] }")
                    else:
                        logger.warning(f"No file for fallback {current_fallback}")
                        
                except Exception as fmt_error:
                    error_str = str(fmt_error)
                    if any(err in error_str for err in ["Requested format is not available", "Unable to extract", "Sign in to confirm"]):
                        logger.warning(f"Fallback {current_fallback} failed ({platform}): {error_str[:50]}. Trying next...")
                        await asyncio.sleep(0.3)  # Короткая задержка между fallback'ами
                        continue
                    else:
                        logger.error(f"Unexpected error in fallback {current_fallback}: {fmt_error}")
                        break

            if not download_success:
                logger.error(f"All fallbacks failed for {url} ({platform}) - loop/extractor error")
                await self._safe_edit_or_reply(progress_msg, message, self.strings("download_failed").format(platform=platform))
                if progress_msg:
                    try:
                        await progress_msg.delete()
                    except:
                        pass
                if progress_task:
                    self.progress_queue.put_nowait(None)
                    await progress_task
                return False, None

            # Финальный файл
            files = glob.glob(f"{self.download_dir}/*{info['id']}*")
            latest_file = max(files, key=os.path.getctime)
            
            self.temp_files.add(latest_file)
            
            # Подпись
            caption = f"📹 <b>{title}</b>\n🔗 <b>{platform} (прогресс ✓)</b>\n{self._format_size(os.path.getsize(latest_file))}"
            
            await self.client.send_file(
                message.to_id,
                latest_file,
                caption=caption,
                reply_to=message.reply_to_msg_id,
                supports_streaming=True
            )
            
            # Очистка
            self.progress_instance = None
            if progress_msg:
                try:
                    await progress_msg.delete()
                except:
                    pass
            if progress_task:
                self.progress_queue.put_nowait(None)
                await progress_task
            return True, title

        except Exception as e:
            error_str = str(e)
            if "Sign in to confirm" in error_str and platform == "YouTube":
                await self._safe_edit_or_reply(progress_msg, message, self.strings("youtube_auth_error"))
                if progress_task:
                    self.progress_queue.put_nowait(None)
                    await progress_task
                return False, None
            logger.error(f"{platform} download error: {e}")
            await self._safe_edit_or_reply(progress_msg, message, self.strings("download_failed").format(platform=platform))
            if progress_msg:
                try:
                    await progress_msg.delete()
                except:
                    pass
            if progress_task:
                self.progress_queue.put_nowait(None)
                await progress_task
            return False, None

    async def _safe_edit_or_reply(self, edit_msg, original_msg, text):
        """Безопасное редактирование или ответ"""
        try:
            if edit_msg:
                await edit_msg.edit(text)
        except MessageNotModifiedError:
            pass  # Сообщение не изменилось, игнорируем
        except Exception as e:
            logger.debug(f"Edit failed, replying: {e}")
            if original_msg:
                await original_msg.reply(text)
        except:
            if original_msg:
                await original_msg.reply(text)

    def _progress_hook(self, d):
        """Хук прогресса yt-dlp (sync, thread-safe)"""
        try:
            if self.progress_instance and d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0)
                
                # Безопасная отправка в очередь (не требует loop)
                try:
                    self.progress_queue.put_nowait((downloaded, total, speed))
                except asyncio.QueueFull:
                    logger.debug("Progress queue full, skipping update")
                    
            elif d['status'] == 'finished':
                logger.info(f"Download finished: {d.get('filename', 'Unknown')}")
                
        except Exception as e:
            logger.debug(f"Progress hook error: {e}")

    @loader.command()
    async def dompcmd(self, message: Message):
        """Универсальная команда: автоопределение платформы и блок кода с прогрессом"""
        try:
            logger.info(f"🚀 DOMP: {message.sender_id} in {message.chat_id}")
            
            # Проверка yt-dlp
            if not self.yt_dlp_version:
                await utils.answer(message, self.strings("install_yt_dlp"))
                return

            await utils.answer(message, self.strings("working"))
            
            # АНАЛИЗ РЕПЛАЯ
            reply = None
            try:
                reply = await message.get_reply_message()
            except Exception as e:
                logger.debug(f"No reply available: {e}")

            url = None
            platform = None

            if reply:
                has_content, content_data = self._is_reply_content(reply)
                if has_content:
                    logger.info(f"→ Reply content: {content_data.get('type', 'unknown')}")
                    
                    # РЕПЛАЙ НА ССЫЛКУ
                    if content_data.get('type') == 'link':
                        platform = content_data.get('platform', 'Unknown')
                        url = content_data['url']
                        
                        await utils.answer(message, self.strings("link_reply").format(
                            platform=platform
                        ))
                        
                        success, title = await self._download_generic(message, url, platform)
                        if success:
                            await self._safe_edit_or_reply(None, message, self.strings("success").format(
                                type=f"{platform} (автоблок + прогресс)"
                            ))
                            await self._safe_delete_command(message)
                        else:
                            await self._safe_edit_or_reply(None, message, self.strings("download_failed").format(platform=platform))
                        return
                    
                    # РЕПЛАЙ НА МЕДИА
                    elif content_data.get('type', '').endswith('_media'):
                        media_type = content_data['media_type']
                        file_ext = content_data['file_ext']
                        
                        await utils.answer(message, self.strings("media_reply").format(
                            filename=f"{media_type}.{file_ext}"
                        ))
                        
                        success = await self._handle_reply_media(message, reply, media_type, file_ext)
                        if success:
                            await self._safe_edit_or_reply(None, message, self.strings("reply_success").format(
                                filename=f"{media_type}.{file_ext}",
                                size="Загружено"
                            ))
                            await self._safe_delete_command(message)
                        else:
                            await self._safe_edit_or_reply(None, message, self.strings("not_media"))
                        return

            # ЕСЛИ НЕТ РЕПЛАЯ - ПРОВЕРЯЕМ АРГУМЕНТЫ
            args = utils.get_args_raw(message).strip()
            logger.debug(f"Args: {args}")
            
            if not args:
                # Нет реплая и аргументов - показываем помощь
                await utils.answer(message, self.strings("no_content"))
                await asyncio.sleep(1)
                await utils.answer(message, self.strings("reply_help"))
                return

            # ВАЛИДАЦИЯ URL ИЗ АРГУМЕНТОВ
            is_valid, normalized_url = self._is_valid_url(args)
            if not is_valid:
                await utils.answer(message, self.strings("no_content"))
                return
            else:
                url = normalized_url
                platform = self._detect_platform(url)
                logger.debug(f"Detected platform: {platform}, Fixed URL: {url}")

            # ОПРЕДЕЛЕНИЕ ПЛАТФОРМЫ (если не определено)
            if not platform:
                platform = self._detect_platform(url)

            fixed_url = self._fix_url(url, platform)
            
            if fixed_url != url:
                await utils.answer(message, self.strings("url_fixed"))

            await utils.answer(message, self.strings("source_detected").format(platform=platform))

            # СКАЧИВАНИЕ С АВТОБЛОКОМ КОДА + ПРОГРЕСС
            success, title = await self._download_generic(message, fixed_url, platform)
            
            if success:
                await self._safe_delete_command(message)
                await self._safe_edit_or_reply(None, message, self.strings("success").format(type=f"{platform} (автоблок + прогресс)"))
            else:
                await self._safe_edit_or_reply(None, message, self.strings("download_failed").format(platform=platform))

        except FloodWaitError as e:
            seconds = getattr(e, 'seconds', 60)
            await utils.answer(message, f"⏳ <b>Флуд: {seconds}с</b>")
        except Exception as e:
            error_msg = str(e)[:120]
            logger.error(f"DOMP error: {e}", exc_info=True)
            await self._safe_edit_or_reply(None, message, self.strings("error").format(error_msg))

    @loader.command()
    async def vdfixcmd(self, message: Message):
        """Ручное исправление URL"""
        args = utils.get_args_raw(message).strip()
        if not args:
            await utils.answer(message, "Укажите URL для исправления: <code>.vdfix https://example.com</code>")
            return
        
        is_valid, fixed = self._is_valid_url(args)
        platform = self._detect_platform(fixed if is_valid else args)
        fixed_url = self._fix_url(fixed if is_valid else args, platform)
        
        await utils.answer(message, f"🔧 <b>Оригинал:</b> {args}\n🌐 <b>Платформа:</b> {platform}\n✅ <b>Исправленный:</b> {fixed_url}")

    async def _safe_delete_command(self, message: Message):
        """Безопасное удаление"""
        try:
            if message.out and message.id:
                await asyncio.sleep(1.5)
                await message.delete()
        except MessageNotModifiedError:
            pass
        except Exception:
            pass

    async def _handle_reply_media(self, message: Message, reply: Message, media_type: str, file_ext: str):
        """Обработка медиа реплая"""
        try:
            logger.info(f"→ Reply media: {media_type} ({file_ext})")
            
            # Имя файла
            timestamp = int(asyncio.time.time())
            chat_id = abs(utils.get_chat_id(message))
            
            if media_type == 'video':
                filename = f"{self.download_dir}/reply_video_{chat_id}_{timestamp}.{file_ext}"
            elif media_type == 'gif':
                filename = f"{self.download_dir}/reply_gif_{chat_id}_{timestamp}.gif"
            elif media_type == 'audio':
                filename = f"{self.download_dir}/reply_audio_{chat_id}_{timestamp}.{file_ext}"
            else:
                filename = f"{self.download_dir}/reply_{media_type}_{chat_id}_{timestamp}.{file_ext}"
            
            # Скачивание
            media_path = await reply.download_media(file=filename)
            
            if not media_path or not os.path.exists(media_path):
                return False

            file_size = os.path.getsize(media_path)
            if file_size == 0 or file_size > 50 * 1024 * 1024:
                return False

            self.temp_files.add(media_path)
            
            # Подпись
            base_caption = f"💾 <b>Из реплая</b>\n📁 <b>{os.path.basename(media_path)}</b>\n💾 <b>{self._format_size(file_size)}</b>"
            
            if media_type == 'video' and hasattr(reply, 'video') and reply.video:
                duration = getattr(reply.video, 'duration', 0)
                if duration:
                    base_caption += f"\n⏱ <b>{duration}с</b>"

            # Отправка
            send_kwargs = {
                'file': media_path,
                'caption': base_caption,
                'reply_to': message.reply_to_msg_id
            }
            
            if media_type == 'gif':
                send_kwargs['attributes'] = [DocumentAttributeAnimated()]
            elif media_type in ['audio']:
                send_kwargs['attributes'] = [DocumentAttributeFilename(os.path.basename(media_path))]
            elif media_type == 'video':
                send_kwargs['supports_streaming'] = True

            await self.client.send_file(message.to_id, **send_kwargs)
            return True

        except Exception as e:
            logger.error(f"Reply media error: {e}")
            return False

    def _format_size(self, size: int) -> str:
        """Формат размера (B/KB/MB/GB)"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024**2:
            return f"{size / 1024:.1f} KB"
        elif size < 1024**3:
            return f"{size / (1024**2):.1f} MB"
        else:
            return f"{size / (1024**3):.1f} GB"

    @loader.command()
    async def vdtest(self, message: Message):
        """Тест"""
        version = self.yt_dlp_version or "N/A"
        ffmpeg = "✓" if self.ffmpeg_available else "✗"
        cookies_status = "Опционально" if not self.config["cookies_path"] else "✓"
        status = "✅" if self.yt_dlp_version else "❌"
        
        test_text = self.strings("debug_info").format(
            version=version,
            ffmpeg=ffmpeg,
            cookies_status=cookies_status,
            count="100+",
            status=status
        )
        
        await utils.answer(message, test_text)

    @loader.command()
    async def vdreply(self, message: Message):
        """Помощь по реплаю"""
        await utils.answer(message, self.strings("reply_help"))

    @loader.command()
    async def vdplatforms(self, message: Message):
        """Платформы"""
        await utils.answer(message, self.strings("platforms_list"))

    @loader.command()
    async def vdinstall(self, message: Message):
        """Установка"""
        await utils.answer(message, self.strings("terminal_install"))

    @loader.command()
    async def vdhelp(self, message: Message):
        """Помощь (cookies, установка)"""
        args = utils.get_args_raw(message).strip().lower()
        if 'cookies' in args:
            await utils.answer(message, self.strings("cookies_help"))
        else:
            await utils.answer(message, self.strings("terminal_install"))

    async def _cleanup_temp_files(self):
        """Очистка"""
        for temp_file in list(self.temp_files):
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
            self.temp_files.discard(temp_file)
        
        # Очистка очереди прогресса
        try:
            while not self.progress_queue.empty():
                self.progress_queue.get_nowait()
        except:
            pass

    async def on_unload(self):
        await self._cleanup_temp_files()