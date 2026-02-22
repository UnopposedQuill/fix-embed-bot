-- 1. Create the authors table
CREATE TABLE IF NOT EXISTS tweet_authors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id TEXT UNIQUE NOT NULL,        -- Twitter's numeric user ID (string to be safe)
    author_name TEXT NOT NULL,              -- @screen_name
    author_display_name TEXT,                -- optional: display name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Add a column to downloads referencing the authors table
ALTER TABLE downloads ADD COLUMN tweet_author_id INTEGER REFERENCES tweet_authors(id);

-- 3. (Optional) Create an index for faster lookups
CREATE INDEX idx_downloads_tweet_author ON downloads(tweet_author_id);