# Telegram Downloader Bot

A powerful Telegram bot that downloads files from restricted channels and supports multiple modes: local storage, re-upload to Telegram, and Google Drive upload.

## Features

✨ **Download from restricted channels** - Bypass download restrictions  
📤 **Re-upload to Telegram** - Share files in your saved messages  
☁️ **Google Drive integration** - Direct upload to your Drive  
📋 **Queue system** - Process multiple downloads one by one  
📨 **Forward support** - Forward any message to download  
⚡ **Fast downloads** - 4-7 MB/s speeds with Pyrogram  

## Requirements

- Python 3.10+
- Telegram account
- Google Cloud Project (for Google Drive features)

## Installation

### 1. Clone/Download the project

```bash
git clone <your-repo-url>
cd telegram-downloader-bot
```

### 2. Install dependencies

```bash
pip install pyrogram tgcrypto python-dotenv google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 3. Get Telegram API credentials

1. Go to https://my.telegram.org/auth
2. Login with your phone number
3. Go to "API Development Tools"
4. Create an app and get your `API_ID` and `API_HASH`

### 4. Generate session string

Create `generate_session.py`:

```python
from pyrogram import Client
import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

with app:
    session_string = app.export_session_string()
    print("\nYOUR SESSION STRING:")
    print(session_string)
```

Run it:
```bash
python generate_session.py
```

### 5. Setup Google Drive (Optional)

1. Go to https://console.cloud.google.com/
2. Create a new project
3. Enable "Google Drive API"
4. Create OAuth credentials (Desktop app)
5. Download `credentials.json` and place it in the project folder

### 6. Create `.env` file

```env
API_ID=your_api_id
API_HASH=your_api_hash
STRING_SESSION=your_session_string
ALLOWED_USERS=your_user_id
GDRIVE_FOLDER_ID=optional_folder_id
```

To get your user ID, send any message to [@userinfobot](https://t.me/userinfobot) on Telegram.

## Usage

### Start the bot

```bash
python saverestrict.py
```

### Commands

- `/start` - Start the bot
- `/help` - Show help message
- `/get <link>` - Download from Telegram link
- `/mode <type>` - Change mode (download/default/gdrive)
- `/queue` - View current queue
- `/clear` - Clear queue
- `/dialogs` - List your accessible chats

### Modes

**1. Download Mode** (💾)
```
/mode download
```
- Downloads files to local disk
- Files saved in `downloads/` folder

**2. Default Mode** (📤)
```
/mode default
```
- Downloads and re-uploads to Telegram
- Deletes local file after upload
- This is the default mode when bot starts

**3. Google Drive Mode** (☁️)
```
/mode gdrive
```
- Downloads file
- Asks: "Drive Only" or "Drive + Local"
- Uploads to Google Drive

### Two Ways to Download

**Method 1: Using links**
```
/get https://t.me/channelname/123
```

**Method 2: Forward messages**
- Forward any message with media to the bot
- Bot automatically downloads it

## Examples

### Download to local disk
```
/mode download
/get https://t.me/c/1234567890/123
```

### Re-upload to Telegram
```
/mode default
/get https://t.me/c/1234567890/123
```

### Upload to Google Drive
```
/mode gdrive
/get https://t.me/c/1234567890/123
[Bot asks: 1 or 2]
1  (Drive Only)
```

### Forward messages
```
/mode default
[Forward any message to the bot]
```

## Queue System

The bot processes files **one by one** for maximum speed:

```
/get <link1>
/get <link2>
/get <link3>

Bot: 📋 Added to queue (Position 2)
Bot: 📋 Added to queue (Position 3)
```

View queue:
```
/queue
```

Clear queue:
```
/clear
```

## Troubleshooting

### "AUTH_KEY_UNREGISTERED" error
Your session expired. Generate a new session string:
```bash
python generate_session.py
```

### "credentials.json not found"
Google Drive features won't work without it. Either:
- Setup Google Drive credentials
- Use `/mode download` or `/mode default` instead

### Slow download speeds
Check:
- Your internet connection
- Try different times of day
- Telegram's server location affects speed

### "Cannot access message"
Make sure:
- You're a member of the channel/chat
- The message ID is correct
- Use `/dialogs` to verify chat IDs

## File Structure

```
telegram-downloader-bot/
├── saverestrict.py          # Main bot file
├── generate_session.py      # Session generator
├── .env                     # Configuration
├── credentials.json         # Google Drive credentials (optional)
├── token.pickle            # Google Drive token (auto-generated)
├── downloads/              # Downloaded files folder
├── bot.log                 # Bot logs
└── README.md               # This file
```

## Notes

- Bot only works for users listed in `ALLOWED_USERS`
- Downloads are processed one at a time for best speed
- Videos are uploaded as streamable (not documents)
- All original metadata is preserved
- Local files are auto-deleted after upload (except in download mode)

## Support

If you encounter issues:
1. Check the `bot.log` file for errors
2. Make sure all dependencies are installed
3. Verify your `.env` configuration
4. Ensure your session string is valid

## License

This project is for personal use only. Respect Telegram's Terms of Service and don't use it for illegal activities.

---

**Made with ❤️ using Pyrogram**