# maintenance.py
from database import MediaDatabase

db = MediaDatabase()

def run_maintenance():
    """Regular maintenance tasks"""
    print("🔧 Running maintenance...")

    # 1. Clean up orphaned records
    db.cleanup_orphaned_records()
    print("✅ Cleaned orphaned records")

    # 2. Update statistics
    stats = db.get_download_stats()
    print(f"📊 Current stats: {stats['total_downloads']} downloads, "
          f"{stats['unique_users']} users, "
          f"{stats['total_size'] / 1024 / 1024:.2f} MB")

    # 3. Check for large files that might need cleanup
    # (Add custom logic based on your needs)

if __name__ == "__main__":
    run_maintenance()
