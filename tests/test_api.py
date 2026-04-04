import pytest
from unittest.mock import Mock, patch
from bot_with_db import download_media_with_tracking

@pytest.mark.asyncio
async def test_api_successful_response():
    """Test handling of successful API response with media"""
    # Mock the API response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tweet": {
            "media": [
                {
                    "type": "photo",
                    "url": "https://example.com/image.jpg"
                }
            ],
            "author": {
                "id": "12345",
                "screen_name": "testuser",
                "name": "Test User"
            }
        }
    }
    
    with patch('requests.get', return_value=mock_response):
        # Create mock user and channel
        mock_user = Mock()
        mock_user.id = "123"
        mock_user.name = "DiscordUser"
        mock_channel = Mock()
        mock_channel.id = "456"
        
        # Call the function
        result = await download_media_with_tracking(
            "123456789", mock_user, mock_channel
        )
        
        # Assert it processed correctly
        assert isinstance(result, list)