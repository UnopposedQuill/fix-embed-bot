-- Check total statistics
SELECT * FROM stats;

-- View all downloads with file counts
SELECT d.*, 
       COUNT(mf.id) as file_count,
       GROUP_CONCAT(mf.file_name) as files
FROM downloads d
LEFT JOIN media_files mf ON d.tweet_id = mf.tweet_id
GROUP BY d.tweet_id
ORDER BY d.created_at DESC
LIMIT 10;

-- Get storage usage by user
SELECT discord_username, 
       COUNT(*) as tweet_count,
       SUM(file_size) as total_size_mb
FROM downloads
GROUP BY discord_user_id
ORDER BY total_size_mb DESC;

-- Find duplicates (should return none with our UNIQUE constraint)
SELECT tweet_id, COUNT(*) as count
FROM downloads
GROUP BY tweet_id
HAVING count > 1;

-- Get daily download statistics
SELECT strftime('%Y-%m-%d', created_at) as date,
       COUNT(*) as downloads,
       COUNT(DISTINCT discord_user_id) as unique_users,
       SUM(file_size) / (1024 * 1024) as size_mb
FROM downloads
GROUP BY date
ORDER BY date DESC;