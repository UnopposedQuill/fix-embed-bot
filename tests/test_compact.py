import pytest
from unittest.mock import Mock, AsyncMock, patch
import discord
from bot_with_db import compact, TWITTER_URL_REGEX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_message(content, msg_id=1, author_name="user"):
    msg = Mock(spec=discord.Message)
    msg.content = content
    msg.id = msg_id
    msg.author = Mock()
    msg.author.id = 111111111111111111
    msg.author.name = author_name
    msg.delete = AsyncMock()
    return msg


def make_interaction(messages):
    """Return a mock Interaction whose channel yields the given messages newest-first."""

    async def mock_history(**kwargs):
        for msg in messages:
            yield msg

    channel = Mock(spec=discord.TextChannel)
    channel.history = Mock(return_value=mock_history())

    status_msg = Mock()
    status_msg.edit = AsyncMock()

    interaction = Mock(spec=discord.Interaction)
    interaction.channel = channel
    interaction.response = Mock()
    interaction.response.defer = AsyncMock()
    interaction.followup = Mock()
    interaction.followup.send = AsyncMock(return_value=status_msg)

    return interaction, status_msg


def make_downloaded_file(tweet_id="123", author_db_id=42):
    return {
        "name": f"{tweet_id}_0_000000.jpg",
        "path": f"/fake/{tweet_id}.jpg",
        "size": 1024,
        "type": "photo",
        "url": "https://example.com/img.jpg",
        "tweet_author_id": author_db_id,
    }


# ---------------------------------------------------------------------------
# Regex tests (synchronous)
# ---------------------------------------------------------------------------

def test_url_regex_matches_twitter():
    matches = TWITTER_URL_REGEX.findall("https://twitter.com/user/status/111")
    assert matches == ["111"]


def test_url_regex_matches_x_com():
    matches = TWITTER_URL_REGEX.findall("https://x.com/user/status/222")
    assert matches == ["222"]


def test_url_regex_matches_fxtwitter():
    """Bot-posted fxtwitter links must also be detected during the scan."""
    matches = TWITTER_URL_REGEX.findall(
        "📥 Media from user: https://fxtwitter.com/i/status/333"
    )
    assert matches == ["333"]


def test_url_regex_extracts_multiple_ids():
    text = (
        "https://twitter.com/a/status/100 "
        "https://x.com/b/status/200"
    )
    matches = TWITTER_URL_REGEX.findall(text)
    assert matches == ["100", "200"]


# ---------------------------------------------------------------------------
# /compact command tests (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compact_no_tweet_messages_does_nothing():
    """When no messages contain tweet URLs nothing is downloaded or deleted."""
    messages = [
        make_message("Hello world", msg_id=2),
        make_message("No tweets here", msg_id=1),
    ]
    interaction, _ = make_interaction(messages)

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock) as mock_dl:

        await compact.callback(interaction)

        mock_dl.assert_not_called()
        mock_db.record_download.assert_not_called()
        for msg in messages:
            msg.delete.assert_not_called()


@pytest.mark.asyncio
async def test_compact_downloads_unprocessed_tweet():
    """A tweet not in the database gets downloaded and recorded."""
    tweet_id = "444444444"
    msg = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=10)
    interaction, _ = make_interaction([msg])

    file_info = make_downloaded_file(tweet_id)

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock, return_value=[file_info]) as mock_dl, \
         patch("os.path.getsize", return_value=1024):
        mock_db.is_tweet_downloaded.return_value = False

        await compact.callback(interaction)

        mock_dl.assert_called_once_with(tweet_id)
        mock_db.record_download.assert_called_once()
        mock_db.add_media_file.assert_called_once()


@pytest.mark.asyncio
async def test_compact_skips_already_downloaded_tweet():
    """A tweet already in the database is not re-downloaded."""
    tweet_id = "555555555"
    msg = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=10)
    interaction, _ = make_interaction([msg])

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock) as mock_dl:
        mock_db.is_tweet_downloaded.return_value = True

        await compact.callback(interaction)

        mock_dl.assert_not_called()
        mock_db.record_download.assert_not_called()


@pytest.mark.asyncio
async def test_compact_deletes_older_duplicate_messages():
    """When the same tweet appears in multiple messages, only the oldest copies are deleted."""
    tweet_id = "666666666"
    newest = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=30)
    older1 = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=20)
    # Also verify fxtwitter bot messages are treated the same way
    older2 = make_message(f"📥 Media: https://fxtwitter.com/i/status/{tweet_id}", msg_id=10)

    # history is newest-first
    interaction, _ = make_interaction([newest, older1, older2])

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock):
        mock_db.is_tweet_downloaded.return_value = True

        await compact.callback(interaction)

        newest.delete.assert_not_called()
        older1.delete.assert_called_once()
        older2.delete.assert_called_once()


@pytest.mark.asyncio
async def test_compact_does_not_delete_if_download_failed():
    """A transient API error (None) leaves all messages intact."""
    tweet_id = "777777777"
    newest = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=20)
    older = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=10)
    interaction, _ = make_interaction([newest, older])

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock, return_value=None), \
         patch("bot_with_db._is_tweet_deleted", return_value=False):
        mock_db.is_tweet_downloaded.return_value = False

        await compact.callback(interaction)

        older.delete.assert_not_called()
        newest.delete.assert_not_called()


@pytest.mark.asyncio
async def test_compact_marks_no_media_tweet_as_processed():
    """A tweet with no media (empty list, not None) is recorded so it is not retried."""
    tweet_id = "131313131"
    msg = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=10)
    interaction, _ = make_interaction([msg])

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock, return_value=[]):
        mock_db.is_tweet_downloaded.return_value = False
        mock_db.get_download.return_value = None

        await compact.callback(interaction)

        mock_db.record_download.assert_called_once()
        # media_count should be 0
        _, kwargs = mock_db.record_download.call_args
        assert kwargs["media_count"] == 0
        assert kwargs["download_path"] is None


@pytest.mark.asyncio
async def test_compact_keeps_unique_tweet_messages():
    """Messages where each tweet ID appears only once are never deleted."""
    messages = [
        make_message("https://twitter.com/user/status/888888888", msg_id=20),
        make_message("https://twitter.com/user/status/999999999", msg_id=10),
    ]
    interaction, _ = make_interaction(messages)

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock):
        mock_db.is_tweet_downloaded.return_value = True

        await compact.callback(interaction)

        for msg in messages:
            msg.delete.assert_not_called()


@pytest.mark.asyncio
async def test_compact_handles_deleted_message_gracefully():
    """A NotFound error when deleting an already-gone message does not crash the command."""
    tweet_id = "101010101"
    newest = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=20)
    older = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=10)
    older.delete = AsyncMock(side_effect=discord.NotFound(Mock(), "unknown message"))
    interaction, _ = make_interaction([newest, older])

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock):
        mock_db.is_tweet_downloaded.return_value = True

        # Should not raise
        await compact.callback(interaction)


@pytest.mark.asyncio
async def test_compact_reports_summary_at_the_end():
    """The final status message edit contains download and deletion counts."""
    tweet_id = "121212121"
    newest = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=20)
    older = make_message(f"https://twitter.com/user/status/{tweet_id}", msg_id=10)
    interaction, status_msg = make_interaction([newest, older])

    file_info = make_downloaded_file(tweet_id)

    with patch("bot_with_db.db") as mock_db, \
         patch("bot_with_db.download_media_with_tracking", new_callable=AsyncMock, return_value=[file_info]), \
         patch("os.path.getsize", return_value=1024):
        # First call (download check): not downloaded. Second call (deletion check): downloaded.
        mock_db.is_tweet_downloaded.side_effect = [False, True]

        await compact.callback(interaction)

        # The last edit should mention the counts
        last_edit_content = status_msg.edit.call_args_list[-1][1]["content"]
        assert "1" in last_edit_content  # 1 downloaded
        assert "1" in last_edit_content  # 1 deleted
