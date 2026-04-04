# SELECT * FROM downloads d where d.download_path = './downloaded_media/2026-02-21/1998726892078379487_0_180902.jpg';


sqlite3 media_downloads.db "SELECT d.download_path FROM downloads d WHERE d.tweet_author_id = 136 OR d.tweet_author_id = 5;"
