"""Test suite for YTGet.

Stdlib unittest only, so the suite runs with no extra dependencies:
    python3 -m unittest discover -s tests -t .

Only Qt-free modules are covered; anything importing PySide6 needs a display
and is excluded on purpose.
"""
