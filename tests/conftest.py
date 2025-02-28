"""Pytest configuration file."""

import os
import sys

# Add the parent directory to the path so that the tests can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))