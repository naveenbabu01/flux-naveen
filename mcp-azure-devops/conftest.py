"""Add src/ to Python path so tool imports work from project root."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
