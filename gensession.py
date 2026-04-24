from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# Replace with your values
API_ID = int(input("Enter API ID: "))
API_HASH = input("Enter API HASH: ")

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("✅ Logged in as:", client.session.save())
    print("\nCopy the above string session and use it in your script.")
