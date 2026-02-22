# migrate_author_data.py
import os
import sys
import time
import requests
from database import MediaDatabase  # your existing DB class

# Use the same database path as your bot
DB_PATH = "media_downloads.db"
API_BASE = "https://api.fxtwitter.com/status/"


def fetch_author_from_api(tweet_id):
  """Fetch tweet data from FxTwitter API and return author info."""
  try:
    url = f"{API_BASE}{tweet_id}"
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
      print(f"⚠️ API returned {response.status_code} for tweet {tweet_id}")
      return None

    data = response.json()
    tweet_data = data.get('tweet')
    if not tweet_data:
      return None

    author_info = tweet_data.get('author')
    if not author_info:
      return None

    return {
      'author_id': str(author_info.get('id')),  # Twitter numeric ID as string
      'screen_name': author_info.get('screen_name'),
      'display_name': author_info.get('name')
    }
  except Exception as e:
    print(f"❌ Error fetching tweet {tweet_id}: {e}")
    return None


def migrate_authors():
  db = MediaDatabase(DB_PATH)

  # Ensure the tweet_authors table exists (your earlier CREATE TABLE)
  # and that downloads has tweet_author_id column.
  # If not, run the ALTER statements first (they are safe to re-run).

  # Get all downloads that don't have a tweet_author_id set yet
  with db.get_cursor() as cursor:
    cursor.execute('''
            SELECT tweet_id FROM downloads
            WHERE tweet_author_id IS NULL
        ''')
    rows = cursor.fetchall()

  total = len(rows)
  print(f"Found {total} downloads to process.")

  for idx, row in enumerate(rows, 1):
    tweet_id = row['tweet_id']
    print(f"[{idx}/{total}] Processing tweet {tweet_id}...")

    author = fetch_author_from_api(tweet_id)
    if not author:
      print(f"⚠️ Could not fetch author for tweet {tweet_id}, skipping.")
      continue

    # Insert or update author in tweet_authors
    with db.get_cursor() as cursor:
      cursor.execute('''
                INSERT INTO tweet_authors (author_id, author_name, author_display_name)
                VALUES (?, ?, ?)
                ON CONFLICT(author_id) DO UPDATE SET
                    author_name = excluded.author_name,
                    author_display_name = excluded.author_display_name,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            ''', (author['author_id'], author['screen_name'], author['display_name']))
      author_db_id = cursor.fetchone()['id']

      # Update downloads table
      cursor.execute('''
                UPDATE downloads SET tweet_author_id = ?
                WHERE tweet_id = ?
            ''', (author_db_id, tweet_id))

    print(f"✅ Linked tweet {tweet_id} to author @{author['screen_name']} (ID: {author['author_id']})")

    # Be nice to the API – small delay between requests
    time.sleep(0.5)

  print("Migration complete!")


if __name__ == "__main__":
  migrate_authors()