import re
import os
import asyncio
import time
import logging
from collections import deque
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton
from pyrogram.errors import FloodWait
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('STRING_SESSION', '')
ALLOWED_USERS = list(map(int, os.getenv("ALLOWED_USERS", "").split(",")))
GDRIVE_FOLDER_ID = os.getenv('GDRIVE_FOLDER_ID', '')  # Optional: specific folder

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Google Drive scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Initialize client
if SESSION_STRING and len(SESSION_STRING) > 100:
    app = Client(
        "telegram_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        sleep_threshold=0,
        workers=4
    )
else:
    app = Client(
        "telegram_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        sleep_threshold=0,
        workers=4
    )

# Regex for Telegram links
LINK_REGEX = re.compile(r'/get\s+(?:https?://)?t(?:elegram)?\.me/(?:c/)?([^/\s]+)(?:/(\d+))?/(\d+)')

# Global state
user_modes = {}  # Default mode for each user
user_queues = {}  # Queue for each user
processing_users = set()  # Users currently processing
pending_gdrive_downloads = {}  # Store pending gdrive download info

# Google Drive service
gdrive_service = None


def format_size(size):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def get_gdrive_service():
    """Initialize Google Drive service."""
    global gdrive_service
    if gdrive_service:
        return gdrive_service
    
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("credentials.json not found. Google Drive features disabled.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    gdrive_service = build('drive', 'v3', credentials=creds)
    return gdrive_service


async def upload_to_gdrive(file_path, file_name):
    """Upload file to Google Drive."""
    try:
        service = get_gdrive_service()
        if not service:
            return False, "Google Drive not configured"
        
        file_metadata = {'name': file_name}
        if GDRIVE_FOLDER_ID:
            file_metadata['parents'] = [GDRIVE_FOLDER_ID]
        
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        logger.info(f"Uploaded to Google Drive: {file_name} (ID: {file.get('id')})")
        return True, file.get('id')
    except Exception as e:
        logger.error(f"Google Drive upload error: {e}")
        return False, str(e)


async def download_file(message: Message, file_path: str, file_name: str, event: Message, max_retries: int = 3):
    """Download file with progress tracking and retry logic."""
    progress_msg = await event.reply(f"📥 Downloading: `{file_name}`")
    
    for attempt in range(max_retries):
        try:
            file_size = 0
            if message.document:
                file_size = message.document.file_size
            elif message.video:
                file_size = message.video.file_size
            elif message.audio:
                file_size = message.audio.file_size
            elif message.photo:
                file_size = message.photo.file_size
            
            if attempt > 0:
                logger.info(f"Retry {attempt + 1}/{max_retries}: {file_name}")
                await progress_msg.edit(f"🔄 Retrying... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(2)
            
            start_time = time.time()
            downloaded = [0]
            last_update = [time.time()]
            
            async def progress(current, total):
                downloaded[0] = current
                now = time.time()
                
                if now - last_update[0] >= 3:
                    elapsed = now - start_time
                    speed = current / elapsed if elapsed > 0 else 0
                    eta = (total - current) / speed if speed > 0 else 0
                    percent = (current / total) * 100 if total > 0 else 0
                    
                    status = (
                        f"📥 **Downloading**\n"
                        f"📄 `{file_name}`\n"
                        f"📊 {percent:.1f}% • {format_size(current)} / {format_size(total)}\n"
                        f"⚡ {format_size(speed)}/s • ⏱ {int(eta)}s"
                    )
                    
                    try:
                        await progress_msg.edit(status)
                    except:
                        pass
                    
                    last_update[0] = now
            
            await asyncio.wait_for(
                message.download(file_name=file_path, progress=progress),
                timeout=3600
            )
            
            total_time = time.time() - start_time
            avg_speed = downloaded[0] / total_time if total_time > 0 else 0
            
            result = (
                f"✅ **Download Complete**\n\n"
                f"📁 **File:** `{file_name}`\n"
                f"💾 **Size:** {format_size(downloaded[0])}\n"
                f"⚡ **Speed:** {format_size(avg_speed)}/s\n"
                f"⏱️ **Time:** {total_time:.1f}s"
            )
            
            await progress_msg.edit(result)
            logger.info(f"Downloaded: {file_name} ({format_size(avg_speed)}/s)")
            return file_path, progress_msg
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout: {file_name} (attempt {attempt + 1})")
            if attempt < max_retries - 1:
                await progress_msg.edit(f"⏱ Timeout. Retrying in 3s... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(3)
            else:
                await progress_msg.edit(f"❌ Download failed after {max_retries} attempts")
                return None, progress_msg
                
        except FloodWait as e:
            logger.warning(f"FloodWait: {e.value}s")
            await progress_msg.edit(f"⏳ Rate limited. Waiting {e.value}s...")
            await asyncio.sleep(e.value)
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(3)
            else:
                await progress_msg.edit(f"❌ Error: `{str(e)}`")
                return None, progress_msg
    
    return None, progress_msg


async def upload_file(chat_id: int, file_path: str, caption: str, event: Message, original_msg: Message):
    """Upload file with progress tracking, preserving original media type."""
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    progress_msg = await event.reply(f"📤 **Uploading to Telegram**\n📄 `{file_name}`")
    
    start_time = time.time()
    uploaded = [0]
    last_update = [time.time()]
    
    async def progress(current, total):
        uploaded[0] = current
        now = time.time()
        
        if now - last_update[0] >= 3:
            elapsed = now - start_time
            speed = current / elapsed if elapsed > 0 else 0
            eta = (total - current) / speed if speed > 0 else 0
            percent = (current / total) * 100
            
            status = (
                f"📤 **Uploading to Telegram**\n\n"
                f"📄 **File:** `{file_name}`\n"
                f"📊 **Progress:** {percent:.1f}%\n"
                f"💾 **Uploaded:** {format_size(current)} / {format_size(total)}\n"
                f"⚡ **Speed:** {format_size(speed)}/s\n"
                f"⏱️ **ETA:** {int(eta)}s"
            )
            
            try:
                await progress_msg.edit(status)
            except:
                pass
            
            last_update[0] = now
    
    try:
        if original_msg.video:
            video = original_msg.video
            await app.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=caption,
                duration=video.duration or 0,
                width=video.width or 0,
                height=video.height or 0,
                supports_streaming=True,
                progress=progress
            )
        elif original_msg.audio:
            audio = original_msg.audio
            await app.send_audio(
                chat_id=chat_id,
                audio=file_path,
                caption=caption,
                duration=audio.duration or 0,
                performer=audio.performer or None,
                title=audio.title or None,
                progress=progress
            )
        elif original_msg.photo:
            await app.send_photo(
                chat_id=chat_id,
                photo=file_path,
                caption=caption,
                progress=progress
            )
        else:
            await app.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=caption,
                progress=progress
            )
        
        total_time = time.time() - start_time
        avg_speed = file_size / total_time if total_time > 0 else 0
        
        result = (
            f"✅ **Upload Complete**\n\n"
            f"📁 **File:** `{file_name}`\n"
            f"💾 **Size:** {format_size(file_size)}\n"
            f"⚡ **Speed:** {format_size(avg_speed)}/s\n"
            f"⏱️ **Time:** {total_time:.1f}s"
        )
        
        await progress_msg.edit(result)
        logger.info(f"Uploaded: {file_name}")
        
    except FloodWait as e:
        await progress_msg.edit(f"⏳ **Rate Limited**\n\n⏰ Waiting {e.value}s...")
        await asyncio.sleep(e.value)
        return await upload_file(chat_id, file_path, caption, event, original_msg)
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await progress_msg.edit(f"❌ **Upload Failed**\n\n```{str(e)}```")


async def process_queue_item(user_id: int, queue_item: dict):
    """Process a single queue item."""
    event = queue_item['event']
    mode = queue_item['mode']
    
    file_path = None
    original_msg = None
    
    try:
        # Check if it's a forwarded message or link-based
        if 'forward_msg' in queue_item:
            # Forwarded message
            msg = queue_item['forward_msg']
            msg_id = msg.id
            
            if not msg.media:
                await event.reply("❌ **No Media Found**\n\nThis message doesn't contain any downloadable media")
                return
            
            original_msg = msg
            caption = msg.caption or ""
            
            if msg.document:
                file_name = msg.document.file_name or f"document_{msg_id}"
            elif msg.video:
                file_name = msg.video.file_name or f"video_{msg_id}.mp4"
            elif msg.audio:
                file_name = msg.audio.file_name or f"audio_{msg_id}.mp3"
            elif msg.photo:
                file_name = f"photo_{msg_id}.jpg"
            else:
                file_name = f"file_{msg_id}"
            
            file_path = os.path.join(DOWNLOAD_FOLDER, file_name)
            
            # Download
            result = await download_file(msg, file_path, file_name, event)
            if not result[0]:
                return
            
            file_path = result[0]
            
        else:
            # Link-based download (existing code)
            chat_id = queue_item['chat_id']
            msg_id = queue_item['msg_id']
            
            # Get message
            msg = None
            if chat_id.isdigit():
                chat_id_with_prefix = int(f"-100{chat_id}")
                try:
                    msg = await app.get_messages(chat_id_with_prefix, msg_id)
                except:
                    try:
                        msg = await app.get_messages(int(chat_id), msg_id)
                    except:
                        pass
            else:
                try:
                    msg = await app.get_messages(chat_id, msg_id)
                except:
                    pass
            
            if not msg:
                await event.reply("❌ **Cannot Access Message**\n\nUse `/dialogs` to verify chat ID")
                return
            
            if not msg.media:
                await event.reply("❌ **No Media Found**\n\nThis message doesn't contain any downloadable media")
                return
            
            original_msg = msg
            caption = msg.caption or ""
            
            if msg.document:
                file_name = msg.document.file_name or f"document_{msg_id}"
            elif msg.video:
                file_name = msg.video.file_name or f"video_{msg_id}.mp4"
            elif msg.audio:
                file_name = msg.audio.file_name or f"audio_{msg_id}.mp3"
            elif msg.photo:
                file_name = f"photo_{msg_id}.jpg"
            else:
                file_name = f"file_{msg_id}"
            
            file_path = os.path.join(DOWNLOAD_FOLDER, file_name)
            
            # Download
            result = await download_file(msg, file_path, file_name, event)
            if not result[0]:
                return
            
            file_path = result[0]
        
        # Handle based on mode
        if mode == "download":
            logger.info(f"File saved: {file_path}")
            await event.reply(
                f"✅ **Saved to Local Disk**\n\n"
                f"📁 **Location:** `{file_path}`\n"
                f"💾 **Size:** {format_size(os.path.getsize(file_path))}"
            )
            
        elif mode == "default":
            await upload_file(event.chat.id, file_path, caption, event, original_msg)
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
        
        elif mode == "gdrive":
            # Get the keep_local choice
            keep_local = queue_item.get('keep_local', False)
            
            # Upload to Google Drive
            progress_msg = await event.reply(
                f"☁️ **Uploading to Google Drive**\n\n"
                f"📄 **File:** `{file_name}`\n"
                f"⏳ Please wait..."
            )
            success, result = await upload_to_gdrive(file_path, file_name)
            
            if success:
                final_msg = (
                    f"✅ **Google Drive Upload Complete**\n\n"
                    f"📁 **File:** `{file_name}`\n"
                    f"💾 **Size:** {format_size(os.path.getsize(file_path))}\n"
                    f"☁️ **Drive ID:** `{result}`"
                )
                
                if keep_local:
                    final_msg += f"\n📂 **Also saved to:** `{file_path}`"
                    logger.info(f"File saved: {file_path}")
                else:
                    final_msg += f"\n🗑️ **Local file deleted**"
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Cleaned up: {file_path}")
                
                await progress_msg.edit(final_msg)
            else:
                await progress_msg.edit(
                    f"❌ **Google Drive Upload Failed**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"⚠️ **Error:** `{result}`\n\n"
                    f"💾 File saved locally: `{file_path}`"
                )
    
    except Exception as e:
        logger.error(f"Process error: {e}")
        await event.reply(f"❌ Error: `{str(e)}`")


async def process_queue(user_id: int):
    """Process queue for a specific user."""
    if user_id in processing_users:
        return
    
    processing_users.add(user_id)
    
    try:
        while user_id in user_queues and len(user_queues[user_id]) > 0:
            queue_item = user_queues[user_id].popleft()
            
            remaining = len(user_queues[user_id])
            if remaining > 0:
                try:
                    await queue_item['event'].reply(
                        f"⏳ **Processing Queue**\n\n"
                        f"📊 {remaining} file(s) remaining"
                    )
                except:
                    pass
            
            await process_queue_item(user_id, queue_item)
        
        # Queue complete
        if user_id in user_queues:
            del user_queues[user_id]
    
    finally:
        processing_users.discard(user_id)


# Command handlers
@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return await message.reply("❌ **Unauthorized Access**")
    
    # Set default mode
    user_modes[message.from_user.id] = "default"
    
    welcome_msg = (
        "🤖 **Telegram Downloader Bot**\n\n"
        "✨ **Features:**\n"
        "📥 Download from restricted channels\n"
        "📤 Re-upload to Telegram\n"
        "☁️ Upload to Google Drive\n"
        "📋 Queue system for multiple files\n"
        "📨 Forward messages to download\n\n"
        "🎯 **Current Mode:** `default`\n\n"
        "Use /help to see all commands"
    )
    
    await message.reply(welcome_msg)


@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    help_text = (
        "📚 **Commands Guide**\n\n"
        "**Download:**\n"
        "`/get <link>` - Download from Telegram link\n"
        "**OR**\n"
        "Forward any message with media to the bot\n\n"
        "**Queue Management:**\n"
        "`/queue` - 📋 View current queue\n"
        "`/clear` - 🗑️ Clear entire queue\n\n"
        "**Settings:**\n"
        "`/mode <type>` - 🎯 Change download mode\n"
        "`/dialogs` - 📱 List your chats\n\n"
        "**Modes:**\n"
        "• `download` - 💾 Save to local disk only\n"
        "• `default` - 📤 Download + upload to Telegram\n"
        "• `gdrive` - ☁️ Upload to Google Drive\n\n"
        "**Tips:**\n"
        "• Forward messages from personal chats\n"
        "• Use `/dialogs` to find chat IDs\n"
        "• Queue processes files one by one\n"
        "• All modes preserve original quality"
    )
    
    await message.reply(help_text)


@app.on_message(filters.command("mode") & filters.private)
async def set_mode(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    try:
        mode = message.text.split()[1].lower()
        if mode not in ["download", "default", "gdrive"]:
            return await message.reply(
                "❌ **Invalid Mode**\n\n"
                "Available modes:\n"
                "• `download` - 💾 Local disk\n"
                "• `default` - 📤 Telegram\n"
                "• `gdrive` - ☁️ Google Drive"
            )
        
        user_modes[message.from_user.id] = mode
        
        mode_emojis = {
            "download": "💾",
            "default": "📤",
            "gdrive": "☁️"
        }
        
        mode_names = {
            "download": "Local Disk",
            "default": "Telegram Upload",
            "gdrive": "Google Drive"
        }
        
        await message.reply(
            f"✅ **Mode Changed**\n\n"
            f"{mode_emojis[mode]} **{mode_names[mode]}**"
        )
    except IndexError:
        await message.reply(
            "⚠️ **Usage:**\n"
            "`/mode <download|default|gdrive>`"
        )


@app.on_message(filters.command("get") & filters.private)
async def handle_get(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    match = LINK_REGEX.search(message.text)
    if not match:
        return await message.reply("❌ Invalid link. Usage: `/get <telegram_link>`")
    
    chat_id, _, msg_id = match.groups()
    user_id = message.from_user.id
    mode = user_modes.get(user_id, "default")
    
    # For gdrive mode, ask for text reply
    if mode == "gdrive":
        # Store the download info for later
        pending_gdrive_downloads[user_id] = {
            'chat_id': chat_id,
            'msg_id': int(msg_id),
            'event': message
        }
        
        await message.reply(
            "📁 **Where do you want to save?**\n\n"
            "Reply with:\n"
            "**1** - Drive Only\n"
            "**2** - Drive + Local"
        )
        return
    
    # For other modes, proceed immediately
    if user_id not in user_queues:
        user_queues[user_id] = deque()
    
    queue_item = {
        'chat_id': chat_id,
        'msg_id': int(msg_id),
        'event': message,
        'mode': mode
    }
    
    user_queues[user_id].append(queue_item)
    
    position = len(user_queues[user_id])
    if position == 1:
        await message.reply(
            f"🚀 **Starting Download**\n"
            f"📊 Position: 1/1"
        )
        asyncio.create_task(process_queue(user_id))
    else:
        await message.reply(
            f"📋 **Added to Queue**\n"
            f"📊 Position: {position}\n"
            f"⏳ {position - 1} file(s) ahead"
        )


# Handler for forwarded messages
@app.on_message(filters.forwarded & filters.private & filters.media)
async def handle_forward(client, message: Message):
    """Handle forwarded messages with media."""
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    user_id = message.from_user.id
    mode = user_modes.get(user_id, "default")
    
    # For gdrive mode, ask for choice
    if mode == "gdrive":
        # Generate a unique ID for this forwarded message
        forward_id = f"fwd_{int(time.time())}"
        
        pending_gdrive_downloads[user_id] = {
            'forward_msg': message,
            'forward_id': forward_id
        }
        
        await message.reply(
            "📁 **Where do you want to save?**\n\n"
            "Reply with:\n"
            "**1** - Drive Only\n"
            "**2** - Drive + Local"
        )
        return
    
    # For other modes, process immediately
    if user_id not in user_queues:
        user_queues[user_id] = deque()
    
    queue_item = {
        'forward_msg': message,
        'event': message,
        'mode': mode
    }
    
    user_queues[user_id].append(queue_item)
    
    position = len(user_queues[user_id])
    if position == 1:
        await message.reply(
            f"🚀 **Starting Download**\n"
            f"📊 Position: 1/1"
        )
        asyncio.create_task(process_queue(user_id))
    else:
        await message.reply(
            f"📋 **Added to Queue**\n"
            f"📊 Position: {position}\n"
            f"⏳ {position - 1} file(s) ahead"
        )


# Handler for gdrive text replies
@app.on_message(filters.private & filters.text & ~filters.command(["start", "help", "mode", "get", "queue", "clear", "dialogs"]))
async def handle_gdrive_choice(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Check if user has a pending gdrive download
    if user_id not in pending_gdrive_downloads:
        return
    
    # Check if it's a valid choice (1 or 2)
    if text not in ["1", "2"]:
        await message.reply("❌ Invalid choice. Please reply with **1** or **2**")
        return
    
    # Get the stored download info
    download_info = pending_gdrive_downloads[user_id]
    del pending_gdrive_downloads[user_id]
    
    keep_local = (text == "2")  # 2 = Drive + Local
    choice_text = "☁️ Drive Only" if not keep_local else "💾 Drive + Local"
    
    await message.reply(
        f"✅ **Choice Confirmed**\n\n"
        f"{choice_text}"
    )
    
    # Add to queue
    if user_id not in user_queues:
        user_queues[user_id] = deque()
    
    # Check if it's a forwarded message or a link
    if 'forward_msg' in download_info:
        # Forwarded message
        queue_item = {
            'forward_msg': download_info['forward_msg'],
            'event': download_info['forward_msg'],
            'mode': 'gdrive',
            'keep_local': keep_local
        }
    else:
        # Link-based download
        queue_item = {
            'chat_id': download_info['chat_id'],
            'msg_id': download_info['msg_id'],
            'event': download_info['event'],
            'mode': 'gdrive',
            'keep_local': keep_local
        }
    
    user_queues[user_id].append(queue_item)
    
    position = len(user_queues[user_id])
    if position == 1:
        await message.reply(f"📥 **Starting Download...**")
        asyncio.create_task(process_queue(user_id))
    else:
        await message.reply(
            f"📋 **Added to Queue**\n"
            f"📊 Position: {position}"
        )


@app.on_callback_query()
async def handle_callback(client, callback: CallbackQuery):
    # Keep this for compatibility
    if callback.from_user.id not in ALLOWED_USERS:
        return
    
    await callback.answer("Please reply with text")


@app.on_message(filters.command("queue") & filters.private)
async def show_queue(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    user_id = message.from_user.id
    if user_id not in user_queues or len(user_queues[user_id]) == 0:
        return await message.reply("✅ **Queue is Empty**")
    
    queue_list = []
    for idx, item in enumerate(user_queues[user_id], 1):
        mode_emoji = {"download": "💾", "default": "📤", "gdrive": "☁️"}
        emoji = mode_emoji.get(item['mode'], "📄")
        
        # Check if it's a forwarded message or link
        if 'forward_msg' in item:
            queue_list.append(f"{idx}. {emoji} Forwarded message")
        else:
            queue_list.append(f"{idx}. {emoji} Message ID: `{item['msg_id']}`")
    
    queue_msg = (
        f"📋 **Current Queue**\n\n"
        f"📊 **Total:** {len(queue_list)} file(s)\n\n"
        + "\n".join(queue_list)
    )
    
    await message.reply(queue_msg)


@app.on_message(filters.command("clear") & filters.private)
async def clear_queue(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    user_id = message.from_user.id
    if user_id in user_queues:
        count = len(user_queues[user_id])
        del user_queues[user_id]
        await message.reply(
            f"🗑️ **Queue Cleared**\n\n"
            f"📊 Removed {count} file(s)"
        )
    else:
        await message.reply("✅ **Queue is Already Empty**")


@app.on_message(filters.command("dialogs") & filters.private)
async def show_dialogs(client, message: Message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    await message.reply("🔍 **Fetching your chats...**")
    
    try:
        dialogs = []
        async for dialog in app.get_dialogs(limit=30):
            chat = dialog.chat
            chat_type = "👤" if chat.type.name == "PRIVATE" else "👥" if chat.type.name == "GROUP" else "📢"
            dialogs.append(
                f"{chat_type} **{chat.title or chat.first_name or 'Unknown'}**\n"
                f"🆔 `{chat.id}`"
            )
        
        if dialogs:
            result = "📱 **Your Chats**\n\n" + "\n\n".join(dialogs)
            await message.reply(result)
        else:
            await message.reply("❌ **No chats found**")
    except Exception as e:
        await message.reply(f"❌ **Error:** `{e}`")


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("🤖 Telegram Downloader Bot Started")
    logger.info("⚡ Powered by Pyrogram")
    logger.info("🎯 Default Mode: Download + Upload to Telegram")
    logger.info("=" * 50)
    app.run()