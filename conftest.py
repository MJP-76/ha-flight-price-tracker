"""Pytest bootstrap.

Makes the repository root importable and, when Home Assistant is not installed
in the test environment, prepends a minimal ``homeassistant`` stub package so
the integration's modules can be imported for unit testing. The stubs are only
shape-compatible; they are never exercised by the pure-logic tests.
"""

import os
import sys

ROOT = os.path.dirname(__file__)
sys.path.insert(0, ROOT)

try:
    import homeassistant  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.join(ROOT, "tests", "stubs"))
