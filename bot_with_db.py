# bot_with_db.py
import discord
import re
import os
import requests
from datetime import datetime
import mimetypes
from discord.ext import commands
from datetime import datetime
from database import MediaDatabase
from config import DISCORD_TOKEN, DOWNLOAD_PATH, ALLOWED_EXTENSIONS

# Initialize database
db = MediaDatabase()

# Create download directory with organization
def get_download_subpath(tweet_id):
    """Organize files by date and tweet ID"""
    today = datetime.now().strftime("%Y-%m-%d")
    daily_path = os.path.join(DOWNLOAD_PATH, today, tweet_id[:3])
    os.makedirs(daily_path, exist_ok=True)
    return daily_path

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Regex to detect Twitter/X URLs
TWITTER_REGEX = re.compile(
    r'https?://(?:www\.)?(?:twitter\.com|x\.com)/(?:\w+)/status/(\d+)'
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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Check for commands first
    if message.content.startswith('!stats'):
        await show_stats(message)
        return
    
    matches = TWITTER_REGEX.findall(message.content)
    
    if matches:
        for tweet_id in matches:
            await process_tweet_with_db(message, tweet_id)
    
    await bot.process_commands(message)

async def process_tweet_with_db(message, tweet_id):
    """Process tweet with database tracking"""
    # Check for duplicates
    if db.is_tweet_downloaded(tweet_id):
        print(f"⚠️ Tweet {tweet_id} already downloaded, skipping...")
        # Optional: Still post the link but don't re-download
        fx_url = f"https://fxtwitter.com/i/status/{tweet_id}"
        await message.channel.send(
            f"📋 Already downloaded: {fx_url}\n"
            f"(Originally downloaded from this tweet)"
        )
        return
    
    try:
        fx_url = f"https://fxtwitter.com/i/status/{tweet_id}"
        
        # Send fxtwitter link
        await message.channel.send(
            f"📥 Media from {message.author}: {fx_url}\n"
            f"🔄 Downloading to server..."
        )
        
        # Download media
        downloaded_files = await download_media_with_tracking(
            tweet_id, message.author, message.channel
        )
        
        if downloaded_files:
            # Record in database
            total_size = sum(os.path.getsize(f['path']) for f in downloaded_files)
            
            db.record_download(
                tweet_id=tweet_id,
                tweet_url=f"https://twitter.com/i/status/{tweet_id}",
                discord_user=message.author,
                discord_channel=message.channel,
                file_size=total_size,
                media_count=len(downloaded_files),
                download_path=downloaded_files[0]['path'] if downloaded_files else None
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
            
            await message.channel.send(
                f"✅ Successfully downloaded {len(downloaded_files)} file(s) "
                f"({total_size / 1024 / 1024:.2f} MB)"
            )
        else:
            await message.channel.send(
                f"⚠️ No media found in tweet {tweet_id}"
            )
            
    except Exception as e:
        print(f"❌ Error processing tweet {tweet_id}: {e}")
        await message.channel.send(
            f"❌ Failed to process media from tweet {tweet_id}"
        )

async def download_media_with_tracking(tweet_id, discord_user, discord_channel):
    """Download media with enhanced tracking"""
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

        # Extract tweet data, TODO: Fix possible exception if format is different
        media_data = data['tweet']['media']['all']
        if not media_data:
            print("ℹ️ No media found in tweet")
            return downloaded_files
        print(f"📥 Found {len(media_data)} media item(s)")

        # Create download directory
        today = datetime.now().strftime("%Y-%m-%d")
        download_dir = os.path.join("downloaded_media", today, tweet_id[:8])
        os.makedirs(download_dir, exist_ok=True)

        # Download each media item
        for i, media_item in enumerate(media_data):
            try:
                # Determine media type and URL
                media_type = media_item.get('type', '')
                media_url = None

                if media_type == 'photo' or 'url' in media_item:
                    # Photos have direct URL
                    media_url = media_item.get('url')
                elif media_type == 'video' or media_type == 'gif':
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
                filename = f"{tweet_id}_{i}_{timestamp}{file_extension}"
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
                            'index': i
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
        import traceback
        traceback.print_exc()
        return downloaded_files

async def show_stats(message):
    """Display download statistics"""
    stats = db.get_download_stats()
    
    embed = discord.Embed(
        title="📊 Media Download Statistics",
        color=discord.Color.blue()
    )
    
    # Format size
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
    
    # Recent activity
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
    
    await message.channel.send(embed=embed)

# Add additional commands
@bot.command(name="recent")
async def show_recent(ctx, limit: int = 10):
    """Show recent downloads"""
    recent = db.get_recent_downloads(limit)
    
    if not recent:
        await ctx.send("No downloads found.")
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
    
    await ctx.send(embed=embed)

@bot.command(name="search")
async def search_downloads(ctx, *, query: str):
    """Search downloads"""
    results = db.search_downloads(query)
    
    if not results:
        await ctx.send(f"No results found for '{query}'")
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
    
    await ctx.send(embed=embed)

@bot.command(name="cleanup")
@commands.has_permissions(administrator=True)
async def cleanup_database(ctx):
    """Clean up orphaned database records"""
    db.cleanup_orphaned_records()
    await ctx.send("✅ Database cleanup complete!")

# Run the bot
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)