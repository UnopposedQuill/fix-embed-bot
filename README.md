# Fix Embed Bot

Uses fxtwitter and similar services to fix the embeds in
Discord.
Additionally, it is designed to store media from the
original message into the server this bot is hosted in.
It is smart enough to avoid redownloading the media
multiple times with some Statistics being extractable.

# Directory Structure
discord-media-bot/
├── bot_with_db.py          # Main bot with database
├── database.py            # Database operations
├── config.py             # Configuration
├── .env                  # Environment variables
├── requirements.txt      # Updated dependencies
├── media_downloads.db    # SQLite database (auto-created)
└── downloaded_media/     # Organized downloads
    ├── 2024-01-18/
    │   └── 123/
    │       └── 1234567890_0_180102_image.jpg
    ├── 2024-01-19/
    └── ...

# Getting started

Run `pip install -r requirements.txt` to install the bot's
dependencies.

Execute the bot with `python bot_with_db.py`
