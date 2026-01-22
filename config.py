# config.py
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DOWNLOAD_PATH = "./downloaded_media"
DB_PATH = "media_downloads.db"
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.webp'}
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB Discord limit for fallback