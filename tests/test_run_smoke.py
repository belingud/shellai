import os
import unittest
from unittest.mock import patch, MagicMock

import pytest
import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from yaicli import CLI, CHAT_MODE, EXEC_MODE, TEMP_MODE


class MockResponse:
    """Mock HTTP response"""

    def __init__(self, json_data, status_code=200, stream=False):
        self.json_data = json_data
        self.status_code = status_code
        self._stream = stream

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception(f"HTTP Error: {self.status_code}")

    def iter_lines(self):
        if not self._stream:
            return []
        # Simulate streaming response format
        yield b'data: {"choices": [{"delta": {"content": "Hello"}}]}'
        yield b'data: {"choices": [{"delta": {"content": " World"}}]}'
        yield b"data: [DONE]"


class TestRunSmoke(unittest.TestCase):
    """Smoke tests for yaicli.py"""

    def setUp(self):
        # Set up environment for tests
        os.environ["YAI_API_KEY"] = "test_api_key"
        os.environ["YAI_STREAM"] = "false"  # Disable streaming for easier testing

        # Create CLI instance with test configuration
        self.cli = CLI(verbose=False)
        self.cli.load_config()

        # Mock console to prevent actual output during tests
        self.cli.console = MagicMock()

    def tearDown(self):
        # Clean up environment after tests
        if "YAI_API_KEY" in os.environ:
            del os.environ["YAI_API_KEY"]
        if "YAI_STREAM" in os.environ:
            del os.environ["YAI_STREAM"]

    @patch("httpx.Client.post")
    def test_simple_prompt(self, mock_post):
        """Test basic prompt mode (ai xxx)"""
        # Setup mock response
        mock_response = MockResponse({"choices": [{"message": {"content": "Test response"}}]})
        mock_post.return_value = mock_response

        # Run CLI with a simple prompt
        self.cli.run(chat=False, shell=False, prompt="Hello AI")

        # Verify API was called with correct parameters
        mock_post.assert_called_once()
        call_args = mock_post.call_args[1]
        self.assertEqual(call_args["json"]["messages"][-1]["content"], "Hello AI")

        # Verify mode was set correctly
        self.assertEqual(self.cli.current_mode, TEMP_MODE)

    @patch("httpx.Client.post")
    @patch("yaicli.CLI._confirm_and_execute")
    def test_shell_mode(self, mock_execute, mock_post):
        """Test shell command mode (ai --shell xxx)"""
        # Setup mock response
        mock_response = MockResponse({"choices": [{"message": {"content": "ls -la"}}]})
        mock_post.return_value = mock_response

        # Run CLI in shell mode
        self.cli.run(chat=False, shell=True, prompt="List files")

        # Verify API was called with correct parameters
        mock_post.assert_called_once()
        call_args = mock_post.call_args[1]
        self.assertEqual(call_args["json"]["messages"][-1]["content"], "List files")

        # Verify mode was set correctly
        self.assertEqual(self.cli.current_mode, EXEC_MODE)

        # Verify shell execution was attempted
        mock_execute.assert_called_once()

    @patch("httpx.Client.post")
    @patch("prompt_toolkit.PromptSession.prompt")
    def test_chat_mode(self, mock_prompt, mock_post):
        """Test chat mode (ai --chat)"""
        # Setup mock responses
        mock_response = MockResponse({"choices": [{"message": {"content": "Hello, how can I help?"}}]})
        mock_post.return_value = mock_response

        # Setup mock prompt inputs (first a message, then exit command)
        mock_prompt.side_effect = ["Hello AI", "/exit"]

        # Run CLI in chat mode
        self.cli.run(chat=True, shell=False, prompt="")

        # Verify mode was set correctly
        self.assertEqual(self.cli.current_mode, CHAT_MODE)

        # Verify API was called with correct parameters
        mock_post.assert_called_once()
        call_args = mock_post.call_args[1]
        self.assertEqual(call_args["json"]["messages"][-1]["content"], "Hello AI")

    @patch("httpx.Client.post")
    def test_error_handling(self, mock_post):
        """Test error handling in API calls"""
        # Setup mock error response
        mock_response = MockResponse({"error": "Invalid API key"}, status_code=401)
        # Make the mock response raise an exception when raise_for_status is called
        mock_response.raise_for_status = MagicMock(side_effect=Exception("HTTP Error: 401"))
        mock_post.return_value = mock_response
        
        # The error is caught in _run_once method and printed to console
        # We need to check that the console.print method was called with the error message
        with patch.object(self.cli.console, "print") as mock_print:
            self.cli.run(chat=False, shell=False, prompt="Hello AI")
            # Find any call that contains the error message
            error_calls = [call for call in mock_print.call_args_list if len(call[0]) > 0 and "Error:" in str(call[0][0])]
            self.assertTrue(len(error_calls) > 0, "No error message was printed to console")

    @patch("httpx.Client.post")
    def test_streaming_response(self, mock_post):
        """Test streaming response handling"""
        # Enable streaming for this test
        os.environ["YAI_STREAM"] = "true"
        self.cli.load_config()

        # Setup mock streaming response
        mock_response = MockResponse({}, stream=True)
        mock_post.return_value = mock_response

        # Run CLI with a simple prompt
        self.cli.run(chat=False, shell=False, prompt="Hello AI")

        # Verify API was called
        mock_post.assert_called_once()

        # Verify content was processed (checking history)
        self.assertEqual(len(self.cli.history), 2)  # User message and assistant response
        self.assertEqual(self.cli.history[1]["content"], "Hello World")


class TestPromptToolkitIntegration(unittest.TestCase):
    """Tests for prompt_toolkit integration"""

    def setUp(self):
        # Set up environment for tests
        os.environ["YAI_API_KEY"] = "test_api_key"
        os.environ["YAI_STREAM"] = "false"  # Disable streaming for easier testing

    def tearDown(self):
        # Clean up environment after tests
        if "YAI_API_KEY" in os.environ:
            del os.environ["YAI_API_KEY"]
        if "YAI_STREAM" in os.environ:
            del os.environ["YAI_STREAM"]

    @patch("httpx.Client.post")
    def test_prompt_toolkit_input(self, mock_post):
        """Test prompt_toolkit input handling"""
        # Setup mock response
        mock_response = MockResponse({"choices": [{"message": {"content": "Test response"}}]})
        mock_post.return_value = mock_response

        # Create CLI instance
        cli = CLI(verbose=False)
        cli.load_config()
        cli.console = MagicMock()

        # Instead of using prompt_toolkit's pipe input which causes EOFError,
        # we'll directly mock the session.prompt method
        cli.session = MagicMock()
        cli.session.prompt.side_effect = ["Hello AI", "/exit"]

        # Set up for chat mode
        cli.current_mode = CHAT_MODE
        cli.prepare_chat_loop = MagicMock()  # Prevent actual setup

        # Mock _process_user_input to avoid actual API calls
        with patch.object(cli, "_process_user_input", return_value=True) as mock_process:
            # Run the REPL loop with a patch to exit after processing one input
            cli._run_repl()

            # Verify input was processed
            mock_process.assert_called_with("Hello AI")


if __name__ == "__main__":
    unittest.main()
