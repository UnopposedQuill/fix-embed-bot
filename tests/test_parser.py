import re
from bot_with_db import TWITTER_REGEX

def test_url_detection():
    """Test that various Twitter/X URLs are detected"""
    test_urls = [
        "https://twitter.com/user/status/123456789",
        "https://x.com/user/status/987654321",
        "http://www.twitter.com/user/status/555555555",
    ]
    
    for url in test_urls:
        matches = TWITTER_REGEX.findall(url)
        assert len(matches) == 1
        assert matches[0].isdigit()