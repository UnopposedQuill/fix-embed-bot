# database.py
import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

class MediaDatabase:
    def __init__(self, db_path="media_downloads.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database tables"""
        with self.get_cursor() as cursor:
            # Table for tracking downloaded tweets
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id TEXT UNIQUE NOT NULL,
                    tweet_url TEXT NOT NULL,
                    discord_user_id TEXT NOT NULL,
                    discord_username TEXT NOT NULL,
                    discord_channel_id TEXT NOT NULL,
                    download_path TEXT,
                    file_size INTEGER,
                    tweet_author_id TEXT,
                    media_count INTEGER DEFAULT 1,
                    download_status TEXT DEFAULT 'success',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table for tracking individual media files
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS media_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_type TEXT NOT NULL,
                    download_url TEXT,
                    FOREIGN KEY (tweet_id) REFERENCES downloads (tweet_id),
                    UNIQUE(tweet_id, file_name)
                )
            ''')
            
            # Table for download statistics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_downloads INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    unique_users INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insert initial stats if not exists
            cursor.execute('''
                INSERT OR IGNORE INTO stats (id, total_downloads, total_size, unique_users)
                VALUES (1, 0, 0, 0)
            ''')
            
            # Table for tracking unique users
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS unique_users (
                    user_id TEXT PRIMARY KEY
                )
            ''')

            # Create indexes for faster queries
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tweet_id ON downloads(tweet_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_discord_user ON downloads(discord_user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON downloads(created_at)')
    
    def is_tweet_downloaded(self, tweet_id):
        """Check if a tweet has already been downloaded"""
        with self.get_cursor() as cursor:
            cursor.execute(
                'SELECT 1 FROM downloads WHERE tweet_id = ? LIMIT 1',
                (tweet_id,)
            )
            return cursor.fetchone() is not None
    
    def record_download(self, tweet_id, tweet_url, discord_user, discord_channel, 
                       file_size=0, media_count=1, download_path=None, tweet_author_id=None):
        """Record a new download in the database"""
        with self.get_cursor() as cursor:
            # Insert or update download record
            cursor.execute('''
                INSERT OR REPLACE INTO downloads 
                (tweet_id, tweet_url, discord_user_id, discord_username, 
                 discord_channel_id, download_path, file_size, tweet_author_id, media_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tweet_id, tweet_url, str(discord_user.id), discord_user.name,
                  str(discord_channel.id), download_path, file_size, tweet_author_id,
                  media_count, datetime.now().isoformat()))
            
            # Update statistics
            cursor.execute('''
                UPDATE stats 
                SET total_downloads = total_downloads + 1,
                    total_size = total_size + ?,
                    updated_at = ?
                WHERE id = 1
            ''', (file_size, datetime.now().isoformat()))
            
            # Update unique user count
            cursor.execute('''
                INSERT OR IGNORE INTO unique_users (user_id)
                VALUES (?)
            ''', (str(discord_user.id),))
            
            cursor.execute('SELECT COUNT(*) as count FROM unique_users')
            unique_count = cursor.fetchone()['count']
            
            cursor.execute('''
                UPDATE stats SET unique_users = ?
                WHERE id = 1
            ''', (unique_count,))
    
    def add_media_file(self, tweet_id, file_name, file_path, file_size, file_type, download_url=None):
        """Record an individual media file"""
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT OR IGNORE INTO media_files 
                (tweet_id, file_name, file_path, file_size, file_type, download_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (tweet_id, file_name, file_path, file_size, file_type, download_url))
    
    def get_download_stats(self):
        """Get download statistics"""
        with self.get_cursor() as cursor:
            cursor.execute('SELECT * FROM stats WHERE id = 1')
            stats = cursor.fetchone()
            
            cursor.execute('''
                SELECT COUNT(DISTINCT discord_user_id) as user_count,
                       COUNT(*) as total_downloads,
                       SUM(file_size) as total_size,
                       strftime('%Y-%m-%d', created_at) as date
                FROM downloads
                GROUP BY date
                ORDER BY date DESC
                LIMIT 30
            ''')
            daily_stats = cursor.fetchall()
            
            return {
                'total_downloads': stats['total_downloads'],
                'total_size': stats['total_size'],
                'unique_users': stats['unique_users'],
                'daily_stats': daily_stats
            }
    
    def get_recent_downloads(self, limit=10):
        """Get recent downloads"""
        with self.get_cursor() as cursor:
            cursor.execute('''
                SELECT d.*, 
                       GROUP_CONCAT(mf.file_name, ', ') as files,
                       COUNT(mf.id) as file_count
                FROM downloads d
                LEFT JOIN media_files mf ON d.tweet_id = mf.tweet_id
                GROUP BY d.tweet_id
                ORDER BY d.created_at DESC
                LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
    
    def search_downloads(self, query, limit=20):
        """Search downloads by tweet ID, username, or filename"""
        with self.get_cursor() as cursor:
            cursor.execute('''
                SELECT d.* FROM downloads d
                WHERE d.tweet_id LIKE ? 
                   OR d.discord_username LIKE ?
                   OR EXISTS (
                       SELECT 1 FROM media_files mf 
                       WHERE mf.tweet_id = d.tweet_id 
                       AND mf.file_name LIKE ?
                   )
                ORDER BY d.created_at DESC
                LIMIT ?
            ''', (f'%{query}%', f'%{query}%', f'%{query}%', limit))
            return cursor.fetchall()
    
    def cleanup_orphaned_records(self):
        """Remove database records for files that no longer exist"""
        with self.get_cursor() as cursor:
            cursor.execute('SELECT tweet_id, download_path FROM downloads')
            downloads = cursor.fetchall()
            
            for download in downloads:
                if download['download_path'] and not os.path.exists(download['download_path']):
                    cursor.execute('DELETE FROM downloads WHERE tweet_id = ?', 
                                 (download['tweet_id'],))
                    cursor.execute('DELETE FROM media_files WHERE tweet_id = ?',
                                 (download['tweet_id'],))

    def insert_or_update_author(self, author_id, screen_name, display_name=None):
        with self.get_cursor() as cursor:
            cursor.execute('''
                INSERT INTO tweet_authors (author_id, author_name, author_display_name, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(author_id) DO UPDATE SET
                    author_name = excluded.author_name,
                    author_display_name = excluded.author_display_name,
                    updated_at = CURRENT_TIMESTAMP
            ''', (author_id, screen_name, display_name))

    def get_author_id(self, author_id):
        with self.get_cursor() as cursor:
            cursor.execute('SELECT id FROM tweet_authors WHERE author_id = ?', (author_id,))
            row = cursor.fetchone()
            return row['id'] if row else None
