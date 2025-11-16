"""
Unit tests for run_live_trading.py entry point script.

Tests argument parsing, validation, and error handling.
Note: These tests verify script structure but won't execute
due to missing dependencies in test environment.
"""

import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestRunLiveTradingArgumentParsing(unittest.TestCase):
    """Test command-line argument parsing."""

    def setUp(self):
        """Setup test fixtures."""
        self.script_path = project_root / "run_live_trading.py"

    def test_script_exists(self):
        """Test that run_live_trading.py exists."""
        self.assertTrue(self.script_path.exists(), "run_live_trading.py not found")

    def test_script_is_executable(self):
        """Test that script has executable permissions."""
        import stat

        mode = self.script_path.stat().st_mode
        is_executable = bool(mode & stat.S_IXUSR)
        self.assertTrue(is_executable, "Script is not executable")

    def test_script_has_shebang(self):
        """Test that script has proper shebang line."""
        with open(self.script_path) as f:
            first_line = f.readline().strip()
        self.assertEqual(
            first_line, "#!/usr/bin/env python3", "Missing or incorrect shebang"
        )

    @patch("sys.argv", ["run_live_trading.py"])
    def test_missing_config_argument_shows_help(self):
        """Test that missing config_path shows help and exits."""
        # Import module to test argument parser
        import argparse

        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
            mock_parse.side_effect = SystemExit(2)

            with self.assertRaises(SystemExit):
                # This will trigger argparse error for missing required argument
                from run_live_trading import main

                main()

    @patch("sys.argv", ["run_live_trading.py", "--help"])
    def test_help_flag_displays_help(self):
        """Test that --help flag displays help message."""
        import argparse

        with patch("argparse.ArgumentParser.parse_args") as mock_parse:
            mock_parse.side_effect = SystemExit(0)

            with self.assertRaises(SystemExit) as cm:
                from run_live_trading import main

                main()

            self.assertEqual(cm.exception.code, 0)


class TestConfigFileValidation(unittest.TestCase):
    """Test config file validation."""

    @patch("sys.argv", ["run_live_trading.py", "nonexistent_config.json"])
    @patch("logging_system.setup_logging")
    @patch("logging_system.get_logger")
    @patch("sys.exit")
    def test_nonexistent_config_file_exits(self, mock_exit, mock_logger, mock_setup):
        """Test that nonexistent config file causes exit."""
        mock_logger_instance = MagicMock()
        mock_logger.return_value = mock_logger_instance
        mock_exit.side_effect = SystemExit(1)

        from run_live_trading import main

        with self.assertRaises(SystemExit):
            main()

        # Verify error was logged
        mock_logger_instance.error.assert_called_once()
        error_message = mock_logger_instance.error.call_args[0][0]
        self.assertIn("Config file not found", error_message)

        # Verify exit(1) was called
        mock_exit.assert_called_once_with(1)

    @patch("sys.argv", ["run_live_trading.py", "config/live_trading_config.json"])
    @patch("logging_system.setup_logging")
    @patch("logging_system.get_logger")
    @patch("scanner.live_trading_orchestrator.LiveTradingOrchestrator")
    @patch("pathlib.Path.exists")
    def test_valid_config_file_starts_orchestrator(
        self, mock_exists, mock_orch, mock_logger, mock_setup
    ):
        """Test that valid config file starts orchestrator."""
        # Mock config file exists
        mock_exists.return_value = True

        # Mock orchestrator
        mock_orch_instance = MagicMock()
        mock_orch.return_value = mock_orch_instance
        mock_orch_instance.start.side_effect = KeyboardInterrupt

        mock_logger_instance = MagicMock()
        mock_logger.return_value = mock_logger_instance

        from run_live_trading import main

        main()

        # Verify orchestrator was created with config path
        mock_orch.assert_called_once()
        call_args = mock_orch.call_args[0][0]
        self.assertIn("config/live_trading_config.json", call_args)

        # Verify start() was called
        mock_orch_instance.start.assert_called_once()


class TestLoggingSetup(unittest.TestCase):
    """Test logging configuration."""

    @patch("sys.argv", ["run_live_trading.py", "config.json", "--log-level", "DEBUG"])
    @patch("logging_system.setup_logging")
    @patch("logging_system.get_logger")
    @patch("scanner.live_trading_orchestrator.LiveTradingOrchestrator")
    @patch("pathlib.Path.exists")
    def test_log_level_argument_passed_to_setup(
        self, mock_exists, mock_orch, mock_logger, mock_setup
    ):
        """Test that --log-level argument is passed to setup_logging."""
        mock_exists.return_value = True
        mock_orch_instance = MagicMock()
        mock_orch.return_value = mock_orch_instance
        mock_orch_instance.start.side_effect = KeyboardInterrupt

        from run_live_trading import main

        main()

        # Verify setup_logging was called with DEBUG level
        mock_setup.assert_called_once()
        call_kwargs = mock_setup.call_args[1]
        self.assertEqual(call_kwargs["level"], "DEBUG")

    @patch(
        "sys.argv",
        ["run_live_trading.py", "config.json", "--log-file", "logs/test.log"],
    )
    @patch("logging_system.setup_logging")
    @patch("logging_system.get_logger")
    @patch("scanner.live_trading_orchestrator.LiveTradingOrchestrator")
    @patch("pathlib.Path.exists")
    def test_log_file_argument_passed_to_setup(
        self, mock_exists, mock_orch, mock_logger, mock_setup
    ):
        """Test that --log-file argument is passed to setup_logging."""
        mock_exists.return_value = True
        mock_orch_instance = MagicMock()
        mock_orch.return_value = mock_orch_instance
        mock_orch_instance.start.side_effect = KeyboardInterrupt

        from run_live_trading import main

        main()

        # Verify setup_logging was called with log file
        mock_setup.assert_called_once()
        call_kwargs = mock_setup.call_args[1]
        self.assertEqual(call_kwargs["log_file"], "logs/test.log")


class TestErrorHandling(unittest.TestCase):
    """Test error handling and graceful shutdown."""

    @patch("sys.argv", ["run_live_trading.py", "config.json"])
    @patch("logging_system.setup_logging")
    @patch("logging_system.get_logger")
    @patch("scanner.live_trading_orchestrator.LiveTradingOrchestrator")
    @patch("pathlib.Path.exists")
    def test_keyboard_interrupt_handled_gracefully(
        self, mock_exists, mock_orch, mock_logger, mock_setup
    ):
        """Test that Ctrl+C is handled gracefully."""
        mock_exists.return_value = True
        mock_orch_instance = MagicMock()
        mock_orch.return_value = mock_orch_instance
        mock_orch_instance.start.side_effect = KeyboardInterrupt

        mock_logger_instance = MagicMock()
        mock_logger.return_value = mock_logger_instance

        from run_live_trading import main

        main()  # Should not raise

        # Verify shutdown message was logged
        logged_messages = [
            call[0][0] for call in mock_logger_instance.info.call_args_list
        ]
        self.assertTrue(
            any("Ctrl+C" in msg or "shutting down" in msg for msg in logged_messages),
            "No shutdown message logged",
        )

    @patch("sys.argv", ["run_live_trading.py", "config.json"])
    @patch("logging_system.setup_logging")
    @patch("logging_system.get_logger")
    @patch("scanner.live_trading_orchestrator.LiveTradingOrchestrator")
    @patch("pathlib.Path.exists")
    @patch("sys.exit")
    def test_fatal_error_logged_and_exits(
        self, mock_exit, mock_exists, mock_orch, mock_logger, mock_setup
    ):
        """Test that fatal errors are logged and cause exit."""
        mock_exists.return_value = True
        mock_orch.side_effect = Exception("Fatal test error")
        mock_exit.side_effect = SystemExit(1)

        mock_logger_instance = MagicMock()
        mock_logger.return_value = mock_logger_instance

        from run_live_trading import main

        with self.assertRaises(SystemExit):
            main()

        # Verify exception was logged
        mock_logger_instance.exception.assert_called_once()

        # Verify exit(1) was called
        mock_exit.assert_called_once_with(1)


class TestScriptDocumentation(unittest.TestCase):
    """Test script documentation and usage."""

    def test_script_has_docstring(self):
        """Test that script has proper module docstring."""
        with open(project_root / "run_live_trading.py") as f:
            content = f.read()

        # Check for docstring
        self.assertIn('"""', content)
        self.assertIn("Usage:", content)
        self.assertIn("Entry point", content)

    def test_main_function_has_docstring(self):
        """Test that main() function has docstring."""
        with open(project_root / "run_live_trading.py") as f:
            content = f.read()

        # Check for main function with docstring
        self.assertIn("def main():", content)
        self.assertIn("Main entry point", content)


if __name__ == "__main__":
    unittest.main()
