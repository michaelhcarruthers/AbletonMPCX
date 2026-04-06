"""Test suite configuration.

Adds the repository root (one level above this directory) to sys.path so that
``helpers`` and ``tools`` packages are importable without needing the repo to
be installed.
"""
import sys
import os

# Repo root: AMCPX/AMCPX/ (parent of tests/)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
