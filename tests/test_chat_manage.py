import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from yaicli.chat_manager import FileChatManager
from yaicli.config import Config


@pytest.fixture
def temp_chat_dir():
    """Create a temporary directory for chat history files that will be removed after tests."""
    with TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def chat_manager(temp_chat_dir, mock_console):
    """Create a FileChatManager with a temporary directory for testing."""
    mock_config = MagicMock(spec=Config)
    # Dictionary-like access for config
    mock_config.__getitem__.side_effect = lambda key: {
        "CHAT_HISTORY_DIR": temp_chat_dir,
        "MAX_SAVED_CHATS": 10,
    }.get(key)

    manager = FileChatManager(config=mock_config, console=mock_console)
    return manager


class TestFileChatManager:
    def test_init(self, chat_manager, temp_chat_dir):
        """Test initialization of FileChatManager."""
        assert chat_manager.chat_dir == Path(temp_chat_dir)
        assert chat_manager.max_saved_chats == 10
        assert chat_manager._chats_map is None

    def test_make_chat_title(self, chat_manager):
        """Test chat title generation."""
        # Test with prompt
        title = chat_manager.make_chat_title("This is a test prompt")
        assert title == "This_is_a_test_prompt"

        # Test with long prompt (should truncate)
        long_prompt = "A" * 100
        title = chat_manager.make_chat_title(long_prompt)
        assert len(title) == 50
        assert title == "A" * 50

        # Test without prompt (should use timestamp)
        with patch("time.time", return_value=12345):
            title = chat_manager.make_chat_title()
            assert title == "Chat-12345"

    def test_save_and_load_chat(self, chat_manager):
        """Test saving a chat and loading it back."""
        # Create sample chat history
        history = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]

        # Save the chat
        title = chat_manager.save_chat(history, "Test Chat")
        assert title == "Test Chat"

        # Verify chat is loaded correctly
        chat_data = chat_manager.load_chat_by_title("Test Chat")
        assert chat_data["title"] == "Test Chat"
        assert len(chat_data["history"]) == 2
        assert chat_data["history"][0]["content"] == "Hello"
        assert chat_data["history"][1]["content"] == "Hi there!"

    def test_save_chat_no_title(self, chat_manager):
        """Test saving a chat without a title."""
        history = [{"role": "user", "content": "Test message"}]

        with patch("time.time", return_value=12345):
            title = chat_manager.save_chat(history)
            assert title == "Chat-12345"

    def test_save_chat_empty_history(self, chat_manager):
        """Test saving an empty chat history."""
        title = chat_manager.save_chat([])
        assert title == ""

    def test_save_chat_overwrite_existing(self, chat_manager):
        """Test that saving a chat with an existing title overwrites the old chat."""
        # Create and save initial chat
        history1 = [{"role": "user", "content": "First chat"}]
        chat_manager.save_chat(history1, "Same Title")

        # Create and save another chat with the same title
        history2 = [{"role": "user", "content": "Second chat"}]
        chat_manager.save_chat(history2, "Same Title")

        # Load the chat and verify it's the second one
        chat_data = chat_manager.load_chat_by_title("Same Title")
        assert chat_data["history"][0]["content"] == "Second chat"

    def test_list_chats(self, chat_manager):
        """Test listing saved chats."""
        # Save a few chats
        chat_manager.save_chat([{"role": "user", "content": "Chat 1"}], "Title 1")
        chat_manager.save_chat([{"role": "user", "content": "Chat 2"}], "Title 2")
        chat_manager.save_chat([{"role": "user", "content": "Chat 3"}], "Title 3")

        # List chats
        chats = chat_manager.list_chats()

        # Verify list contains the saved chats
        assert len(chats) == 3
        titles = [chat["title"] for chat in chats]
        assert "Title 1" in titles
        assert "Title 2" in titles
        assert "Title 3" in titles

    def test_max_saved_chats(self, temp_chat_dir, mock_console):
        """Test that max_saved_chats is respected."""
        # Create a manager with max 2 saved chats
        mock_config = MagicMock(spec=Config)
        mock_config.__getitem__.side_effect = lambda key: {
            "CHAT_HISTORY_DIR": temp_chat_dir,
            "MAX_SAVED_CHATS": 2,
        }.get(key)

        manager = FileChatManager(config=mock_config, console=mock_console)

        # Save 3 chats
        manager.save_chat([{"role": "user", "content": "Chat 1"}], "Title 1")
        time.sleep(0.1)  # Ensure different timestamps
        manager.save_chat([{"role": "user", "content": "Chat 2"}], "Title 2")
        time.sleep(0.1)  # Ensure different timestamps
        manager.save_chat([{"role": "user", "content": "Chat 3"}], "Title 3")

        # Should only keep the 2 most recent
        chats = manager.list_chats()
        assert len(chats) == 2
        titles = [chat["title"] for chat in chats]
        assert "Title 3" in titles
        assert "Title 2" in titles
        assert "Title 1" not in titles

    def test_load_chat_by_index(self, chat_manager):
        """Test loading a chat by index."""
        # Save chats
        chat_manager.save_chat([{"role": "user", "content": "Chat 1"}], "Title 1")
        chat_manager.save_chat([{"role": "user", "content": "Chat 2"}], "Title 2")

        # Get the index of the first chat
        chats = chat_manager.list_chats()
        index = next((chat["index"] for chat in chats if chat["title"] == "Title 1"), None)

        # Load by index
        chat_data = chat_manager.load_chat(index)
        assert chat_data["title"] == "Title 1"
        assert chat_data["history"][0]["content"] == "Chat 1"

    def test_load_nonexistent_chat(self, chat_manager):
        """Test loading a chat that doesn't exist."""
        # By index
        chat_data = chat_manager.load_chat(999)
        assert chat_data == {}

        # By title
        chat_data = chat_manager.load_chat_by_title("Nonexistent Title")
        assert chat_data == {}

    def test_validate_chat_index(self, chat_manager):
        """Test validation of chat indexes."""
        # Save a chat
        chat_manager.save_chat([{"role": "user", "content": "Test"}], "Test")

        # Get its index
        chats = chat_manager.list_chats()
        valid_index = chats[0]["index"]

        # Test validation
        assert chat_manager.validate_chat_index(valid_index) is True
        assert chat_manager.validate_chat_index(999) is False
        assert chat_manager.validate_chat_index(0) is False
        assert chat_manager.validate_chat_index(-1) is False

    def test_delete_chat(self, chat_manager):
        """Test deleting a chat."""
        # Save a chat
        chat_manager.save_chat([{"role": "user", "content": "Test"}], "Test")

        # Get its index
        chats = chat_manager.list_chats()
        index = chats[0]["index"]

        # Delete it
        result = chat_manager.delete_chat(index)
        assert result is True

        # Verify it's gone
        assert chat_manager.load_chat(index) == {}
        assert len(chat_manager.list_chats()) == 0

    def test_delete_nonexistent_chat(self, chat_manager):
        """Test deleting a chat that doesn't exist."""
        result = chat_manager.delete_chat(999)
        assert result is False

    def test_refresh_chats(self, chat_manager, temp_chat_dir):
        """Test refreshing chats from disk."""
        # Save a chat
        chat_manager.save_chat([{"role": "user", "content": "Test"}], "Test")

        # Modify _chats_map directly to simulate stale data
        chat_manager._chats_map = {"title": {}, "index": {}}

        # Refresh should load from disk
        chat_manager.refresh_chats()

        # Verify chat is loaded
        chats = chat_manager.list_chats()
        assert len(chats) == 1
        assert chats[0]["title"] == "Test"

    def test_parse_filename(self, chat_manager):
        """Test parsing of chat filenames."""
        # Standard filename
        chat_file = Path("20230401-120000-title-Test_Chat.json")
        info = chat_manager._parse_filename(chat_file, 1)

        assert info["index"] == 1
        assert info["title"] == "Test Chat"
        assert info["date"] == "2023-04-01 12:00"

        # Filename with special characters
        chat_file = Path("20230401-120000-title-Test_Chat_With-Dashes.json")
        info = chat_manager._parse_filename(chat_file, 2)

        assert info["index"] == 2
        assert info["title"] == "Test Chat With-Dashes"

        # Irregular filename
        chat_file = Path("irregular_filename.json")
        info = chat_manager._parse_filename(chat_file, 3)

        assert info["index"] == 3
        assert info["title"] == "irregular filename"
        assert info["date"] == ""

    def test_file_error_handling(self, chat_manager, monkeypatch):
        """Test handling of file errors."""
        # Test file not found
        with monkeypatch.context() as m:
            m.setattr(Path, "exists", lambda self: False)
            chat_data = chat_manager.load_chat_by_title("Nonexistent")
            assert chat_data == {}

        # Test JSON decode error
        chat_manager.save_chat([{"role": "user", "content": "Test"}], "Test")
        chats = chat_manager.list_chats()
        index = chats[0]["index"]

        with monkeypatch.context() as m:

            def mock_open(*args, **kwargs):
                mock = MagicMock()
                mock.__enter__ = lambda self: self
                mock.__exit__ = lambda *args: None
                mock.read = lambda: "invalid json"
                return mock

            m.setattr("builtins.open", mock_open)
            chat_data = chat_manager.load_chat(index)
            assert chat_data == {}
