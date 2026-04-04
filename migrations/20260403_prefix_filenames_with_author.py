"""
Migration: prefix downloaded filenames with the tweet author's screen name.

Before: {tweet_id}_{index}_{timestamp}.ext
After:  {screen_name}_{tweet_id}_{index}_{timestamp}.ext

Records with no linked author are prefixed with "unknown".
Safe to re-run: files already carrying a prefix are skipped.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import MediaDatabase

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "media_downloads.db")


def already_prefixed(file_name, author_name):
    """Return True if the file already starts with the expected author prefix."""
    return file_name.startswith(f"{author_name}_")


def migrate():
    db = MediaDatabase(DB_PATH)

    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                mf.id        AS mf_id,
                mf.file_name AS file_name,
                mf.file_path AS file_path,
                mf.tweet_id  AS tweet_id,
                COALESCE(ta.author_name, 'unknown') AS author_name
            FROM media_files mf
            JOIN downloads d ON mf.tweet_id = d.tweet_id
            LEFT JOIN tweet_authors ta ON d.tweet_author_id = ta.id
        """)
        rows = cursor.fetchall()

    total = len(rows)
    skipped = renamed = errors = 0

    print(f"Found {total} file record(s) to process.")

    for row in rows:
        author_name = row["author_name"]
        old_name = row["file_name"]
        old_path = row["file_path"]

        if already_prefixed(old_name, author_name):
            skipped += 1
            continue

        new_name = f"{author_name}_{old_name}"
        new_path = os.path.join(os.path.dirname(old_path), new_name)

        # Rename the physical file
        if os.path.exists(old_path):
            try:
                os.rename(old_path, new_path)
            except OSError as e:
                print(f"  ❌ Could not rename {old_path}: {e}")
                errors += 1
                continue
        else:
            print(f"  ⚠️  File not on disk, updating DB record only: {old_path}")

        # Update media_files
        with db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE media_files SET file_name = ?, file_path = ? WHERE id = ?",
                (new_name, new_path, row["mf_id"]),
            )

        # Keep download_path in downloads in sync if it pointed to this file
        with db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE downloads SET download_path = ? WHERE tweet_id = ? AND download_path = ?",
                (new_path, row["tweet_id"], old_path),
            )

        print(f"  ✅ {old_name}  →  {new_name}")
        renamed += 1

    print(
        f"\nDone. {renamed} renamed, {skipped} already correct, {errors} error(s)."
    )


if __name__ == "__main__":
    migrate()
