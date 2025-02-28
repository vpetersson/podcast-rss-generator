import os
import sys
import unittest
from unittest.mock import patch

from podcast_rss_generator.cli import main


class TestCLI(unittest.TestCase):
    @patch('podcast_rss_generator.cli.read_podcast_config')
    @patch('podcast_rss_generator.cli.generate_rss')
    @patch('sys.stdout')
    def test_main_with_default_args(self, mock_stdout, mock_generate_rss, mock_read_config):
        """Test the CLI with default arguments."""
        # Mock the config
        mock_config = {"metadata": {}, "episodes": []}
        mock_read_config.return_value = mock_config

        # Call main with default arguments
        with patch.object(sys, 'argv', ['podcast-rss-generator']):
            main()

        # Verify the correct functions were called with the right arguments
        mock_read_config.assert_called_once_with("podcast_config.yaml")
        mock_generate_rss.assert_called_once_with(mock_config, "podcast_feed.xml")

    @patch('podcast_rss_generator.cli.read_podcast_config')
    @patch('podcast_rss_generator.cli.generate_rss')
    @patch('sys.stdout')
    def test_main_with_custom_args(self, mock_stdout, mock_generate_rss, mock_read_config):
        """Test the CLI with custom arguments."""
        # Mock the config
        mock_config = {"metadata": {}, "episodes": []}
        mock_read_config.return_value = mock_config

        # Call main with custom arguments
        with patch.object(sys, 'argv', ['podcast-rss-generator', '--input-file', 'custom.yaml', '--output-file', 'custom.xml']):
            main()

        # Verify the correct functions were called with the right arguments
        mock_read_config.assert_called_once_with("custom.yaml")
        mock_generate_rss.assert_called_once_with(mock_config, "custom.xml")

    @patch('podcast_rss_generator.__version__', '0.1.0')
    @patch('sys.stdout')
    @patch('sys.exit')
    def test_version_flag(self, mock_exit, mock_stdout, *args):
        """Test the --version flag."""
        # Call main with --version flag
        with patch.object(sys, 'argv', ['podcast-rss-generator', '--version']):
            main()

        # Verify sys.exit was called with 0
        mock_exit.assert_called_once_with(0)

    @patch('podcast_rss_generator.cli.read_podcast_config')
    @patch('sys.stderr')
    @patch('sys.exit')
    def test_error_handling(self, mock_exit, mock_stderr, mock_read_config):
        """Test error handling in the CLI."""
        # Mock read_podcast_config to raise an exception
        mock_read_config.side_effect = Exception("Test error")

        # Call main
        with patch.object(sys, 'argv', ['podcast-rss-generator']):
            main()

        # Verify sys.exit was called with 1
        mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()