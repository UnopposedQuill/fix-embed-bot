# Fix Embed Bot

[![CI](https://github.com/UnopposedQuill/fix-embed-bot/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/UnopposedQuill/fix-embed-bot/actions/workflows/ci.yml)

Uses fxtwitter and similar services to fix the embeds in
Discord.
Additionally, it is designed to store media from the
original message into the server this bot is hosted in.
It is smart enough to avoid redownloading the media
multiple times with some Statistics being extractable.

## Directory Structure
```
fix-embed-bot/
├── bot_with_db.py              # Main bot with database integration
├── database.py                 # Database operations
├── maintenance.py              # Standalone maintenance tasks
├── config.py                   # Configuration (reads from .env)
├── .env                        # Environment variables (not committed)
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Test configuration
├── .pylintrc                   # Linter configuration
├── media_downloads.db          # SQLite database (auto-created)
├── migrations/                 # One-off data migration scripts
├── tests/                      # Automated tests
├── downloaded_media/           # Media organised by date
│   ├── 2026-01-23/
│   │   ├── author_tweetid_0_120000.jpg
│   │   └── ...
│   └── ...
└── exported_media/             # Media exported by tweet author
```

## Getting Started

Copy `.env.example` to `.env` and fill in your Discord token:
```
DISCORD_TOKEN=your_token_here
```

Install dependencies and run the bot:
```bash
pip install -r requirements.txt
python bot_with_db.py
```

## Commands

| Command | Description | Permissions |
|---|---|---|
| `/stats` | Show download statistics (total downloads, storage used, unique users) | Everyone |
| `/recent [limit]` | List the most recent downloads (default: 10) | Everyone |
| `/search <query>` | Search downloads by tweet ID, username, or filename | Everyone |
| `/cleanup` | Remove database records for files no longer on disk | Administrator |
| `/compact` | Scan the channel newest-first, download any unprocessed tweets, and delete older duplicate posts of the same tweet | Manage Messages |

## Running Tests

```bash
pytest
```
