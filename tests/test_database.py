import pytest
import tempfile
import os
from database import MediaDatabase


class MockUser:
    id = 111111111111111111
    name = "testuser"


class MockChannel:
    id = 222222222222222222

@pytest.fixture
def temp_db():
    """Create a temporary database for each test"""
    db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = db_file.name
    db_file.close()
    
    db = MediaDatabase(db_path)
    yield db
    
    # Cleanup
    os.unlink(db_path)

def test_duplicate_detection(temp_db):
    """Test that duplicate tweets are correctly identified"""
    tweet_id = "123456789"
    
    # Should not be downloaded yet
    assert not temp_db.is_tweet_downloaded(tweet_id)
    
    # Record a download
    temp_db.record_download(
        tweet_id=tweet_id,
        tweet_url="https://twitter.com/...",
        discord_user=MockUser(),
        discord_channel=MockChannel(),
        file_size=1024,
        media_count=1,
        download_path="/fake/path"
    )
    
    # Should now be detected as downloaded
    assert temp_db.is_tweet_downloaded(tweet_id)