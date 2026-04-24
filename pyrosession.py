from pyrogram import Client
import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')

# This will ask for your phone number and verification code
app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

with app:
    session_string = app.export_session_string()
    print("\n" + "="*50)
    print("YOUR PYROGRAM SESSION STRING:")
    print("="*50)
    print(session_string)
    print("="*50)
    print("\nCopy this and replace STRING_SESSION in your .env file")