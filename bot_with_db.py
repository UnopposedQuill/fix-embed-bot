# bot_with_db.py
import os
import re
import traceback
from datetime import datetime
from functools import reduce

import discord
import requests
from discord import app_commands

from config import DISCORD_TOKEN, DOWNLOAD_PATH
from database import MediaDatabase

# Initialize database
db = MediaDatabase()

# Create download directory with organization
def download_subpath():
    """Organize files by date"""
    today = datetime.now().strftime("%Y-%m-%d")
    daily_path = os.path.join(DOWNLOAD_PATH, today)
    os.makedirs(daily_path, exist_ok=True)
    return daily_path

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Regex to detect Twitter/X URLs in user messages
TWITTER_REGEX = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com)/(?:\w+)/status/(\d+)'
)

# Broader regex that also covers fxtwitter bot-posted messages
TWITTER_URL_REGEX = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com|fxtwitter\.com)/\w+/status/(\d+)'
)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

    # Create necessary directories
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)

    # Create unique_users table if it doesn't exist
    with db.get_cursor() as cursor:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS unique_users (
                user_id TEXT PRIMARY KEY
            )
        ''')

    await tree.sync()
    print('Slash commands synced.')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    matches = TWITTER_REGEX.findall(message.content)

    if matches:
        for tweet_id in matches:
            await process_tweet_with_db(message, tweet_id)

async def process_tweet_with_db(message, tweet_id):
    """Process tweet with database tracking"""
    fx_url = f"https://fxtwitter.com/i/status/{tweet_id}"

    # Attempt to remove original message, leave only the bot's
    await delete_message(message)

    # Check for duplicates
    if db.is_tweet_downloaded(tweet_id):
        print(f"⚠️ Tweet {tweet_id} already downloaded, skipping...")
        # Optional: Still post the link but don't re-download

        await message.channel.send(
            f"📋 Already downloaded: {fx_url}\n"
            f"(Originally downloaded from this tweet)"
        )
        return

    try:
        # Send fxtwitter link first
        await message.channel.send(f"📥 Media from {message.author}: {fx_url}")

        # Download media
        downloaded_files = await download_media_with_tracking(tweet_id)

        # Finally, record in database
        if downloaded_files:
            total_size = sum(os.path.getsize(f['path']) for f in downloaded_files)

            db.record_download(
                tweet_id=tweet_id,
                tweet_url=f"https://twitter.com/i/status/{tweet_id}",
                discord_user=message.author,
                discord_channel=message.channel,
                file_size=total_size,
                media_count=len(downloaded_files),
                download_path=downloaded_files[0]['path'] if downloaded_files else None,
                tweet_author_id=downloaded_files[0]['tweet_author_id']
            )

            # Record individual files
            for file_info in downloaded_files:
                db.add_media_file(
                    tweet_id=tweet_id,
                    file_name=file_info['name'],
                    file_path=file_info['path'],
                    file_size=file_info['size'],
                    file_type=file_info['type'],
                    download_url=file_info.get('url')
                )

            print(f"✅ Successfully downloaded {len(downloaded_files)} file(s) ({total_size / 1024 / 1024:.2f} MB)")
    except Exception as e:
        print(f"❌ Error processing tweet {tweet_id}: {e}")


async def delete_message(message):
    # Attempt to remove original message, leave only the bot's
    if message.guild and message.channel.permissions_for(message.guild.me).manage_messages:
        try:
            await message.delete()
            print(f"🗑️ Successfully deleted original message {message.id}.")
        except discord.NotFound:
            print(f"ℹ️ Original message {message.id} was already deleted.")
        except discord.Forbidden:
            # This should not happen if the check passed, but it's a safe fallback
            print(f"⚠️ Unexpectedly lacked permission to delete message {message.id}.")
        except Exception as e:
            print(f"⚠️ Other error deleting message: {e}")
    else:
        # The bot does not have the 'Manage Messages' permission here
        print(f"❌ Cannot delete in #{message.channel}. Bot lacks 'Manage Messages' permission.")
        # TODO: Send a temporary error (e.g., to a log channel you plan to create)
        # await message.channel.send("⚠️ Need 'Manage Messages' to clean up.", delete_after=5)


async def download_media_with_tracking(tweet_id):
    """Download media with enhanced tracking"""
    def dig(obj, *keys, default=None):
        try:
            return reduce(lambda d, k: d[k], keys, obj)
        except (KeyError, TypeError):
            return default
    downloaded_files = []

    try:
        # Use FxTwitter API
        api_url = f"https://api.fxtwitter.com/status/{tweet_id}"
        print(f"🔍 Fetching tweet {tweet_id} from FxTwitter API...")

        response = requests.get(api_url, timeout=15)

        if response.status_code != 200:
            print(f"❌ API Error: Status {response.status_code}")
            return downloaded_files

        data = response.json()

        # Extract tweet data. If these fields are not present, there is no media.
        media_data = dig(data, 'tweet', 'media', 'all')
        if not media_data:
            print("ℹ️ No media found in tweet")
            return downloaded_files
        print(f"📥 Found {len(media_data)} media item(s)")

        author_info = dig(data, 'tweet', 'author')
        author_id = author_info.get('id')  # Twitter's numeric user ID
        author_screen_name = author_info.get('screen_name')
        author_display_name = author_info.get('name')

        if author_id and author_screen_name:
            # Insert or ignore duplicate author
            db.insert_or_update_author(author_id, author_screen_name, author_display_name)
            # Store the author's database ID for later use when recording download
            author_db_id = db.get_author_id(author_id)
        else:
            author_db_id = None

        # Get the download directory
        download_dir = download_subpath()

        # Download each media item
        for i, media_item in enumerate(media_data):
            try:
                # Determine media type and URL
                media_type = media_item.get('type', '')
                media_url = None

                if media_type == 'photo' or 'url' in media_item:
                    # Photos have direct URL
                    media_url = media_item.get('url')
                elif media_type in ('video', 'gif'):
                    # Videos/GIFs might have variants
                    variants = media_item.get('variants', [])
                    if variants:
                        # Get the highest quality video (mp4 preferably)
                        mp4_variants = [v for v in variants if v.get('type') == 'video/mp4']
                        if mp4_variants:
                            # Get the one with the highest bitrate or quality
                            best_variant = max(mp4_variants,
                                               key=lambda x: x.get('bitrate', 0))
                            media_url = best_variant.get('url')
                        elif variants:
                            # Fallback to first variant
                            media_url = variants[0].get('url')

                if not media_url:
                    print(f"⚠️ Could not find URL for media item {i}")
                    continue

                print(f"⬇️ Downloading item {i + 1}: {media_url[:80]}...")

                # Determine file extension
                if '?' in media_url:
                    media_url_clean = media_url.split('?')[0]
                else:
                    media_url_clean = media_url

                # Try to get extension from URL
                file_extension = os.path.splitext(media_url_clean)[1]

                # If no extension in URL, guess from content type or media type
                if not file_extension:
                    if media_type == 'video':
                        file_extension = '.mp4'
                    elif media_type == 'gif':
                        file_extension = '.mp4'  # Twitter GIFs are actually MP4
                    else:
                        file_extension = '.jpg'

                # Create filename
                timestamp = datetime.now().strftime("%H%M%S")
                author_prefix = author_screen_name or "unknown"
                filename = f"{author_prefix}_{tweet_id}_{i}_{timestamp}{file_extension}"
                filepath = os.path.join(download_dir, filename)

                # Download the file
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                with requests.get(media_url, headers=headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    total_size = 0

                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                total_size += len(chunk)

                    # Verify file was downloaded
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        print(f"✅ Downloaded: {filename} ({total_size / 1024:.1f} KB)")

                        downloaded_files.append({
                            'name': filename,
                            'path': filepath,
                            'size': total_size,
                            'type': media_type,
                            'url': media_url,
                            'index': i,
                            'tweet_author_id': author_db_id,
                        })
                    else:
                        print(f"❌ Failed to save file: {filename}")

            except Exception as e:
                print(f"❌ Error downloading media item {i}: {e}")
                continue

        return downloaded_files

    except requests.exceptions.Timeout:
        print(f"❌ Timeout fetching tweet {tweet_id}")
        return downloaded_files
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error for tweet {tweet_id}: {e}")
        return downloaded_files
    except Exception as e:
        print(f"❌ Unexpected error processing tweet {tweet_id}: {e}")
        traceback.print_exc()
        return downloaded_files

@tree.command(name="stats", description="Show download statistics.")
async def show_stats(interaction: discord.Interaction):
    """Display download statistics"""
    stats = db.get_download_stats()

    embed = discord.Embed(
        title="📊 Media Download Statistics",
        color=discord.Color.blue()
    )

    size_mb = stats['total_size'] / 1024 / 1024

    embed.add_field(
        name="Total Downloads",
        value=f"**{stats['total_downloads']}** tweets",
        inline=True
    )

    embed.add_field(
        name="Storage Used",
        value=f"**{size_mb:.2f} MB**",
        inline=True
    )

    embed.add_field(
        name="Unique Users",
        value=f"**{stats['unique_users']}** users",
        inline=True
    )

    recent_downloads = db.get_recent_downloads(5)
    if recent_downloads:
        recent_text = "\n".join(
            f"• `{row['tweet_id'][:8]}...` by {row['discord_username']}"
            for row in recent_downloads
        )
        embed.add_field(
            name="Recent Downloads",
            value=recent_text,
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@tree.command(name="recent", description="List the most recent downloads.")
@app_commands.describe(limit="Number of entries to show (default 10)")
async def show_recent(interaction: discord.Interaction, limit: int = 10):
    """Show recent downloads"""
    recent = db.get_recent_downloads(limit)

    if not recent:
        await interaction.response.send_message("No downloads found.")
        return

    embed = discord.Embed(
        title="🕐 Recent Downloads",
        color=discord.Color.green()
    )

    for i, row in enumerate(recent, 1):
        embed.add_field(
            name=f"{i}. Tweet {row['tweet_id'][:8]}...",
            value=(
                f"👤 {row['discord_username']}\n"
                f"📅 {row['created_at'][:16]}\n"
                f"📁 {row['file_count'] or 0} files"
            ),
            inline=True
        )

    await interaction.response.send_message(embed=embed)


@tree.command(name="search", description="Search downloads by tweet ID, username, or filename.")
@app_commands.describe(query="Search term")
async def search_downloads(interaction: discord.Interaction, query: str):
    """Search downloads"""
    results = db.search_downloads(query)

    if not results:
        await interaction.response.send_message(f"No results found for '{query}'")
        return

    embed = discord.Embed(
        title=f"🔍 Search Results for '{query}'",
        color=discord.Color.orange(),
        description=f"Found {len(results)} matching downloads"
    )

    for i, row in enumerate(results[:5], 1):
        embed.add_field(
            name=f"{i}. {row['tweet_id'][:12]}...",
            value=(
                f"👤 {row['discord_username']}\n"
                f"📅 {row['created_at'][:16]}\n"
                f"🔗 [View Tweet]({row['tweet_url']})"
            ),
            inline=True
        )

    if len(results) > 5:
        embed.set_footer(text=f"Showing 5 of {len(results)} results")

    await interaction.response.send_message(embed=embed)


@tree.command(name="cleanup", description="Remove database records for files no longer on disk.")
@app_commands.checks.has_permissions(administrator=True)
async def cleanup_database(interaction: discord.Interaction):
    """Clean up orphaned database records"""
    db.cleanup_orphaned_records()
    await interaction.response.send_message("✅ Database cleanup complete!")

@tree.command(
    name="compact",
    description="Download unprocessed tweets and remove older duplicate posts, keeping only the newest per tweet."
)
@app_commands.checks.has_permissions(manage_messages=True)
async def compact(interaction: discord.Interaction):
    """Scan the channel newest-first, ensure every tweet is downloaded, then delete older duplicate posts."""
    await interaction.response.defer(thinking=True)
    channel = interaction.channel

    status_msg = await interaction.followup.send("🔍 Scanning channel history...")

    # Pass 1: collect all messages that contain tweet URLs, newest-first.
    # Each tweet_id maps to an ordered list of messages (index 0 = newest).
    tweet_messages: dict[str, list[discord.Message]] = {}
    scanned = 0

    async for message in channel.history(limit=None, oldest_first=False):
        scanned += 1
        if scanned % 500 == 0:
            await status_msg.edit(content=f"🔍 Scanned {scanned} messages...")

        tweet_ids = TWITTER_URL_REGEX.findall(message.content)
        for tweet_id in tweet_ids:
            tweet_messages.setdefault(tweet_id, []).append(message)

    total_tweets = len(tweet_messages)
    await status_msg.edit(
        content=f"📋 Found {total_tweets} unique tweet(s) across {scanned} messages. Processing..."
    )

    downloaded_count = 0
    deleted_count = 0

    for i, (tweet_id, messages) in enumerate(tweet_messages.items(), 1):
        if i % 10 == 0:
            await status_msg.edit(
                content=(
                    f"⚙️ Processing tweet {i}/{total_tweets}... "
                    f"({downloaded_count} downloaded, {deleted_count} deleted)"
                )
            )

        newest = messages[0]

        # Ensure the tweet media is downloaded before doing anything else.
        if not db.is_tweet_downloaded(tweet_id):
            files = await download_media_with_tracking(tweet_id)
            if files:
                total_size = sum(os.path.getsize(f['path']) for f in files)
                db.record_download(
                    tweet_id=tweet_id,
                    tweet_url=f"https://twitter.com/i/status/{tweet_id}",
                    discord_user=newest.author,
                    discord_channel=channel,
                    file_size=total_size,
                    media_count=len(files),
                    download_path=files[0]['path'],
                    tweet_author_id=files[0]['tweet_author_id'],
                )
                for file_info in files:
                    db.add_media_file(
                        tweet_id=tweet_id,
                        file_name=file_info['name'],
                        file_path=file_info['path'],
                        file_size=file_info['size'],
                        file_type=file_info['type'],
                        download_url=file_info.get('url'),
                    )
                downloaded_count += 1

        # Only delete older duplicates once the tweet is confirmed in the database.
        if db.is_tweet_downloaded(tweet_id):
            for old_message in messages[1:]:
                try:
                    await old_message.delete()
                    deleted_count += 1
                except discord.NotFound:
                    pass  # already gone
                except discord.Forbidden:
                    print(f"⚠️ No permission to delete message {old_message.id} in #{channel}")

    await status_msg.edit(
        content=(
            f"✅ Compact complete!\n"
            f"🔍 {scanned} messages scanned\n"
            f"📥 {downloaded_count} tweet(s) newly downloaded\n"
            f"🗑️ {deleted_count} duplicate message(s) removed"
        )
    )


# Run the bot
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
