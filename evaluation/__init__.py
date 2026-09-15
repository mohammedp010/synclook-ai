"""Offline evaluation suites.

The scripts here are run directly (``python evaluation/harness.py``) but they
also import each other, so the directory is a real package: without it the
shared modules resolve under two names depending on entry point.
"""
