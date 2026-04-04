# config.py
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
# Optional: set to your server's ID for instant slash command sync during development.
# Leave unset (or remove from .env) to use global sync (can take up to 1 hour).
DEV_GUILD_ID = int(os.getenv("DEV_GUILD_ID")) if os.getenv("DEV_GUILD_ID") else None
DOWNLOAD_PATH = "./downloaded_media"
DB_PATH = "media_downloads.db"
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.mp4', '.mov', '.webp'}
MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB Discord limit for fallback
