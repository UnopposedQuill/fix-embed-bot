# bot_with_db.py
import discord
import re
import os
import requests
import hashlib
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
        vx_url = f"https://vxtwitter.com/i/status/{tweet_id}"
        await message.channel.send(
            f"📋 Already downloaded: {vx_url}\n"
            f"(Originally downloaded from this tweet)"
        )
        return
    
    try:
        vx_url = f"https://vxtwitter.com/i/status/{tweet_id}"
        
        # Send vxtwitter link
        await message.channel.send(
            f"📥 Media from {message.author.mention}: {vx_url}\n"
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
        # Try vxtwitter API first
        api_url = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'media_extended' in data and data['media_extended']:
                download_path = get_download_subpath(tweet_id)
                
                for i, media in enumerate(data['media_extended']):
                    media_url = media.get('url')
                    if media_url:
                        # Generate safe filename
                        file_extension = os.path.splitext(media_url.split('?')[0])[1]
                        if not file_extension:
                            file_extension = '.jpg'  # Default
                        
                        # Create unique filename
                        timestamp = datetime.now().strftime("%H%M%S")
                        filename = f"{tweet_id}_{i}_{timestamp}{file_extension}"
                        filepath = os.path.join(download_path, filename)
                        
                        # Download file
                        media_response = requests.get(media_url, stream=True)
                        file_size = 0
                        
                        with open(filepath, 'wb') as f:
                            for chunk in media_response.iter_content(chunk_size=8192):
                                f.write(chunk)
                                file_size += len(chunk)
                        
                        # Verify file was written
                        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                            downloaded_files.append({
                                'name': filename,
                                'path': filepath,
                                'size': file_size,
                                'type': file_extension[1:],  # Remove dot
                                'url': media_url
                            })
                            print(f"✅ Downloaded: {filename} ({file_size} bytes)")
        else:
            print(f"⚠️ API returned status {response.status_code} for tweet {tweet_id}")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Download error for tweet {tweet_id}: {e}")
    
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